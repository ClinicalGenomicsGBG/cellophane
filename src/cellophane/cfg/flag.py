"""Flag class for command-line options."""

from functools import partial
from typing import Any, Callable, Iterable, SupportsFloat, Type, get_args

import rich_click as click
from attrs import define, field, setters

from .click_ import (
    FORMATS,
    SCHEMA_TYPES,
    FormattedString,
    InvertibleParamType,
    ParsedSize,
    StringMapping,
    TypedArray,
    click_type,
)


def _convert_float(value: SupportsFloat | None) -> float | None:
    return float(value) if value is not None else None


def _convert_tuple(value: Iterable) -> tuple[str, ...]:
    return tuple(value)


@define(slots=False)
class Flag:
    """Represents a flag used for command-line options.

    Attributes
    ----------
        key (list[str] | None): The key associated with the flag.
        type SCHEMA_TYPES: The JSONSchema type of the flag.
        items SCHEMA_TYPES: The JSONSchema items type of the flag.
        format_ FORMATS: The JSONSchema format of the flag.
        minimum (int | None): The minimum value of the flag.
        maximum (int | None): The maximum value of the flag.
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

    key: tuple[str, ...] = field(converter=_convert_tuple, on_setattr=setters.convert)
    type: SCHEMA_TYPES | None = field(default=None)
    items: dict | None = field(default=None)
    min: int | None = field(
        default=None,
        converter=_convert_float,
        on_setattr=setters.convert,
    )
    max: int | None = field(
        default=None,
        converter=_convert_float,
        on_setattr=setters.convert,
    )
    format: FORMATS | None = field(default=None)
    pattern: str | None = field(default=None)
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
        """Converts the value to the flag type.

        Args:
        ----
            value (Any): The value to be converted.
            ctx (click.Context | None): The click context.
            param (click.Parameter | None): The click parameter.

        Returns:
        -------
            Any: The converted value.

        """
        _converter: Callable
        if isinstance(self.click_type, click.ParamType):
            _converter = partial(self.click_type.convert, ctx=ctx, param=param)
        else:
            _converter = self.click_type

        return _converter(value)

    @property
    def click_type(
        self,
    ) -> (
        Type
        | click.Path
        | click.Choice
        | click.IntRange
        | click.FloatRange
        | StringMapping
        | TypedArray
        | ParsedSize
        | FormattedString
    ):
        """Translate jsonschema type to Python type.

        Returns
        -------
            type: The Python type corresponding to the property type.

        """
        return click_type(
            type_=self.type,
            format_=self.format,
            pattern=self.pattern,
            min_=self.min,
            max_=self.max,
            enum=self.enum,
            items=self.items,
        )

    @property
    def flag(self) -> str:
        """Constructs the flag name from the key.

        Raises
        ------
            ValueError: Raised when the key is None.

        Returns
        -------
            str: The flag name.

        """
        return "_".join(self.key)

    @property
    def no_flag(self) -> str:
        """Constructs the no-flag name from the key.

        Raises
        ------
            ValueError: Raised when the key is None.

        Returns
        -------
            str: The flag name.

        """
        return "_".join([*self.key[:-1], "no", self.key[-1]])

    @property
    def click_option(self) -> Callable:
        """Construct a click.option decorator from a Flag

        Returns
        -------
            Callable: A click.option decorator

        """

        type_ = self.click_type
        default = self.default if self.value is None else self.value
        return click.option(
            (
                f"--{self.flag}/--{self.no_flag}"
                if self.type == "boolean"
                else f"--{self.flag}"
            ),
            self.flag,
            type=type_,
            default=True if self.type == "boolean" and default is None else default,
            required=self.required,
            help=self.description,
            show_default=(
                (self.secret or default is None)
                or (
                    type_.invert(default)  # type: ignore[arg-type]
                    if default and isinstance(type_, InvertibleParamType)
                    else str(default)
                )
            ),
        )

    @property
    def dummy_click_option(self) -> Callable:
        """Construct a barebones click.option decorator from a Flag"

        Only specifies the flag name and type, without any additional options.

        Returns
        -------
            Callable: A click.option decorator
        """
        return click.option(
            (
                f"--{self.flag}/--{self.no_flag}"
                if self.type == "boolean"
                else f"--{self.flag}"
            ),
            type=bool if self.type == "boolean" else None,
        )