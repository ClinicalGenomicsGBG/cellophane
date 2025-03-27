"""CLI for managing cellophane projects"""

import logging
from pathlib import Path
from typing import Literal

import rich_click as click

from cellophane import logs

from .exceptions import (
    InvalidModulesError,
    InvalidModulesRepoError,
    InvalidProjectRepoError,
    InvalidVersionsError,
    NoModulesError,
    NoVersionsError,
)
from .repo import ProjectRepo
from .util import (
    add_requirements,
    add_version_tags,
    commit_module_changes,
    drop_local_commits,
    initialize_project,
    remove_requirements,
    rewrite_action,
    update_example_config,
)


@click.group(
    context_settings={
        "help_option_names": ["-h", "--help"],
        "show_default": True,
    },
)
@click.option(
    "--modules-repo",
    "modules_repo_url",
    type=str,
    help="URL to the module repository",
    default="https://github.com/ClinicalGenomicsGBG/cellophane_modules",
)
@click.option(
    "--modules-branch",
    "modules_repo_branch",
    type=str,
    help="Branch to use for the module repository",
    default="main",
)
@click.option(
    "--path",
    type=click.Path(path_type=Path),
    help="Path to the cellophane project",
    default=Path(),
)
@click.option(
    "--log_level",
    type=str,
    help="Log level",
    default="INFO",
    callback=lambda ctx, param, value: value.upper(),
)
@click.pass_context
def main(
    ctx: click.Context,
    path: Path,
    log_level: str,
    modules_repo_url: str,
    modules_repo_branch: str,
) -> None:
    """Cellophane

    A library for writing modular wrappers
    """
    ctx.ensure_object(dict)
    logs.setup_console_handler().setLevel(log_level)

    ctx.obj["logger"] = logging.LoggerAdapter(logging.getLogger(), {"label": "cellophane"})
    ctx.obj["logger"].setLevel(log_level)
    ctx.obj["path"] = path
    ctx.obj["modules_repo_url"] = modules_repo_url
    ctx.obj["modules_repo_branch"] = modules_repo_branch


@main.command()
@click.argument(
    "command",
    metavar="COMMAND",
    type=click.Choice(["add", "rm", "update"]),
    required=True,
)
@click.argument(
    "modules",
    metavar="MODULE[@BRANCH] ...",
    callback=lambda ctx, param, module_strings: [
        tuple(m.split("@")) if "@" in m else (m, None) for m in module_strings
    ],
    nargs=-1,
)
@click.pass_context
def module(
    ctx: click.Context,
    command: Literal["add", "update", "rm"],
    modules: list[tuple[str, str]] | list[tuple[str, None]] | None,
) -> None:
    """Manage modules

    COMMAND: add|update|rm
    """
    ctx.ensure_object(dict)
    _logger: logging.LoggerAdapter = ctx.obj["logger"]
    _path: Path = ctx.obj["path"]

    try:
        _repo = ProjectRepo(
            _path,
            ctx.obj["modules_repo_url"],
            ctx.obj["modules_repo_branch"],
        )
    except (InvalidProjectRepoError, InvalidModulesRepoError) as exception:
        _logger.critical(exception, exc_info=True)
        raise SystemExit(1) from exception  # pylint: disable=bad-exception-cause

    if _repo.is_dirty():
        _logger.critical("Repository has uncommited changes")
        raise SystemExit(1)

    try:
        # add_or_update_modules_remote(_repo)
        module_action(repo=_repo, action=command, modules=modules, path=_path, logger=_logger)
    except NoModulesError as exc:
        _logger.warning(exc)
        raise SystemExit(1) from exc
    except (InvalidModulesError, InvalidVersionsError, NoVersionsError) as exc:
        _logger.critical(exc)
        raise SystemExit(1) from exc
    except Exception as exc:
        _logger.critical(
            f"Unhandled Exception: {exc!r}",
            exc_info=True,
        )
        raise SystemExit(1) from exc


def module_action(
    repo: ProjectRepo,
    action: Literal["add", "update", "rm"],
    modules: list[tuple[str, str]] | list[tuple[str, None]] | None,
    path: Path,
    logger: logging.LoggerAdapter,
) -> None:
    index = repo.index
    versioned_tagged_modules = add_version_tags(
        modules=modules,
        valid_modules=repo.modules if action != "add" else repo.absent_modules,
        repo=repo,
        skip_version=action == "rm",
    )
    for module, version, tag in versioned_tagged_modules:
        previous_head = repo.head.commit
        msg = {
            "add": f"Add module {module}@{version}",
            "update": f"Update module {module}->{version}",
            "rm": f"Remove module {module}",
        }
        try:
            previous_actions = drop_local_commits(repo, index, module, logger)
            index.remove(path / f"modules/{module}", working_tree=True, r=True, ignore_unmatch=True)
            remove_requirements(path, module)
            if action in ["add", "update"]:
                # Append the module name to the tag if it is not a valid tag
                _tag = tag if tag in [r.name for r in repo.tags] else f"modules/{tag}"
                _path = repo.external.modules[module]["path"]
                # Read the tree from the modules repository and add it to the 'modules' directory
                repo.git.read_tree(f"--prefix=modules/{module}/", "-u", f"{_tag}:{_path}")
            module_path = Path(repo.external.modules[module]["path"])
            new_action = rewrite_action(index, module_path, previous_actions, action)
            add_requirements(path, module)
            update_example_config(path)

        except Exception as exc:
            logger.error(f"{msg[action]} failed: {exc!r}", exc_info=True)
            repo.head.reset(previous_head, index=True, working_tree=True)
        else:
            logger.info(msg[action])
            if new_action is not None:
                commit_module_changes(
                    index=index,
                    module_=module,
                    action=new_action,
                    msg=msg[new_action],
                )
        finally:
            index.update()


@main.command()
@click.option(
    "--force",
    is_flag=True,
    help="Force initialization of non-empty directory",
    default=False,
)
@click.argument(
    "name",
    type=str,
)
@click.pass_context
def init(ctx: click.Context, name: str, force: bool) -> None:
    """Initialize a new cellophane project

    If no path is specified, the current directory will be used.
    If the path is not a git repository, it will be initialized as one.
    """
    path: Path = ctx.obj["path"]
    logger: logging.LoggerAdapter = ctx.obj["logger"]
    logger.info(f"Initializing new cellophane project at {path}")

    try:
        initialize_project(
            name=name,
            path=path,
            force=force,
            modules_repo_url=ctx.obj["modules_repo_url"],
            modules_repo_branch=ctx.obj["modules_repo_branch"],
        )
    except FileExistsError as exc:
        logger.critical("Project path is not empty (--force to ignore)")
        raise SystemExit(1) from exc
    except Exception as exc:
        logger.critical(f"Unhandled exception: {exc!r}", exc_info=True)
        raise SystemExit(1) from exc
