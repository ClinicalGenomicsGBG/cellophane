"""Click related utilities for configuration."""

import re
from ast import literal_eval
from contextlib import suppress
from functools import partial
from pathlib import Path
from typing import (
    Any,
    Callable,
    Literal,
    Mapping,
    MutableMapping,
    Type,
    get_args,
    overload,
)

import rich_click as click
from humanfriendly import format_size, parse_size
from jsonschema._format import draft7_format_checker
from jsonschema.exceptions import FormatError

from cellophane import data, util

from .util import extract_parens

SCHEMA_TYPES = Literal[
    "string",
    "number",
    "integer",
    "boolean",
    "mapping",
    "array",
    "path",
    "size",
]

FORMATS = Literal[
    "color",
    "date",
    "date-time",
    "duration",
    "email",
    "hostname",
    "idn-hostname",
    "ipv4",
    "ipv6",
    "iri",
    "iri-reference",
    "json-pointer",
    "regex",
    "relative-json-pointer",
    "time",
    "uri",
    "uri-reference",
    "uri-template",
]


class InvertibleParamType(click.ParamType):
    """A custom Click parameter type for representing types that can be inverted back to a
    string representation.
    """

    def invert(self, value: Any) -> str:  # pragma: no cover
        """Inverts the value back to a string representation."""
        # Excluded from coverage as this is a stub method that should be overridden
        raise NotImplementedError


class StringMapping(InvertibleParamType):
    """Represents a click parameter type for comma-separated mappings.

    Attributes:
    ----------
        name (str): The name of the parameter type.
        scanner (re.Scanner): The regular expression scanner used for parsing mappings.

    Methods:
    -------
        convert(
            value: str | Mapping,
            param: click.Parameter | None,
            ctx: click.Context | None,
        ) -> Mapping | None:
            Converts the input value to a mapping.

    Args:
    ----
        value (str | Mapping): The input value to be converted.
        param (click.Parameter | None): The click parameter associated with the value.
        ctx (click.Context | None): The click context.

    Returns:
    -------
        Mapping | None: The converted mapping.

    Raises:
    ------
        click.BadParameter: When the input value is not a valid comma-separated mapping.

    Example:
    -------
        ```python
        mapping_type = StringMapping()
        value = "a=1, b=2, c=3"
        param = None
        ctx = None

        result = mapping_type.convert(value, param, ctx)
        print(result)  # Output: {'a': '1', 'b': '2', 'c': '3'}
        ```

    """

    name = "mapping"
    scanner = re.Scanner(  # type: ignore[attr-defined]
        [
            (r'"[^"]*"', lambda _, token: token[1:-1]),
            (r"'[^']*'", lambda _, token: token[1:-1]),
            (r"\(.*", lambda _, token: extract_parens(token)),
            (r"[\w.]+(?==)", lambda _, token: token.strip()),
            (r"(?<==)[^,]+", lambda _, token: token.strip()),
            (r"\s*[=,]\s*", lambda *_: None),
        ],
    )

    def convert(
        self,
        value: str | MutableMapping,
        param: click.Parameter | None,
        ctx: click.Context | None,
        fail: bool = True,
    ) -> data.PreservedDict:
        """Converts a string value to a mapping.

        This method takes a value and converts it to a mapping.
        If the value is a string, it is scanned and split into tokens.
        If the number of tokens is even, the tokens are paired up and
        converted into a dictionary.
        If the value is already a mapping and there are no extra tokens,
        it is returned as is. Otherwise, an error is raised.

        Args:
        ----
            value (str | Mapping): The value to be converted.
            param (click.Parameter | None): The click parameter
                associated with the value.
            ctx (click.Context | None): The click context associated with the value.
            fail (bool, optional): Whether to self.fail or raise an exception on error.

        Returns:
        -------
            Mapping | None: The converted mapping value.

        Raises:
        ------
            ValueError: Raised when the value is not a valid comma-separated mapping.

        Example:
        -------
            ```python
            converter = Converter()
            value = "{'a': 1, 'b': 2}"
            result = converter.convert(value, None, None)
            print(result)  # {'a': '1', 'b': '2'}
            ```

        """

        if isinstance(value, Mapping):
            return data.PreservedDict(value)

        try:
            tokens, extra = self.scanner.scan(value)
            if extra or len(tokens) % 2 != 0:
                raise ValueError
            parsed = data.PreservedDict(zip(tokens[::2], tokens[1::2]))
        except Exception:  # pylint: disable=broad-except
            if not fail:
                raise
            self.fail(f"Expected a mapping (a=b,x=y), got {value}", param, ctx)
        for k, v in parsed.items():
            with suppress(Exception):
                parsed[k] = literal_eval(v)
            with suppress(Exception):
                parsed[k] = self.convert(parsed[k], param, ctx, fail=False)
        while True:
            try:
                key: str = next(k for k in parsed if "." in k)
                parts = key.rsplit(".", maxsplit=1)
                if (subkey := parts[0]) in parsed:
                    parsed[subkey] |= {parts[1]: parsed.pop(key)}
                else:
                    parsed[subkey] = {parts[1]: parsed.pop(key)}
            except StopIteration:
                break

        return data.PreservedDict(parsed)

    def invert(self, value: dict) -> str:
        """Inverts the value back to a string representation.

        Args:
        ----
            value (Mapping): The value to be inverted.

        Returns:
        -------
            str: The inverted value.

        """
        if isinstance(value, str):
            return value
        _container = data.Container(value)
        _keys = util.map_nested_keys(value)
        _nodes: list[str] = [f"{'.'.join(k)}={repr(_container[k])}" for k in _keys]

        return ",".join(_nodes)


