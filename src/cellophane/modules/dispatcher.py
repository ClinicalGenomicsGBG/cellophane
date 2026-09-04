from __future__ import annotations

from copy import deepcopy
from functools import partial, wraps
from logging import LoggerAdapter, getLogger
from multiprocessing import Lock
from typing import TYPE_CHECKING, Callable, overload

from mpire.exception import InterruptWorker
from mpire.pool import WorkerPool

from cellophane.logs import handle_warnings, redirect_logging_to_queue
from cellophane.data import Samples

from .checkpoint import Checkpoints
from .hook import ExceptionHook, PostHook, PreHook
from .predicate import select_samples, select_exception
from cellophane.cleanup import Cleaner, DeferredCleaner

if TYPE_CHECKING:
    from multiprocessing import Queue
    from multiprocessing.synchronize import Lock as LockType
    from pathlib import Path
    from typing import Any, Literal, Sequence
    from uuid import UUID

    from cellophane.cfg import Config
    from cellophane.executors.executor import Executor
    from cellophane.modules import Runner
    from cellophane.util import Timestamp


class MergeSamplesError(Exception): ...


class MergeCleanersError(Exception): ...


def _poolable(func: Callable) -> Callable:
    """Decorator to adapt a function to be run in a cellophane worker pool.

    All worker pools in cellophane are expected to have a shared reference to a logging queue,
    so this decorator handles the logging redirection and warning handling automatically.
    """

    @wraps(func)
    def inner(log_queue: Queue, /, log_label: str, dispatcher: "Dispatcher", **kwargs: Any) -> object:
        handle_warnings()
        redirect_logging_to_queue(log_queue)
        dispatcher._log_queue = log_queue
        logger = LoggerAdapter(getLogger(), {"label": log_label})
        return func(logger=logger, **kwargs, log_queue=log_queue, dispatcher=dispatcher)

    return inner


def _unlock_after(lock: LockType, callback: Callable | None = None) -> Callable:
    def inner(result):
        try:
            if callable(callback):
                callback(result)
        finally:
            lock.acquire(block=False)
            lock.release()

    return inner


def _exception_hook_error_callback(
    exception: Exception,
    *,
    logger: LoggerAdapter,
) -> None:
    logger.error(f"Unhandled exception when running exception hooks: {exception!r}", exc_info=exception)


def _pre_post_hooks_submit_error_callback(
    exception: Exception,
    *,
    when: Literal["pre", "post"],
    logger: LoggerAdapter,
    dispatcher: Dispatcher,
    pool: WorkerPool | None = None,
) -> None:
    logger.error(f"Unhandled exception when running {when} hooks: {exception!r}", exc_info=exception)
    dispatcher.run_exception_hooks(exception=exception, pool=pool)


def _runner_submit_error_callback(
    exception: Exception,
    *,
    logger: LoggerAdapter,
    dispatcher: Dispatcher,
    pool: WorkerPool | None = None,
) -> None:
    logger.error(f"Unhandled exception when submitting runner task: {exception!r}", exc_info=exception)
    dispatcher.run_exception_hooks(exception=exception, pool=pool)


def _merge_cleaners(
    this: Cleaner | DeferredCleaner,
    that: Cleaner | DeferredCleaner,
):
    try:
        this &= that
    except Exception as exc:
        raise MergeCleanersError(f"Unhandled exception when merging cleaners: {exc!r}")


def _merge_samples(this: Samples, that: Samples, override: bool = False):
    try:
        if len(this) == 0 or override:
            this ^= that
        else:
            this &= that
    except Exception as exc:
        for sample in that:
            if sample.uuid not in this:
                this.append(sample)
            this[sample.uuid].fail(repr(exc))
        raise MergeSamplesError(f"Unhandled exception when merging samples: {exc!r}") from exc


