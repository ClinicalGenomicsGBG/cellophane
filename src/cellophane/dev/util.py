"""Utility functions for cellophane dev command-line interface."""

import logging
import re
from contextlib import suppress
from pathlib import Path
from textwrap import dedent
from typing import Iterable, Literal

from git import GitCommandError, IndexFile, Repo
from questionary import Choice, checkbox, select
from rich.console import Console

from cellophane import CELLOPHANE_ROOT, Schema

from .exceptions import (
    InvalidModulesError,
    InvalidVersionsError,
    NoModulesError,
    NoVersionsError,
)
from .repo import ProjectRepo


def add_requirements(path: Path, module_path: Path) -> None:
    """Add module requirements to the global requirements file.

    Args:
    ----
      path (Path): The path to the root of the application.
      _module (str): The name of the module.

    """
    requirements_path = path / "modules" / "requirements.txt"
    module_path = path / "modules" / module_path.name

    if (
        module_path.is_dir()
        and (module_path / "requirements.txt").exists()
        and (spec := f"-r {module_path.name}/requirements.txt\n") not in requirements_path.read_text()
    ):
        with open(requirements_path, "a", encoding="utf-8") as handle:
            handle.write(spec)


def remove_requirements(path: Path, module_path: Path) -> None:
    """Remove a specific module's requirements from the project's requirements.txt file.

    Args:
    ----
      path (Path): The path to the project directory.
      _module (str): The name of the module to remove requirements for.

    """
    requirements_path = path / "modules" / "requirements.txt"

    if (spec := f"-r {module_path.name}/requirements.txt\n") in (requirements := requirements_path.read_text()):
        with open(requirements_path, "w", encoding="utf-8") as handle:
            handle.write(requirements.replace(spec, ""))


def update_example_config(path: Path) -> None:
    """Update the example configuration file.

    Args:
    ----
      path (Path): The path to the root of the application.

    """
    schema = Schema.from_file(
        path=[
            CELLOPHANE_ROOT / "schema.base.yaml",
            path / "schema.yaml",
            *(path / "modules").glob("**/schema.yaml"),
        ],
    )

    with open(path / "config.example.yaml", "w", encoding="utf-8") as handle:
        handle.write(schema.example_config)


def ask_modules(valid_modules: Iterable[str]) -> list[str]:
    """Ask the user to select one or more modules.

    Args:
    ----
      valid_modules (Sequence[str]): The valid modules to select from.

    """
    if not valid_modules:
        raise NoModulesError("No modules to select from")

    _modules = checkbox(
        "Select module(s)",
        choices=[Choice(title=module, value=module) for module in valid_modules],
        erase_when_done=True,
        validate=lambda x: len(x) > 0 or "Select at least one module",
    ).ask()
    Console().show_cursor()
    if not _modules:
        raise NoModulesError("No modules selected")

    return _modules


def ask_version(module_: str, valid_versions: Iterable[tuple[str, str]]) -> tuple[str, str]:
    """Ask the user to select a version for a module.

    Args:
    ----
      _module (str): The name of the module.
      modules_repo (ModulesRepo): The modules repository.

    """
    if not valid_versions:
        raise NoVersionsError(f"No compatible versions for module '{module_}'")

    _versions = select(
        f"Select version for {module_}",
        choices=[Choice(title=version, value=(tag, version)) for version, tag in valid_versions],
        erase_when_done=True,
    ).ask()
    Console().show_cursor()

    if not _versions:
        raise NoVersionsError("No version selected")

    return _versions


def add_version_tags(
    modules: list[tuple[str, str]] | list[tuple[str, None]] | None,
    valid_modules: set[str],
    repo: ProjectRepo,
    skip_version: bool = False,
) -> list[tuple[str, str | None, str | None]]:
    if modules is not None:
        if invalid_modules := {m for m, _ in modules} - valid_modules:
            raise InvalidModulesError([*invalid_modules])
        elif invalid_versions := {
            (module, version)
            for module, version in modules
            if version is not None and version != "latest" and version not in repo.external.modules[module]["versions"]
        }:
            raise InvalidVersionsError([*invalid_versions])

    versioned_modules = modules or [(module, None) for module in ask_modules(valid_modules)]
    result: list[tuple[str, str | None, str | None]] = []
    for module, version in versioned_modules:
        if skip_version:
            version, tag = None, None
        elif version is None:
            version, tag = ask_version(module, repo.compatible_versions(module))
        elif version == "latest":
            version = repo.external.modules[module].get("latest")
            if version is None:
                raise InvalidVersionsError((module, "latest"))
            tag = repo.external.modules[module]["versions"][version]["tag"]
        else:
            tag = repo.external.modules[module]["versions"][version]["tag"]

        result.append((module, version, tag))

    return result