class TypedArray(InvertibleParamType):
    """A custom Click parameter type for representing typed arrays.

    Args:
    ----
        items (Literal["string", "number", "integer", "path"] | None):
            The type of items in the array. Defaults to "string".

    Raises:
    ------
        ValueError: If the provided items type is invalid.

    Returns:
    -------
        list: The converted list of values.

    Examples:
    --------
        >>> @click.command()
        ... @click.option("--values", type=TypedArray(items="number"))
        ... def process_values(values):
        ...     for value in values:
        ...         print(value)
        ...
        >>> process_values(["1", "2", "3"])
        1
        2
        3

    """

    name = "array"
    scanner = re.Scanner(  # type: ignore[attr-defined]
        [
            (r'"[^"]*"', lambda _, token: token),
            (r"'[^']*'", lambda _, token: token),
            (r"\([^)]+\)", lambda _, token: extract_parens(token)),
            (r"[^,]+", lambda _, token: token.strip()),
            (r"\s*[,]\s*", lambda *_: None),
        ],
    )
    items: dict

    def __init__(self, items: dict | None) -> None:
        self.items = items or {}
        if (items_type := self.items.get("type")) not in [
            *get_args(SCHEMA_TYPES),
            None,
        ]:
            raise ValueError(f"Invalid type: {items_type}")

    def convert(  # type: ignore[override]
        self,
        value: Any,
        param: click.Parameter | None,
        ctx: click.Context | None,
    ) -> list:
        """Converts a list of values using the specified item type.

        Args:
        ----
            value (list): The list of values to convert.
            param (click.Parameter): The Click parameter associated with the conversion.
            ctx (click.Context): The Click context.

        Returns:
        -------
            list: The converted list of values.

        Raises:
        ------
            Exception: If an error occurs during the conversion.

        Examples:
        --------
            >>> items = TypedArray(items="number")
            >>> items.convert(["1", "2", "3"], param, ctx)
            [1, 2, 3]

        """
        try:
            if isinstance(value, str):
                parsed, extra = self.scanner.scan(value)
                if parsed and extra:
                    raise ValueError(
                        f"Expected a comma separated array (a,b,x,y), got {value}"
                    )
                else:
                    parsed = parsed or [extra]

                for idx, v in enumerate(parsed):
                    with suppress(Exception):
                        parsed[idx] = literal_eval(v)

            elif isinstance(value, (list, tuple)):
                parsed = value
            else:
                parsed = [value]

        except Exception as exc:  # pylint: disable=broad-except
            self.fail(str(exc), param, ctx)

        if not self.items.get("type"):
            return parsed

        items_click_type: Callable = click_type(
            self.items.get("type", "string"),
            enum=self.items.get("enum"),
            items=self.items.get("items"),
            pattern=self.items.get("pattern"),
            format_=self.items.get("format"),
            min_=self.items.get("minimum"),
            max_=self.items.get("maximum"),
        )
        converter = (
            partial(items_click_type.convert, param=param, ctx=ctx)
            if isinstance(items_click_type, click.ParamType)
            else items_click_type
        )
        try:
            # NOTE: Mypy thinks that `converter` is not callable
            return [converter(v) for v in parsed]  # type: ignore[operator]
        except Exception as exc:  # pylint: disable=broad-except
            self.fail(f"Unable to convert value: {exc}", param, ctx)

    def invert(self, value: list) -> str:
        return value if isinstance(value, str) else ", ".join(repr(v) for v in value)

    def get_metavar(self, param: click.Parameter, ctx: click.Context | None = None) -> str | None:
        del param, ctx  # Unused
        metavar = f"{self.name.upper()}"
        if (items_type := self.items.get("type")) is not None:
            metavar += f"[{items_type}]"
        return metavar


