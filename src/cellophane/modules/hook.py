from copy import deepcopy
from functools import partial
from graphlib import TopologicalSorter
from logging import LoggerAdapter, getLogger
from multiprocessing import Queue
from pathlib import Path
from typing import Callable, Literal, Sequence

from mpire.exception import InterruptWorker

from cellophane.cfg import Config
from cellophane.cleanup import Cleaner, DeferredCleaner
from cellophane.data import Samples
from cellophane.executors import Executor
from cellophane.util import Timestamp

from .checkpoint import Checkpoints
from .deps import DEPENDENCY, _internal


def _organize_internal(
    before: DEPENDENCY | list[DEPENDENCY] | None,
    after: DEPENDENCY | list[DEPENDENCY] | None,
) -> tuple[list[DEPENDENCY], list[DEPENDENCY]]:
    match before or [], after or []:
        # Check if both before and after are empty
        case [[], []]:
            return [], []

        # Ensure that all dependencies are lists
        case b, a if not isinstance(b, list):
            return _organize_internal([b], a)
        case b, a if not isinstance(a, list):
            return _organize_internal(b, [a])

        # Replace "all" with _internal.ALL
        case [["all", *b] | [*b, "all"], a]:
            return _organize_internal([_internal.ALL, *b], a)
        case b, ["all", *a] | [*a, "all"]:
            return _organize_internal(b, [*a, _internal.ALL])

        # Replace _internal.ALL with BEFORE_ALL or AFTER_ALL
        case [[_internal.ALL, *b] | [*b, _internal.ALL], a]:
            return _organize_internal([*b, _internal.BEFORE_ALL], a)
        case b, [_internal.ALL, *a] | [*a, _internal.ALL]:
            return _organize_internal(b, [*a, _internal.AFTER_ALL])

        # Check if before and after are already lists
        case b, a if not all(isinstance(i, (str, _internal)) for i in {*b, *a}):
            raise ValueError(f"{before=}, {after=}")

        # Ensure hooks run between BEFORE_ALL and AFTER_ALL unless otherwise specified
        case b, a if not {_internal.BEFORE_ALL, _internal.AFTER_ALL} & {*a, *b}:
            return _organize_internal(
                [*b, _internal.AFTER_ALL], [*a, _internal.BEFORE_ALL]
            )

        # Check if before and after are already valid
        case list(b), list(a) if all(isinstance(d, (str, _internal)) for d in {*b, *a}):
            return b, a

    # If we reach here, the dependencies are not valid
    raise ValueError(f"{before=}, {after=}")


class Hook:
    """Base class for cellophane pre/post-hooks."""

    name: str
    label: str
    func: Callable
    when: Literal["pre", "post"]
    condition: Literal["always", "complete", "failed"]
    before: list[DEPENDENCY]
    after: list[DEPENDENCY]
    per: Literal["session", "sample", "runner"] = "session"

    def __init__(
        self,
        func: Callable,
        when: Literal["pre", "post"],
        label: str | None = None,
        condition: Literal["always", "complete", "failed"] = "always",
        before: DEPENDENCY | list[DEPENDENCY] | None = None,
        after: DEPENDENCY | list[DEPENDENCY] | None = None,
        per: Literal["session", "sample", "runner"] = "session",
    ) -> None:
        try:
            self.before, self.after = _organize_internal(before, after)
        except ValueError as exc:
            raise ValueError(f"{func.__name__}: {exc}") from exc
        self.__name__ = func.__name__
        self.__qualname__ = func.__qualname__
        self.__module__ = func.__module__
        self.name = func.__name__
        self.label = label or func.__name__
        self.condition = condition
        self.func = staticmethod(func)
        self.when = when
        self.per = per

    def __call__(
        self,
        samples: Samples,
        config: Config,
        root: Path,
        executor_cls: type[Executor],
        log_queue: Queue,
        timestamp: Timestamp,
        cleaner: Cleaner,
        checkpoints: Checkpoints,
    ) -> Samples:
        logger = LoggerAdapter(getLogger(), {"label": self.label})
        logger.debug(f"Running {self.label} hook")
        _workdir = config.workdir / config.tag
        with executor_cls(
            config=config,
            log_queue=log_queue,
            workdir_base=_workdir,
        ) as executor:
            match self.func(
                samples=samples,
                config=config,
                timestamp=timestamp,
                logger=logger,
                root=root,
                workdir=_workdir,
                executor=executor,
                cleaner=cleaner,
                checkpoints=checkpoints,
            ):
                case returned if isinstance(returned, Samples):
                    _ret = returned
                case None:
                    logger.debug("Hook did not return any samples")
                    _ret = samples
                case returned:
                    logger.warning(f"Unexpected return type {type(returned)}")
                    _ret = samples
        return _ret