def _pre_post_hooks_callback(
    result: tuple[Samples, DeferredCleaner],
    *,
    logger: LoggerAdapter,
    samples: Samples,
    cleaner: Cleaner | DeferredCleaner,
    pool: WorkerPool | None = None,
    dispatcher: Dispatcher,
) -> None:
    try:
        with dispatcher.cleaner_lock:
            _merge_cleaners(cleaner, result[1])
        with dispatcher.samples_lock:
            _merge_samples(samples, result[0], override=True)
    except (MergeCleanersError, MergeSamplesError) as exc:
        logger.error(str(exc))
        dispatcher.run_exception_hooks(exception=exc, pool=pool)

def _runner_callback(
    result: tuple[Samples, DeferredCleaner],
    *,
    logger: LoggerAdapter,
    samples: Samples,
    cleaner: Cleaner,
    sample_runner_count: dict[UUID, int],
    dispatcher: Dispatcher,
    pool: WorkerPool,
) -> None:
    try:
        with dispatcher.cleaner_lock:
            _merge_cleaners(cleaner, result[1])
        with dispatcher.samples_lock:
            _merge_samples(samples, result[0])
            for s in result[0]:
                sample_runner_count[s.uuid] -= 1
                if sample_runner_count[s.uuid] == 0:
                    dispatcher.run_post_hooks(
                        per="sample",
                        samples=samples,
                        cleaner=cleaner,
                        pool=pool,
                        uuid=s.uuid,
                    )
    except (MergeSamplesError, MergeCleanersError) as exc:
        logger.error(str(exc))
        dispatcher.run_exception_hooks(exception=exc, pool=pool)
    except Exception as exc:
        logger.error(f"Unhandled exception in runner callback: {exc!r}", exc_info=exc)
        dispatcher.run_exception_hooks(exception=exc, pool=pool)


def _run_pre_post_hooks(
    hooks: Sequence[PreHook | PostHook | ExceptionHook],
    *,
    when: Literal["pre", "post"],
    per: Literal["session", "sample", "runner"],
    samples: Samples,
    config: Config,
    root: Path,
    executor_cls: type[Executor],
    log_queue: Queue,
    timestamp: Timestamp,
    checkpoint_suffix: str | None = None,
    cleaner: Cleaner | DeferredCleaner,
    logger: LoggerAdapter,
    dispatcher: "Dispatcher",
) -> tuple[Samples, Cleaner | DeferredCleaner]:
    for hook in [h for h in hooks if isinstance(h, (PreHook, PostHook)) and (h.when, h.per) == (when, per)]:
        try:
            hook_samples = None
            match hook.condition:
                case c if c not in ["always", "unprocessed", "complete", "failed"] and not callable(c):
                    logger.warning(f"Hook '{hook.label}' has an invalid condition '{hook.condition}', skipping")
                    continue
                case "always":
                    hook_samples = samples
                case "unprocessed" if not (hook_samples := samples.unprocessed):
                    continue
                case "complete" if not (hook_samples := samples.complete):
                    continue
                case "failed" if not (hook_samples := samples.failed):
                    continue
                case predicate if (
                    callable(predicate) and (hook_samples := select_samples(samples, config, predicate)) is None
                ):
                    logger.debug(f"No samples satisfy condition for {when}-hook '{hook.label}', skipping")
                    continue

            if hook_samples is None:
                logger.warning(f"Hook '{hook.label}' has an invalid condition '{hook.condition}', skipping")
                continue

            checkpoints = Checkpoints(
                samples=hook_samples,
                prefix=(
                    f"{hook.when}-hook.{hook.name}"
                    if checkpoint_suffix is None
                    else f"{hook.when}-hook.{hook.name}.{checkpoint_suffix}"
                ),
                workdir=config.workdir / config.tag,
                config=config,
            )

            samples |= hook(
                samples=hook_samples,
                config=config,
                root=root,
                executor_cls=executor_cls,
                log_queue=log_queue,
                timestamp=timestamp,
                cleaner=cleaner,
                checkpoints=checkpoints,
                dispatcher=dispatcher,
            )
        except (KeyboardInterrupt, InterruptWorker):
            logger.warning("Keyboard interrupt received, failing samples and stopping execution")
            for sample in samples:
                sample.fail(f"{when.capitalize()} hook {hook.label} interrupted")
        except BaseException as exc:
            logger.error(f"Unhandled exception in {when} hook '{hook.label}': {exc!r}")
            dispatcher.run_exception_hooks(exception=exc)
            for sample in samples:
                sample.fail(f"Hook {hook.name} failed: {exc}")

    return samples, cleaner


