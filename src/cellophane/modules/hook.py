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
from .deps import DEPENDENCY, _flag, stage


def _get_hook_by_name(name: str, hooks: list["Hook"]) -> "Hook | None":
    return next((h for h in hooks if h.name == name), None)


def _get_next_hook(hook: "Hook", hooks: list["Hook"]) -> tuple["Hook", DEPENDENCY | None]:
    """Get the next named hook in the dependency chain."""
    # _flags = {f for f in hook.before if isinstance(f, _flag) and not _flag.ALL & f}
    _hooks = {h for h in hooks if h.name in hook.before and h.name != hook.name}

    _hook: "Hook" = hook
    _min: DEPENDENCY | None = None
    for dep in _hooks:
        _, _dep_min = _get_next_hook(dep, hooks)
        if _min is None or (_dep_min is not None and _dep_min < _min):
            _hook, _min = dep, _dep_min

    return _hook, _min

def _get_prev_hook(hook: "Hook", hooks: list["Hook"]) -> tuple["Hook | None", DEPENDENCY | None]:
    """Get the last named hook in the dependency chain."""
    # _flags = {f for f in hook.after if isinstance(f, _flag) and not _flag.ALL & f}
    _hooks = {h for h in hooks if h.name in hook.after and h.name != hook.name}

    _hook: "Hook | None" = None
    _max: DEPENDENCY | None = None
    for dep in _hooks:
        _, _dep_max = _get_prev_hook(dep, hooks)
        if _max is None or (_dep_max is not None and _dep_max > _max):
            _hook, _max = dep, _dep_max

    return _hook, _max


def before(hook: "Hook", hooks: list["Hook"]) -> tuple[set[_flag], set[str]]:
    _flags = set()
    _names = set()
    for d in hook.before:
        if isinstance(d, _flag) and _flag.ALL not in d:
            _flags.add(d)
        elif isinstance(d, str) and (h := _get_hook_by_name(d, hooks)) is not None:
            _names.add(d)
            if any(b := before(h, hooks)):
                _flags |= b[0]
                _names |= b[1]
    if not _flags and not _names and any(a := after(hook, hooks)):
        _flags.add(max(a[0]).next())
        # for n in a[1]:
        #     if (h := _get_hook_by_name(n, hooks)) is not None:
        #         _names |= {n for n in before(h, hooks)[1] if n not in a[1]}
    return _flags, _names


def after(hook: "Hook", hooks: list["Hook"]) -> tuple[set[_flag], set[str]]:
    _flags = set()
    _names = set()
    for d in hook.after:
        if isinstance(d, _flag) and _flag.ALL not in d:
            _flags.add(d)
        elif isinstance(d, str) and (h := next((h for h in hooks if h.name == d), None)) is not None:
            _names.add(d)
            if any(a := after(h, hooks)):
                _flags |= a[0]
                _names |= a[1]
    if not _flags and any(b := before(hook, hooks)):
        _flags.add(min(b[0]).previous())
        # for n in b[1]:
        #     if (h := _get_hook_by_name(n, hooks)) is not None:
        #         _names |= {n for n in after(h, hooks)[1] if n not in b[1]}

    return _flags, _names


def _insert_neighbor_stages(hooks: list["Hook"]) -> list["Hook"]:
    import logging
    _hooks = hooks.copy()
    for hook in _hooks:
        _b_flags, _b_names = before(hook, hooks)
        _a_flags, _a_names = after(hook, hooks)
        hook.before = [*{*hook.before, *_b_flags, *_b_names}]
        hook.after = [*{*hook.after, *_a_flags, *_a_names}]

        logging.debug(f"--- Hook {hook.__name__} ---")
        logging.debug("--- before ---")
        for b in hook.before:
            logging.debug(f"{b!r}")
        logging.debug("--- after ---")
        for a in hook.after:
            logging.debug(f"{a!r}")
        logging.debug("\n")

    return hooks


# node='pre_before_all' deps=set()
# node='pre_before_samples_init' deps={
#   BEFORE|PRE|ALL,
#   "pre_before_all"
# }
# node='pre_before_notifications_init' deps={
#   BEFORE|PRE|ALL,
#   "pre_before_all",
#   BEFORE|PRE|SAMPLES_INIT,
#   "pre_before_samples_init"
#   AFTER|PRE|SAMPLES_INIT,
# }
# node='pre_before_notifications_sent' deps={
#   BEFORE|PRE|ALL,
#   "pre_before_all",
#   BEFORE|PRE|SAMPLES_INIT,
#   "pre_before_samples_init",
#   AFTER|PRE|SAMPLES_INIT,
#   BEFORE|PRE|NOTIFICATIONS_INIT,
#   "pre_before_notifications_init"
#   AFTER|PRE|NOTIFICATIONS_INIT,
# }
# node='pre_before_files_init' deps={
#   BEFORE|PRE|ALL
#   "pre_before_all",
#   BEFORE|PRE|SAMPLES_INIT,
#   "pre_before_samples_init",
#   AFTER|PRE|SAMPLES_INIT,
#   BEFORE|PRE|NOTIFICATIONS_INIT,
#   "pre_before_notifications_init",
#   AFTER|PRE|NOTIFICATIONS_INIT,
#   BEFORE|PRE|NOTIFICATIONS_SENT,
#   "pre_before_notifications_sent"
#   AFTER|PRE|NOTIFICATIONS_SENT,
# }
# node='pre_before_output_init' deps={
#   BEFORE|PRE|ALL
#  "pre_before_all",
 #   BEFORE|PRE|SAMPLES_INIT,
