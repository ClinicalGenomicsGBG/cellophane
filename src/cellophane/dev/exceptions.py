"""Exceptions for the cellophane dev command-line interface."""
from __future__ import annotations

from typing import TYPE_CHECKING

from git import InvalidGitRepositoryError

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any



class InvalidModulesError(Exception):
    """Exception raised when a module is not valid.

    Args:
    ----
        _module (str | tuple[str]): The names of the module.
        msg (str | None): The error message (default: None).

    """

    def __init__(self, modules: str | list[str], msg: str | None = None):
        _modules = modules if isinstance(modules, list) else [modules]
        self.modules = _modules
        _msg = "\n".join(f"Module '{module}' is not valid" for module in _modules)
        super().__init__(msg or _msg)


class InvalidVersionsError(Exception):
    """Exception raised when a module is not valid.

    Args:
    ----
        _module (str): The name of the module.
        branch (str): The name of the branch.
        msg (str | None): The error message (default: None).

    """

    def __init__(self, versioned_modules: tuple[str, str] | list[tuple[str, str]]) -> None:
        _versioned_modules = versioned_modules if isinstance(versioned_modules, list) else [versioned_modules]
        self.modules = _versioned_modules
        _msg = "\n".join(
            f"Version '{version}' is invalid for module '{module}'" for module, version in _versioned_modules
        )
        super().__init__(_msg)


class NoModulesError(Exception):
    """Exception raised when there are no modules to select from."""

    def __init__(self, msg: str | None = None) -> None:
        super().__init__(msg)


class NoVersionsError(Exception):
    """Exception raised when there are no versions to select from."""

    def __init__(self, msg: str | None = None) -> None:
        super().__init__(msg)


class InvalidModulesRepoError(InvalidGitRepositoryError):
    """Exception raised when the modules repository is invalid.

    Args:
    ----
        url (str): The URL of the invalid modules repository.
        *args: Additional positional arguments passed to InvalidGitRepositoryError.
        msg (str | None): The error message (default: None).
        **kwargs: Additional keyword arguments passed to InvalidGitRepositoryError.

    """

    def __init__(
        self,
        url: str,
        *args: Any,
        msg: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            msg or f"Invalid cellophane modules repository '{url}'",
            *args,
            **kwargs,
        )


class InvalidProjectRepoError(InvalidGitRepositoryError):
    """Exception raised when the project repository is invalid.

    Args:
    ----
        path (Path | str): The project root path.
        *args: Additional positional arguments passed to InvalidGitRepositoryError.
        msg (str | None): The error message (default: None).
        **kwargs: Additional keyword arguments passed to InvalidGitRepositoryError.

    """

    def __init__(
        self,
        path: Path | str,
        *args: Any,
        msg: str | None = None,
        **kwargs: Any,
    ):
        super().__init__(
            msg or f"Invalid cellophane project repository '{path}'",
            *args,
            **kwargs,
        )