def resolve_dependencies(hooks: list[Hook]) -> list[Hook]:
    """Resolves hook dependencies and returns the hooks in the resolved order.
    Uses a topological sort to resolve dependencies. If the order of two hooks
    cannot be determined, the order is not guaranteed.

    # FIXME: It should be possible to determine the order of all hooks

    Args:
    ----
        hooks (list[Hook]): The list of hooks to resolve.

    Returns:
    -------
        list[Hook]: The hooks in the resolved order.

    """
    # Initialize the graph with the internal stage order
    graph: dict[DEPENDENCY, set[DEPENDENCY]] = _internal.order()

    for hook in hooks:
        hook_phase = _internal.PRE if hook.when == "pre" else _internal.POST
        # Add the hook to the graph
        if hook.__name__ not in graph:
            graph[hook.__name__] = set()

        # Add the dependencies to the hook node
        for dependency in hook.after:
            if isinstance(dependency, _internal):
                dependency = hook_phase | dependency
            graph[hook.__name__].add(dependency)

        # Add the hook to the any node that depends on it, creating nodes as needed
        for dependency in hook.before:
            if isinstance(dependency, _internal):
                dependency = hook_phase | dependency
            if dependency not in graph:
                graph[dependency] = set()
            graph[dependency].add(hook.__name__)

    # Sort the hooks in topological order
    order = [*TopologicalSorter(graph).static_order()]
    return [*sorted(hooks, key=lambda h: order.index(h.__name__))]


def run_hooks(
    hooks: Sequence[Hook],
    *,
    when: Literal["pre", "post"],
    per: Literal["session", "sample", "runner"],
    samples: Samples,
    config: Config,
    root: Path,
    executor_cls: type[Executor],
    log_queue: Queue,
    timestamp: Timestamp,
    cleaner: Cleaner | DeferredCleaner,
    logger: LoggerAdapter,
    checkpoint_suffix: str | None = None,
) -> Samples:
    """Run hooks at the specified time and update the samples object.

    Args:
    ----
        hooks (Sequence[Hook]): The hooks to run.
        when (Literal["pre", "post"]): The time to run the hooks.
        samples (data.Samples): The samples object to update.
        **kwargs (Any): Additional keyword arguments to pass to the hooks.

    Returns:
    -------
        data.Samples: The updated samples object.

    """
    samples_ = deepcopy(samples)

    for hook in [h for h in hooks if (h.when, h.per) == (when, per)]:
        checkpoint_prefix = f"{when}-hook.{hook.name}"
        if checkpoint_suffix:
            checkpoint_prefix += f".{checkpoint_suffix}"
        hook_ = partial(
            hook,
            config=config,
            root=root,
            executor_cls=executor_cls,
            log_queue=log_queue,
            timestamp=timestamp,
            cleaner=cleaner,
            checkpoints=Checkpoints(
                samples=samples,
                prefix=checkpoint_prefix,
                workdir=config.workdir / config.tag,
                config=config,
            ),
        )
        if hook.when == "pre":
            # Catch exceptions to allow post-hooks to run even if a pre-hook fails
            try:
                samples_ = hook_(samples=samples_)
            except (KeyboardInterrupt, InterruptWorker):
                logger.warning("Keyboard interrupt received, failing samples and stopping execution")
                for sample in samples_:
                    sample.fail(f"Hook {hook.name} interrupted")
                break
            except BaseException as exc:
                logger.error(f"Exception in {hook.label}: {exc}")
                for sample in samples_:
                    sample.fail(f"Hook {hook.name} failed: {exc}")
                break
        elif hook.condition == "always":
            samples_ = hook_(samples=samples_)
        elif hook.condition == "complete" and (s := samples.complete):
            samples_ = hook_(samples=s) | samples_.failed
        elif hook.condition == "failed" and (s := samples.failed):
            samples_ = hook_(samples=s) | samples_.complete

    return samples_
