"""Runners for executing functions as jobs."""

from logging import LoggerAdapter, getLogger
from multiprocessing import Queue
from pathlib import Path
from typing import Any, Callable

from mpire.exception import InterruptWorker
from psutil import Process, TimeoutExpired

from cellophane.cfg import Config
from cellophane.cleanup import DeferredCleaner
from cellophane.data import OutputGlob, Samples
from cellophane.executors import Executor
from cellophane.logs import handle_warnings, redirect_logging_to_queue
from cellophane.util import Timestamp

from .checkpoint import Checkpoints


def _resolve_outputs(
    samples: Samples,
    workdir: Path,
    config: Config,
    timestamp: Timestamp,
    logger: LoggerAdapter,
) -> None:
    for output_ in samples.output.copy():
        if not isinstance(output_, OutputGlob):
            continue
        samples.output.remove(output_)
        if not samples.complete:
            continue
        try:
            samples.output |= output_.resolve(
                samples=samples.complete,
                workdir=workdir,
                config=config,
                timestamp=timestamp,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(f"Failed to resolve output {output_}: {exc!r}")
            logger.debug(exc, exc_info=True)


def _cleanup(
    *,
    runner: "Runner",
    reason: BaseException,
    logger: LoggerAdapter,
    samples: Samples,
    executor: Executor,
) -> None:
    match reason:
        case InterruptWorker():
            reason_ = f"Runner '{runner.name}' was interrupted"
        case SystemExit():
            reason_ = (
                f"Runner '{runner.name}' exitded with non-zero status"
                + (f"({reason.code})" if reason.code is not None else "")
            )
        case _:
            reason_ = f"Unhandled exception in runner '{runner.name}': {reason!r}"

    logger.warning(reason_)
    executor.terminate()

    logger.debug("Clearing outputs and failing samples")
    samples.output = set()
    for sample in samples:
        sample.fail(reason_)
    for proc in Process().children(recursive=True):
        try:
            logger.debug(f"Waiting for {proc.name()} ({proc.pid})")
            proc.terminate()
            proc.wait(10)
        except TimeoutExpired:
            logger.warning(f"Killing unresponsive process {proc.name()} ({proc.pid})")
            proc.kill()
            proc.wait()

class Runner:
    """A runner for executing a function as a job.

    Args:
    ----
        func (Callable): The function to be executed as a job.
        label (str | None): The label for the runner.
            Defaults to the name of the function.
        split_by (str | None): The attribute to split samples by.

    """

    label: str
    split_by: str | None
    func: Callable
    main: Callable[..., Samples | None]

    def __init__(
        self,
        func: Callable,
        label: str | None = None,
        split_by: str | None = None,
    ) -> None:
        self.__name__ = func.__name__  # type: ignore[attr-defined]
        self.__qualname__ = func.__qualname__  # type: ignore[attr-defined]
        self.name = func.__name__  # type: ignore[attr-defined]
        self.label = label or func.__name__  # type: ignore[attr-defined]
        self.main = staticmethod(func)
        self.label = label or self.__name__
        self.split_by = split_by
        super().__init_subclass__()

    def __call__(
        self,
        log_queue: Queue,
        /,
        config: Config,
        root: Path,
        samples: Samples,
        executor_cls: type[Executor],
        timestamp: Timestamp,
        workdir: Path,
        group: Any,
        dispatcher: Any,
    ) -> tuple[Samples, DeferredCleaner]:
        handle_warnings()
        redirect_logging_to_queue(log_queue)

        workdir.mkdir(parents=True, exist_ok=True)
        logger = LoggerAdapter(getLogger(), {"label": self.label})
        cleaner = DeferredCleaner(root=workdir)

        samples = dispatcher.run_pre_hooks(
            per="runner",
            samples=samples,
            cleaner=cleaner,
            checkpoint_suffix=f"runner_{self.name}",
        )

        with executor_cls(
            config=config,
            log_queue=log_queue,
            workdir_base=workdir,
            dispatcher=dispatcher,
        ) as executor:
            try:
                match self.main(
                    samples=samples,
                    config=config,
                    timestamp=timestamp,
                    logger=logger,
                    root=root,
                    workdir=workdir,
                    executor=executor,
                    cleaner=cleaner,
                    checkpoints=Checkpoints(
                        samples=samples,
                        prefix=f"runner.{self.name}.{group}" if group is not None else f"runner.{self.name}",
                        workdir=workdir,
                        config=config,
                    )
                ):
                    case None:
                        logger.debug("Runner did not return any samples")

                    case returned if isinstance(returned, Samples):
                        samples = returned

                    case returned:
                        logger.warning(f"Unexpected return type {type(returned)}")

                for sample in samples:
                    sample.processed = True

            except InterruptWorker as exc:
                _cleanup(runner=self, reason=exc, logger=logger, samples=samples, executor=executor)

            except BaseException as exc:
                dispatcher.run_exception_hooks(exception=exc)
                _cleanup(runner=self, reason=exc, logger=logger, samples=samples, executor=executor)

        _resolve_outputs(samples, workdir, config, timestamp, logger)
        for sample in samples.complete:
            logger.debug(f"Sample {sample.id} processed successfully")
        for sample in samples.unprocessed:
            sample.fail("Sample was not processed")
        if n_failed := len(samples.failed):
            logger.error(f"{n_failed} samples failed")
            cleaner.unregister(workdir)
        for sample in samples.failed:
            logger.debug(f"Sample {sample.id} failed - {sample.failed}")

        samples = dispatcher.run_post_hooks(
            per="runner",
            samples=samples,
            cleaner=cleaner,
            checkpoint_suffix=f"runner_{self.name}",
        )

        return samples, cleaner