#   "pre_before_samples_init",
#   AFTER|PRE|SAMPLES_INIT,
#   BEFORE|PRE|NOTIFICATIONS_INIT,
#   "pre_before_notifications_init",
#   AFTER|PRE|NOTIFICATIONS_INIT,
#   BEFORE|PRE|NOTIFICATIONS_SENT,
#   "pre_before_notifications_sent",
#   AFTER|PRE|NOTIFICATIONS_SENT,
#   BEFORE|PRE|FILES_INIT,
#   "pre_before_files_init"
#   AFTER|PRE|FILES_INIT,
# }
# node='pre_after_output_init' deps={
#   BEFORE|PRE|ALL
#   "pre_before_all",
#   BEFORE|PRE|SAMPLES_INIT,
#   "pre_before_samples_init",
#   AFTER|PRE|SAMPLES_INIT,
#   BEFORE|PRE|NOTIFICATIONS_INIT,
#   "pre_before_notifications_init",
#   AFTER|PRE|NOTIFICATIONS_INIT,
#   BEFORE|PRE|NOTIFICATIONS_SENT,
#   "pre_before_notifications_sent",
#   AFTER|PRE|NOTIFICATIONS_SENT,
#   BEFORE|PRE|FILES_INIT,
#   "pre_before_files_init",
#   AFTER|PRE|FILES_INIT,
#   BEFORE|PRE|OUTPUT_INIT,
#   "pre_before_output_init"
#   AFTER|PRE|OUTPUT_INIT,
# }
# node='pre_after_all' deps={
#   BEFORE|PRE|ALL,
#   "pre_before_all",
#   BEFORE|PRE|SAMPLES_INIT,
#   "pre_before_samples_init",
#   AFTER|PRE|SAMPLES_INIT,
#   BEFORE|PRE|NOTIFICATIONS_INIT,
#   "pre_before_notifications_init",
#   AFTER|PRE|NOTIFICATIONS_INIT,
#   BEFORE|PRE|NOTIFICATIONS_SENT,
#   "pre_before_notifications_sent",
#   AFTER|PRE|NOTIFICATIONS_SENT,
#   BEFORE|PRE|FILES_INIT,
#   "pre_before_files_init",
#   AFTER|PRE|FILES_INIT,
#   BEFORE|PRE|OUTPUT_INIT,
#   "pre_before_output_init",
#   AFTER|PRE|OUTPUT_INIT,
#   "pre_after_output_init"
#   AFTER|PRE|FILES_INIT,
#   AFTER|PRE|ALL
# }

def _update_before_after(
    before: DEPENDENCY | list[DEPENDENCY] | None,
    after: DEPENDENCY | list[DEPENDENCY] | None,
    phase: Literal["pre", "post"],
) -> tuple[list[DEPENDENCY], list[DEPENDENCY]]:
    match phase:
        case "pre":
            _phase = _flag.PRE
        case "post":
            _phase = _flag.POST
        case _:
            raise ValueError(f"Invalid phase: {phase}")

    match before or [], after or []:
        # Check if both before and after are empty
        case [[], []]:
            return [], []

        # Ensure that before and after are lists
        case b, a if not isinstance(b, list):
            return _update_before_after([b], a, phase)
        case b, a if not isinstance(a, list):
            return _update_before_after(b, [a], phase)

        # Check that all dependencies are valid types
        case b, a if not all(isinstance(i, (str, _flag)) for i in {*b, *a}):
            raise ValueError(f"{before=}, {after=}")

        # Replace "all" with _flag.ALL
        case [["all", *b] | [*b, "all"], a]:
            return _update_before_after([_flag.ALL, *b], a, phase)
        case b, ["all", *a] | [*a, "all"]:
            return _update_before_after(b, [*a, _flag.ALL], phase)

        # Add PRE or POST and  BEFORE or AFTER flags to the dependencies
        case [[flag, *b], a] if flag in stage.values() and isinstance(flag, _flag):
            return _update_before_after([_phase | _flag.BEFORE | flag, *b], a, phase)
        case b, [flag, *a] if flag in stage.values() and isinstance(flag, _flag):
            return _update_before_after(b, [*a, _phase | _flag.AFTER | flag], phase)

        # Ensure hook runs between before/after all
        case b, a if _phase | _flag.BEFORE | _flag.ALL not in [*b, *a]:
            _after = [*a, _phase | _flag.BEFORE | _flag.ALL]
            return _update_before_after(b, _after, phase)
        case b, a if _phase | _flag.AFTER | _flag.ALL not in [*b, *a]:
            _before = [*b, _phase | _flag.AFTER | _flag.ALL]
            return _update_before_after(_before, a, phase)

        case [[*b], [*a]]:
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
            self.before, self.after = _update_before_after(before, after, phase=when)
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
    graph: dict = _flag.graph()
    _insert_neighbor_stages(hooks)

    for hook in hooks:
        # Add the hook to the graph
        if hook.__name__ not in graph:
            graph[hook.__name__] = set()

        # Add the dependencies to the hook node
        graph[hook.__name__] |= {*hook.after}

        # Add the hook to the any node that depends on it, creating nodes as needed
        for dependency in hook.before:
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
