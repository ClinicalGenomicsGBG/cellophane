"""Miscellaneous utility functions."""
from __future__ import annotations

from logging import CRITICAL, root
from typing import TYPE_CHECKING, ParamSpec, Protocol, TypeVar

from attrs import define, field

if TYPE_CHECKING:
    from logging import Handler, Logger
    from typing import Any


def is_instance_or_subclass(obj: Any, class_or_tuple: type | tuple[type, ...]) -> bool:
    """Checks if an object is an instance of or a subclass of a class.

    Args:
    ----
        obj (Any): The object to check.
        cls (type): The class to check against.

    Returns:
    -------
        bool: True if the object is an instance of or a subclass of the class,
            False otherwise.

    Example:
    -------
        ```python
        is_instance_or_subclass(1, int)  # True
        is_instance_or_subclass(1.0, int)  # False
        is_instance_or_subclass(int, int)  # True
        is_instance_or_subclass(int, object)  # True
        ```

    """
    if not isinstance(obj, type):
        return isinstance(obj, class_or_tuple)

    _tuple = (class_or_tuple,) if isinstance(class_or_tuple, type) else class_or_tuple
    return issubclass(obj, _tuple) and all(obj != cls for cls in _tuple)


@define
class freeze_logs:
    """Context manager to suppress logging output.

    Example:
    -------
        ```python
        with freeze_logs():
            logging.info("This will not be printed")
        ```

    """

    logger: Logger = field(default=root)
    original_handlers: set[Handler] = field(factory=set)
    original_level: int = field(default=CRITICAL)

    def __enter__(self) -> None:
        self.original_level = self.logger.level
        self.original_handlers = {*self.logger.handlers}
        self.logger.setLevel(CRITICAL + 1)

    def __exit__(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs  # Unused
        for handler in {*self.logger.handlers} ^ self.original_handlers:
            handler.close()
            self.logger.removeHandler(handler)
        self.logger.setLevel(self.original_level)


P = ParamSpec("P")
R = TypeVar("R", covariant=True)
class NamedCallable(Protocol[P, R]):
    __name__: str
    __qualname__: str
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R: ...  # type: ignore[misc]
