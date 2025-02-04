"""Module loader for cellophane modules."""

import asyncio as aio
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from site import addsitedir

from cellophane.data import Sample, Samples
from cellophane.executors import Executor, MockExecutor, SubprocessExecutor
from cellophane.util import freeze_logs, is_instance_or_subclass

from .hook import Hook, resolve_dependencies
from .runner_ import Runner

MODULE_CONTENTS = tuple[
    list[Hook],
    list[Runner],
    list[type[Sample]],
    list[type[Samples]],
    list[type[Executor]],
]


async def _async_load(file: Path) -> MODULE_CONTENTS:
    hooks: list[Hook] = []
    runners: list[Runner] = []
    sample_mixins: list[type[Sample]] = []
    samples_mixins: list[type[Samples]] = []
    executors_: list[type[Executor]] = []

    try:
        if (
            (base := (file.stem if file.stem != "__init__" else file.parent.name))
            and (spec := spec_from_file_location(f"modules.{base}", file)) is not None
            and (module := module_from_spec(spec)) is not None
            and (loader := spec.loader) is not None
        ):
            sys.modules[f"modules.{base}"] = module
            loader.exec_module(module)
    except Exception as exc:
        raise ImportError(f"Unable to import module '{base}': {exc!r}") from exc

    for obj in [getattr(module, a) for a in dir(module)]:
        if is_instance_or_subclass(obj, Hook):
            hooks.append(obj)
        elif is_instance_or_subclass(obj, Sample):
            sample_mixins.append(obj)
        elif is_instance_or_subclass(obj, Samples):
            samples_mixins.append(obj)
        elif is_instance_or_subclass(obj, Runner):
            runners.append(obj)
        elif is_instance_or_subclass(obj, Executor):
            executors_.append(obj)

    return hooks, runners, sample_mixins, samples_mixins, executors_


async def _gather_module_contents(root: Path) -> MODULE_CONTENTS:
    futures = [
        aio.create_task(_async_load(file))
        for file in [
            *(root / "modules").glob("*.py"),
            *(root / "modules").glob("*/__init__.py"),
        ]
        if file != (root / "modules" / "__init__.py")
    ]
    results: MODULE_CONTENTS = ([], [], [], [], [SubprocessExecutor, MockExecutor])
    for future in aio.as_completed(futures):
        result = await future
        for i, r in enumerate(result):
            results[i].extend(r)  # type: ignore[arg-type]
    return results


def load(root: Path) -> MODULE_CONTENTS:
    """Loads module(s) from the specified path and returns the hooks, runners,
    sample mixins, and samples mixins found within.

    Args:
    ----
        path (Path): The path to the directory containing the modules.

    Returns:
    -------
        tuple[
            list[Hook],
            list[Runner],
            list[type[data.Sample]],
            list[type[data.Samples]],
        ]: A tuple containing the lists of hooks, runners, sample mixins,
            and samples mixins.

    """
    addsitedir(str(root))
    with freeze_logs():
        (
            hooks,
            runners,
            sample_mixins,
            samples_mixins,
            executors_,
        ) = aio.run(_gather_module_contents(root))
    try:
        hooks = resolve_dependencies(hooks)
    except Exception as exc:  # pylint: disable=broad-except
        raise ImportError(f"Unable to resolve hook dependencies: {exc!r}") from exc

    return hooks, runners, sample_mixins, samples_mixins, executors_