def initialize_project(
    name: str,
    path: Path,
    modules_repo_url: str,
    modules_repo_branch: str,
    force: bool = False,
) -> ProjectRepo:
    """Initializes a new Cellophane repository with the specified name, path,
    and modules repository URL.

    Creates the necessary directories and files for the repository structure.
    The repository is then initialized,, and an initial commit is made.

    Args:
    ----
        name (str): The name of the repository.
        path (Path): The path where the repository will be initialized.
        modules_repo_url (str): The URL of the modules repository.
        force (bool | None): Whether to force initialization even if the path
            is not empty. Defaults to False.

    Returns:
    -------
        CellophaneRepo: An instance of the `CellophaneRepo` class representing the
            initialized repository.

    Raises:
    ------
        FileExistsError: Raised when the path is not empty and force is False.

    Example:
    -------
        ```python
        name = "my_awesome_repo"
        path = Path("/path/to/repo")
        modules_repo_url = "https://example.com/modules"
        repo = CellophaneRepo.initialize(name, path, modules_repo_url)

        # ./my_awesome_wrapper/
        # │
        # │   # Directory containing cellophane modules
        # ├── modules
        # │   ├── __init__.py
        # │   │
        # │   │   # Requirements file for the modules
        # │   └── requirements.txt
        # │
        # │   # Directory containing scripts to be submitted by Popen, SGE, etc.
        # ├── scripts
        # │   └── my_script.sh
        # │
        # │   # Directory containing misc. files used by the wrapper.
        # ├── scripts
        # │   └── some_more_data.txt
        # │
        # │   # Requirements file for the wrapper
        # ├── requirements.txt
        # │
        # │   # JSON Schema defining configuration options
        # ├── schema.yaml
        # │
        # │   # Main entrypoint for the wrapper
        # └── __main__.py
        # │
        # │   # Alternative entrypoint for the wrapper
        # └── my_awesome_wrapper.py
        ```

    """
    _prog_name = re.sub("\\W", "_", name)

    if [*path.glob("*")] and not force:
        raise FileExistsError(path)

    for subdir in (
        path / "modules",
        path / "scripts",
    ):
        subdir.mkdir(parents=True, exist_ok=force)

    for file in (
        path / "modules" / "__init__.py",
        path / "schema.yaml",
    ):
        file.touch(exist_ok=force)

    (path / "__main__.py").write_text(
        (CELLOPHANE_ROOT / "template" / "__main__.py")
        .read_text(encoding="utf-8")
        .format(label=name, prog_name=_prog_name),
    )

    (path / f"{_prog_name}.py").write_text(
        (CELLOPHANE_ROOT / "template" / "entrypoint.py")
        .read_text(encoding="utf-8")
        .format(label=name, prog_name=_prog_name),
    )

    (path / "requirements.txt").write_text(
        (CELLOPHANE_ROOT / "template" / "requirements.txt")
        .read_text(encoding="utf-8")
        .format(label=name, prog_name=_prog_name),
    )

    (path / ".gitignore").write_text(
        (CELLOPHANE_ROOT / "template" / ".gitignore")
        .read_text(encoding="utf-8")
        .format(label=name, prog_name=_prog_name),
    )

    (path / "modules" / "requirements.txt").write_text(
        (CELLOPHANE_ROOT / "template" / "modules" / "requirements.txt")
        .read_text(encoding="utf-8")
        .format(label=name, prog_name=_prog_name),
    )

    update_example_config(path)

    repo = Repo.init(str(path))
    index = repo.index
    index.add(
        [
            path / "modules" / "__init__.py",
            path / "modules" / "requirements.txt",
            path / "requirements.txt",
            path / "schema.yaml",
            path / "config.example.yaml",
            path / "__main__.py",
            path / f"{_prog_name}.py",
            path / ".gitignore",
        ],
    )
    index.write()
    index.commit("feat(cellophane): Initial commit from cellophane 🎉")

    return ProjectRepo(path, modules_repo_url, modules_repo_branch)