def _run_exception_hooks(
    hooks: Sequence[PreHook | PostHook | ExceptionHook],
    *,
    exception: BaseException,
    config: Config,
    root: Path,
    executor_cls: type[Executor],
    log_queue: Queue,
    timestamp: Timestamp,
    logger: LoggerAdapter,
    dispatcher: "Dispatcher",
) -> None:
    for hook in [h for h in hooks if isinstance(h, ExceptionHook)]:
        try:
            if callable(hook.condition) and not select_exception(exception, config, hook.condition):
                logger.debug(
                    f"Exception {exception!r} does not satisfy condition "
                    f"for exception hook '{hook.label}', skipping"
                )
                continue
            else:
                hook(
                    exception=exception,
                    config=config,
                    root=root,
                    executor_cls=executor_cls,
                    log_queue=log_queue,
                    timestamp=timestamp,
                    dispatcher=dispatcher,
                )
        except Exception as exc:
            logger.error(f"Unhandled exception in exception hook '{hook.label}': {exc!r}", exc_info=True)


def _start_runners(
    runners: Sequence[Runner],
    *,
    samples: Samples,
    logger: LoggerAdapter,
    log_queue: Queue,
    config: Config,
    root: Path,
    executor_cls: type[Executor],
    timestamp: Timestamp,
    cleaner: Cleaner,
    dispatcher: "Dispatcher",
) -> Samples:
    """Start cellphane runners in parallel and collect the results.

    Args:
    ----
        runners (Sequence[Runner]): The runners to execute.
        samples (data.Samples): The samples to process.
        logger (LoggerAdapter): The logger.
        log_queue (Queue): The queue for logging.
        kwargs (Any): Additional keyword arguments to pass to the runners.

    Returns:
    -------
        data.Samples: The samples after processing.

    """
    if not samples:
        logger.warning("No samples to process")
        return samples

    if not runners:
        logger.warning("No runners to execute")
        for sample in samples:
            sample.fail("Sample was not processed")
        return samples

    result_samples = samples.__class__()
    sample_runner_count: dict[UUID, int] = {sample.uuid: 0 for sample in samples}

    with WorkerPool(
        use_dill=True,
        daemon=False,
        start_method="fork",
        shared_objects=log_queue,
    ) as pool:
        try:
            for runner in runners:
                workdir = config.workdir / config.tag / runner.name

                if not callable(runner.condition):
                    runner_samples = samples
                elif not (runner_samples := select_samples(samples, config, runner.condition)):
                    logger.debug(f"No samples satisfy condition for runner '{runner.label}', skipping")
                    continue

                if runner.split_by is not None:
                    split_samples = runner_samples.split(
                        by=runner.split_by,
                        samples=runner_samples,
                        config=config,
                    )
                else:
                    split_samples = [(None, runner_samples)]

                for group, group_samples in split_samples:
                    if runner.split_by is None:
                        group_workdir = workdir
                    elif group is None:
                        group_workdir = workdir / "unknown"
                    elif isinstance(group, (str, int, bool)):
                        group_workdir = workdir / str(group)
                    else:
                        hash_ = hash(group).to_bytes(8, "big", signed=True).hex()
                        group_workdir = workdir / hash_
                    lock = dispatcher.get_lock()
                    for sample in group_samples:
                        sample_runner_count[sample.uuid] += 1
                    callback = partial(
                        _runner_callback,
                        logger=logger,
                        samples=result_samples,
                        sample_runner_count=sample_runner_count,
                        cleaner=cleaner,
                        dispatcher=dispatcher,
                        pool=pool,
                    )
                    error_callback = partial(
                        _runner_submit_error_callback,
                        logger=logger,
                        dispatcher=dispatcher,
                    )

                    pool.apply_async(
                        runner,
                        kwargs={
                            "config": config,
                            "root": root,
                            "samples": group_samples,
                            "executor_cls": executor_cls,
                            "timestamp": timestamp,
                            "workdir": group_workdir,
                            "group": group,
                            "dispatcher": dispatcher,
                        },
                        callback=_unlock_after(lock, callback),
                        error_callback=_unlock_after(lock, error_callback),
                    )

            dispatcher.wait_until_complete()

        except KeyboardInterrupt:
            logger.critical("Received SIGINT, telling runners to shut down...")
            pool.terminate()

        except BaseException as exc:
            logger.critical(f"Unhandled exception when starting runners: {exc!r}", exc_info=exc)
            dispatcher.run_exception_hooks(exception=exc)
            pool.terminate()
        finally:
            pool.stop_and_join()

    return result_samples if len(result_samples) > 0 else samples


