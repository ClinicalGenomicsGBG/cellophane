"""Configuration object based on a schema."""

from typing import Any

from attrs import define, field

from cellophane import data

from .schema import Schema


@define(init=False, slots=False)
class Config(data.Container):
    """Represents a configuration object based on a schema.

    Attributes:
    ----------
        __schema__ (Schema): The schema associated with the configuration.

    Methods:
    -------
        __init__(
            schema: Schema,
            _data: dict | None = None,
            **kwargs,
        ):
            Initializes the Config object with the given schema and data.

    Args:
    ----
        schema (Schema): The schema associated with the configuration.
        _data (dict | None, optional): The data for the configuration. Defaults to None.
        **kwargs: Additional keyword arguments for the configuration.

    Example:
    -------
        ```python
        schema = Schema()
        config = Config(schema)

        # Creating a configuration from a file
        path = "config.yaml"
        config = Config.from_file(path, schema)
        ```

    """

    __schema__: Schema = field(repr=False, factory=Schema, init=False)

    def __init__(
        self,
        schema: Schema,
        _data: dict | None = None,
        **kwargs: Any,
    ) -> None:
        self.__schema__ = schema
        super().__init__(_data=_data, **kwargs)