def drop_local_commits(
    repo: ProjectRepo,
    index: IndexFile,
    module_: str,
    logger: logging.LoggerAdapter,
) -> list[Literal["add", "update", "rm"]]:
    """Recompute the action to take based on local commits for a module.

    Remove all commits for the module not yet in upstream and recompute the action
    to take based on the module's current state. Detects no-op cases where the module
    remains the same as the last commit in upstream.

    Examples:
        The module was added and now removed
            -> No-op.
        The module was added and now updated
            -> Add with the new version.
        The module was removed and now added with the same version
            -> No-op
        The module was removed and now added with a different version
            -> Update with the new version

    Args:
    ----
        repo (ProjectRepo): The project repository.
        index (IndexFile): The index file for the repository.
        action (Literal["add", "update", "rm"]): The action to take.
        module_ (str): The name of the module.
        version (str): The version of the module.
        logger (logging.LoggerAdapter): The logger instance.

    Returns:
    -------
        Literal["add", "update", "rm"] | None: The recomputed action to take (or None for no-op).
    """
    previous_actions: list[Literal["add", "update", "rm"]] = []
    try:
        for commit in repo.module_commits(module_, local_only=True):
            current_head = repo.head.commit
            # Remove all commits for the module not yet in upstream
            repo.git.rebase(f"--onto={commit.hexsha}^", commit.hexsha)
            previous_actions.append(commit.trailers_dict["CellophaneModuleAction"][0])  # type: ignore[arg-type]
    except Exception as exc:
        # Revert to previous state if rebase fails
        logger.warning(f"Unable to remove previous commit '{commit.hexsha[:6]}' for '{module_}': {exc!r}")
        with suppress(GitCommandError):
            repo.git.rebase("--abort")
        index.reset(current_head, index=True, working_tree=True)

    return previous_actions


def rewrite_action(
    index: IndexFile,
    path: Path,
    previous_actions: list[Literal["add", "update", "rm"]],
    action: Literal["add", "update", "rm"],
) -> Literal["add", "update", "rm"] | None:
    """Rewrite the action to take based on the module's current state.

    Detects no-op cases where the module remains the same as HEAD.

    Args:
    ----
        index (IndexFile): The index file for the repository.
        module_path (Path): The path to the module.
        previous_commits (list[Commit]): The list of previous commits for the module.
        action (Literal["add", "update", "rm"]): The current requested action.

    Returns:
    -------
        Literal["add", "update", "rm"] | None: The recomputed action to take (or None for no-op).
    """
    # No changes compared to HEAD
    if previous_actions and not index.diff("HEAD", paths=path):
        return None
    # All commits for the module not yet in upstream were removed
    elif "add" in previous_actions and action == "update":
        # Change action to add as module was added and now updated
        return "add"
    elif "rm" in previous_actions and action == "add":
        # Check if module version changed between removal and addition
        # If version changed, change action to update
        # Otherwise, no-op as module was removed and now added
        return "update"

    return action


def commit_module_changes(
    index: IndexFile,
    module_: str,
    action: Literal["add", "update", "rm"],
    msg: str,
) -> None:
    """Commit changes to a module in the project repository.

    Args:
    ----
        index (IndexFile): The index file for the repository.
        module_ (str): The name of the module.
        action (Literal["add", "update", "rm"]): The action performed on the module.
        version (str): The version of the module.
        add_paths (Sequence[str]): The paths to add to the commit.
        logger (logging.LoggerAdapter): The logger instance.
    """

    index.add("config.example.yaml")
    index.add("modules/requirements.txt")
    index.write()

    _msg = f"""
        chore(cellophane): {msg}


        CellophaneModule: {module_}
        CellophaneModuleAction: {action}
    """
    index.commit(dedent(_msg).strip())