class Dispatcher:
    """Convienience class to dispatch hooks, optionally in a separate process."""

    _common_kwargs: dict[str, Any]
    _hooks: Sequence[PreHook | PostHook | ExceptionHook]
    _runners: Sequence[Runner]
    _logger: LoggerAdapter
    _log_queue: Queue
    _samples_lock: LockType | None
    _cleaner_lock: LockType | None
    _task_locks: list[LockType]

    def __init__(
        self,
        hooks: Sequence[PreHook | PostHook | ExceptionHook],
        runners: Sequence[Runner],
        config: Config,
        root: Path,
        executor_cls: type[Executor],
        log_queue: Queue,
        timestamp: Timestamp,
        logger: LoggerAdapter,
    ) -> None:
        self._common_kwargs = {
            "config": config,
            "root": root,
            "executor_cls": executor_cls,
            "timestamp": timestamp,
        }
        self._hooks = hooks
        self._runners = runners
        self._logger = logger
        self._log_queue = log_queue
        self._samples_lock = None
        self._cleaner_lock = None
        self._task_locks = []

    @property
    def samples_lock(self) -> LockType:
        if self._samples_lock is None:
            self._samples_lock = Lock()
        return self._samples_lock

    @property
    def cleaner_lock(self) -> LockType:
        if self._cleaner_lock is None:
            self._cleaner_lock = Lock()
        return self._cleaner_lock

    def __getstate__(self):
        return self.__dict__ | {
            "_task_locks": [],
            "_samples_lock": None,
            "_cleaner_lock": None,
            "_log_queue": None,
        }

    def _run_hooks(
        self,
        hooks_runner_fn: Callable,
        hooks_kwargs: dict,
        pool: WorkerPool | None = None,
        callback: Callable | None = None,
        error_callback: Callable | None = None,
    ) -> Samples | None:
        lock = self.get_lock()
        callback_ = _unlock_after(lock, callback)
        error_callback_ = _unlock_after(lock, error_callback)
        if pool is not None:
            pool.apply_async(
                _poolable(hooks_runner_fn),
                kwargs={
                    **hooks_kwargs,
                    "hooks": self._hooks,
                    "log_label": (self._logger.extra or {"label": "cellophane"})["label"],
                    "dispatcher": self,
                },
                callback=callback_,
                error_callback=error_callback_,
            )
        else:
            try:
                result = hooks_runner_fn(
                    **hooks_kwargs,
                    hooks=self._hooks,
                    log_queue=self._log_queue,
                    logger=self._logger,
                    dispatcher=self,
                )
                callback_(result)
                match result:
                    case tuple([Samples() as s, _]):
                        return s
                    case _:
                        return None
            except Exception as exc:
                error_callback_(exc)

    def get_lock(self) -> LockType:
        (lock := Lock()).acquire()
        self._task_locks.append(lock)
        return lock

    def wait_until_complete(self) -> None:
        for lock in self._task_locks:
            lock.acquire()

    @overload
    def run_pre_hooks(
        self,
        per: Literal["session", "runner"],
        samples: Samples,
        cleaner: Cleaner | DeferredCleaner,
        pool: None = None,
        checkpoint_suffix: str | None = None,
    ) -> Samples: ...
    @overload
    def run_pre_hooks(
        self,
        per: Literal["session", "runner"],
        samples: Samples,
        cleaner: Cleaner | DeferredCleaner,
        pool: WorkerPool,
        checkpoint_suffix: str | None = None,
    ) -> None: ...
    def run_pre_hooks(
        self,
        per: Literal["session", "runner"],
        samples: Samples,
        cleaner: Cleaner | DeferredCleaner,
        pool: WorkerPool | None = None,
        checkpoint_suffix: str | None = None,
    ) -> Samples | None:
        """Run pre-hooks for the given scope."""
        samples_ = deepcopy(samples)
        result = self._run_hooks(
            hooks_runner_fn=_run_pre_post_hooks,
            hooks_kwargs={
                **self._common_kwargs,
                "when": "pre",
                "per": per,
                "samples": samples_,
                "cleaner": cleaner,
                "checkpoint_suffix": checkpoint_suffix,
            },
            pool=pool,
            callback=partial(
                _pre_post_hooks_callback,
                samples=samples,
                cleaner=cleaner,
                pool=pool,
                dispatcher=self,
                logger=self._logger,
            ),
            error_callback=partial(
                _pre_post_hooks_submit_error_callback,
                pool=pool,
                dispatcher=self,
                logger=self._logger,
            ),
        )
        return result

    @overload
    def run_post_hooks(
        self,
        per: Literal["session", "runner"],
        samples: Samples,
        cleaner: Cleaner | DeferredCleaner,
        pool: None = None,
        uuid: None = None,
        checkpoint_suffix: str | None = None,
    ) -> Samples: ...
    @overload
    def run_post_hooks(
        self,
        per: Literal["session", "runner"],
        samples: Samples,
        cleaner: Cleaner | DeferredCleaner,
        pool: WorkerPool,
        uuid: None = None,
        checkpoint_suffix: str | None = None,
    ) -> None: ...
    @overload
    def run_post_hooks(
        self,
        per: Literal["sample"],
        samples: Samples,
        cleaner: Cleaner | DeferredCleaner,
        pool: WorkerPool,
        uuid: UUID,
        checkpoint_suffix: str | None = None,
    ) -> None: ...
    def run_post_hooks(
        self,
        per: Literal["session", "runner", "sample"],
        samples: Samples,
        cleaner: Cleaner | DeferredCleaner,
        pool: WorkerPool | None = None,
        uuid: UUID | None = None,
        checkpoint_suffix: str | None = None,
    ) -> Samples | None:
        """Run post-hooks for the given scope."""
        samples_ = deepcopy(samples)
        if per == "sample" and uuid is not None:
            samples_.data = [s for s in samples_ if s.uuid == uuid]

        result = self._run_hooks(
            hooks_runner_fn=_run_pre_post_hooks,
            hooks_kwargs={
                **self._common_kwargs,
                "when": "post",
                "per": per,
                "samples": samples_,
                "cleaner": cleaner,
                "checkpoint_suffix": checkpoint_suffix,
            },
            pool=pool,
            callback=partial(
                _pre_post_hooks_callback,
                samples=samples,
                cleaner=cleaner,
                pool=pool,
                dispatcher=self,
                logger=self._logger,
            ),
            error_callback=partial(
                _pre_post_hooks_submit_error_callback,
                pool=pool,
                dispatcher=self,
                logger=self._logger,
            ),
        )
        return result

    def run_exception_hooks(
        self,
        exception: BaseException,
        pool: WorkerPool | None = None,
    ) -> None:
        """Run exception-hooks for the given scope."""
        self._run_hooks(
            hooks_runner_fn=_run_exception_hooks,
            hooks_kwargs={
                **self._common_kwargs,
                "exception": exception,
            },
            pool=pool,
            error_callback=partial(
                _exception_hook_error_callback,
                logger=self._logger,
            ),
        )

    def start_runners(
        self,
        samples: Samples,
        cleaner: Cleaner,
    ) -> Samples:
        """Start runners using this dispatcher's configuration."""
        return _start_runners(
            **self._common_kwargs,
            runners=self._runners,
            samples=samples,
            log_queue=self._log_queue,
            cleaner=cleaner,
            dispatcher=self,
            logger=self._logger,
        )