class ParsedSize(InvertibleParamType):
    """Converts a string value representing a size to an integer.

    Args:
    ----
        value (str): The value to be converted.
        param (click.Parameter | None): The click parameter associated with the value.
        ctx (click.Context | None): The click context associated with the value.

    Returns:
    -------
        int: The converted integer value.

    Raises:
    ------
        ValueError: Raised when the value is not a valid integer.

    """

    name = "size"

    def convert(
        self,
        value: str | int,
        param: click.Parameter | None,
        ctx: click.Context | None,
    ) -> int:
        """Converts a string value to an integer.

        Args:
        ----
            value (str): The value to be converted.
            param (click.Parameter | None): The click parameter
                associated with the value.
            ctx (click.Context | None): The click context associated with the value.

        Returns:
        -------
            int: The converted integer value.

        Raises:
        ------
            ValueError: Raised when the value is not a valid integer.

        Example:
        -------
            ```python
            converter = Converter()
            value = "1"
            result = converter.convert(value, None, None)
            print(result)

        """
        try:
            return parse_size(str(value))
        except Exception as exc:  # pylint: disable=broad-except
            self.fail(str(exc), param, ctx)

    def invert(self, value: int) -> str:
        """Inverts the value back to a string representation.

        Args:
        ----
            value (int): The value to be inverted.

        Returns:
        -------
            str: The inverted value.

        """
        if isinstance(value, str):
            return value
        try:
            return format_size(value)
        except Exception:
            raise


class FormattedString(click.ParamType):
    """Click parameter type for formatted strings."""

    name = "string"
    format_: FORMATS | None = None
    pattern: str | None = None

    def __init__(
        self,
        format_: FORMATS | None = None,
        pattern: str | None = None,
    ) -> None:
        if format_ not in [*get_args(FORMATS), None]:
            raise ValueError(f"Invalid format: {format_}")
        self.format_ = format_
        self.pattern = pattern

    @overload
    def convert(
        self,
        value: str,
        param: click.Parameter | None,
        ctx: click.Context | None,
    ) -> str:  # pragma: no cover
        ...
    @overload
    def convert(
        self,
        value: None,
        param: click.Parameter | None,
        ctx: click.Context | None,
    ) -> None:  # pragma: no cover
        ...

    def convert(
        self,
        value: str | None,
        param: click.Parameter | None,
        ctx: click.Context | None,
    ) -> str | None:
        if value is None:
            return value
        _value = str(value)
        try:
            if self.format_ is not None:
                draft7_format_checker.check(_value, self.format_)
            if self.pattern is not None and not re.search(self.pattern, _value):
                raise FormatError(f"'{value}' does not match pattern '{self.pattern}'")
        except FormatError as exc:
            self.fail(exc.message, param, ctx)
        except Exception as exc:  # pylint: disable=broad-except
            # FIXME: Are any values not coercible to string?
            self.fail(f"Unable to convert '{value}' to string: {exc!r}", param, ctx)
        return _value

    def get_metavar(self, param: click.Parameter, ctx: click.Context | None = None) -> str | None:
        del param, ctx  # Unused
        metavar = f"{self.name.upper()}"
        if self.format_:
            metavar += f"[{self.format_}]"
        if self.pattern:
            metavar += f"({self.pattern})"
        return metavar


class ResilientIntRange(click.IntRange):
    """A resilient click.IntRange that can handle float values."""

    def convert(
        self,
        value: str | int | float,
        param: click.Parameter | None,
        ctx: click.Context | None,
    ) -> int:
        with suppress(Exception):
            value = float(value)
        return super().convert(value, param, ctx)


def click_type(  # type: ignore[return]
    type_: SCHEMA_TYPES | None = None,
    enum: list | None = None,
    items: dict | None = None,
    format_: FORMATS | None = None,
    pattern: str | None = None,
    min_: int | float | None = None,
    max_: int | float | None = None,
) -> (
    Type[bool]
    | click.Path
    | click.Choice
    | ResilientIntRange
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
    match type_:
        case _ if enum:
            return click.Choice(enum, case_sensitive=False)
        case "string":
            return FormattedString(format_, pattern)
        case "number":
            return click.FloatRange(min_, max_)
        case "integer":
            return ResilientIntRange(min_, max_)
        case "boolean":
            return bool
        case "mapping":
            return StringMapping()
        case "array":
            return TypedArray(items=items)
        case "path":
            return click.Path(path_type=Path)
        case "size":
            return ParsedSize()
        case _:
            return FormattedString(format_, pattern)
