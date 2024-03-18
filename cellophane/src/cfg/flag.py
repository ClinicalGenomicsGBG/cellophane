"""Flag class for command-line options."""

from functools import partial
from typing import Any, Callable, Type, get_args

import rich_click as click
from attrs import define, field

from .click_ import (
    ITEMS_TYPES,
    SCHEMA_TYPES,
    InvertibleParamType,
    ParsedSize,
    StringMapping,
    TypedArray,
    click_type,
)


@define(slots=False)
class Flag:
    """
    Represents a flag used for command-line options.

    Attributes:
        key (list[str] | None): The key associated with the flag.
        type (
            Literal[
                "string",
                "number",
                "integer",
                "boolean",
                "mapping",
                "array",
                "path",
            ] | None
        ): The type of the flag.
        description (str | None): The description of the flag.
        default (Any): The default value of the flag.
        enum (list[Any] | None): The list of allowed values for the flag.
        required (bool): Indicates if the node is required.
        secret (bool): Determines if the value is hidden in the help section.

    Properties:
        required: Determines if the flag is required.
        pytype: Returns the Python type corresponding to the flag type.
        flag: Returns the flag name.
        click_option: Returns the click.option decorator for the flag.
        ```
    """

    type: SCHEMA_TYPES | None = field(default=None)
    items: ITEMS_TYPES | None = field(default=None)
    _key: list[str] | None = field(default=None)
    description: str | None = field(default=None)
    default: Any = field(default=None)
    value: Any = field(default=None)
    enum: list[Any] | None = field(default=None)
    required: bool = field(default=False)
    secret: bool = field(default=False)

    @type.validator
    def _type(self, attribute: str, value: str | None) -> None:
        del attribute  # Unused

        if value not in [*get_args(SCHEMA_TYPES), None]:
            raise ValueError(f"Invalid type: {value}")

    def convert(
        self,
        value: Any,
        ctx: click.Context | None = None,
        param: click.Parameter | None = None,
    ) -> Any:
        """
        Converts the value to the flag type.

        Args:
            value (Any): The value to be converted.
            ctx (click.Context | None): The click context.
            param (click.Parameter | None): The click parameter.

        Returns:
            Any: The converted value.
        """
        _converter: Callable
        if isinstance(self.click_type, click.ParamType):
            _converter = partial(self.click_type.convert, ctx=ctx, param=param)
        else:
            _converter = self.click_type

        try:
            return _converter(value)
        except TypeError:
            return value

    @property
    def key(self) -> list[str]:
        """
        Retrieves the key.

        Returns:
            list[str]: The key.

        Raises:
            ValueError: Raised when the key is not set.
        """
        if not self._key:
            raise ValueError("Key not set")
        return self._key

    @key.setter
    def key(self, value: list[str]) -> None:
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ValueError(f"Invalid key: {value}")

        self._key = value

    @property
    def click_type(
        self,
    ) -> Type | click.Path | click.Choice | StringMapping | TypedArray | ParsedSize:
        """
        Translate jsonschema type to Python type.

        Returns:
            type: The Python type corresponding to the property type.
        """
        return click_type(self.type, self.enum, self.items)

    @property
    def flag(self) -> str:
        """
        Constructs the flag name from the key.

        Raises:
            ValueError: Raised when the key is None.

        Returns:
            str: The flag name.
        """
        return "_".join(self.key)

    @property
    def no_flag(self) -> str:
        """
        Constructs the no-flag name from the key.

        Raises:
            ValueError: Raised when the key is None.

        Returns:
            str: The flag name.
        """
        return "_".join([*self.key[:-1], "no", self.key[-1]])

    @property
    def click_option(self) -> Callable:
        """
        Construct a click.option decorator from a Flag

        Returns:
            Callable: A click.option decorator
        """
        return click.option(
            (
                f"--{self.flag}/--{self.no_flag}"
                if self.type == "boolean"
                else f"--{self.flag}"
            ),
            type=self.click_type,
            default=(
                True
                if self.type == "boolean" and self.default is None
                else self.value or self.default
            ),
            required=self.required,
            help=self.description,
            show_default=(
                False
                if self.secret
                else (
                    self.click_type.invert(default)
                    if (default := self.value or self.default)
                    and isinstance(self.click_type, InvertibleParamType)
                    else str(default)
                )
            ),
        )
