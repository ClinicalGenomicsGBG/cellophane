from cellophane.testing import BaseTest, Invocation, literal, regex
from click import BadParameter
from jsonschema import ValidationError
from pytest import mark


class Test_schemata(BaseTest):
    args = ["--workdir", "out"]

    @mark.override(
        structure={"schema.yaml": "!INVALID!"},
    )
    def test_invalid_schema(self, invocation: Invocation) -> None:
        assert invocation.logs == regex(r"Failed to load schema")
        assert invocation.exit_code != 0

    @mark.override(
        structure={"schema.yaml": "properties: {a: {type: object}}"},
    )
    def test_object_no_properties(self, invocation: Invocation) -> None:
        assert isinstance(invocation.exception, ValidationError)
        assert (
            "Invalid schema: node 'a' has type 'object' but no properties."
            in invocation.exception.args
        )
        assert invocation.exit_code != 0

    @mark.override(
        structure={"schema.yaml": "properties: {a: {type: INVALID}}"},
    )
    def test_invalid_type(self, invocation: Invocation) -> None:
        assert isinstance(invocation.exception, ValueError)
        assert "Invalid type: INVALID" in invocation.exception.args
        assert invocation.exit_code != 0

    @mark.override(
        structure={"schema.yaml": "properties: {a: {type: number}}"},
        args=[*args, "--a", "INVALID"],
    )
    def test_bad_type_cli(self, invocation: Invocation) -> None:
        assert isinstance(invocation.exception, BadParameter)
        assert "'INVALID' is not a valid float range." in invocation.exception.args
        assert invocation.exit_code != 0

    @mark.override(
        structure={
            "schema.yaml": "properties: {a: {type: number}}",
            "config.yaml": "a: INVALID",
        },
        args=[*args, "--config_file", "config.yaml"],
    )
    def test_bad_type_config(self, invocation: Invocation) -> None:
        assert isinstance(invocation.exception, BadParameter)
        assert (
            "'INVALID' is not a valid float range." in invocation.exception.args
        )
        assert invocation.exit_code != 0

    @mark.override(
        structure={
            "schema.yaml": "properties: {a: {type: number, default: INVALID}}",
        },
    )
    def test_bad_type_default(self, invocation: Invocation) -> None:
        assert isinstance(invocation.exception, ValidationError)
        assert "Invalid default value 'INVALID' for 'a'" in invocation.exception.args
        assert invocation.exit_code != 0

    @mark.override(
        structure={"schema.yaml": "properties: {a: {type: number}}"},
        args=[*args, "--a", "1.0"],
    )
    def test_type(self, invocation: Invocation) -> None:
        assert invocation.exit_code == 0

    @mark.override(
        structure={"schema.yaml": "properties: {a: {type: string, format: INVALID}}"},
    )
    def test_invalid_format(self, invocation: Invocation) -> None:
        assert isinstance(invocation.exception, ValueError)
        assert "Invalid format: INVALID" in invocation.exception.args
        assert invocation.exit_code != 0

    @mark.override(
        structure={"schema.yaml": "properties: {a: {type: string, format: email}}"},
        args=[*args, "--a INVALID"],
    )
    def test_bad_format(self, invocation: Invocation) -> None:
        assert isinstance(invocation.exception, BadParameter)
        assert "'INVALID' is not a 'email'" in invocation.exception.args
        assert invocation.exit_code != 0

    @mark.override(
        structure={"schema.yaml": "properties: {a: {type: string, format: email}}"},
        args=[*args, "--a VALID@TEST.com"],
    )
    def test_format(self, invocation: Invocation) -> None:
        assert invocation.exit_code == 0

    @mark.override(
        structure={"schema.yaml": "properties: {a: {type: mapping}}"},
        args=[*args, "--a INVALID"],
    )
    def test_bad_mapping(self, invocation: Invocation) -> None:
        assert isinstance(invocation.exception, BadParameter)
        assert (
            "Expected a mapping (a=b,x=y), got INVALID" in invocation.exception.args
        )
        assert invocation.exit_code != 0

    @mark.override(
        structure={"schema.yaml": "properties: {a: {type: mapping}}"},
        args=[*args, "--a 1337"],
    )
    def test_not_a_mapping(self, invocation: Invocation) -> None:
        assert isinstance(invocation.exception, BadParameter)
        assert "Expected a mapping (a=b,x=y), got 1337" in invocation.exception.args
        assert invocation.exit_code != 0

    @mark.override(
        structure={"schema.yaml": "properties: {a: {type: mapping}}"},
        args=[*args, '--a foo=bar,baz=qux'],
    )
    def test_mapping(self, invocation: Invocation) -> None:
        assert invocation.exit_code == 0

    @mark.override(
        structure={
            "schema.yaml": "properties: {a: {type: array, items: {type: INVALID}}}"
        },
    )
    def test_invalid_array_item_type(self, invocation: Invocation) -> None:
        assert isinstance(invocation.exception, ValueError)
        assert "Invalid type: INVALID" in invocation.exception.args
        assert invocation.exit_code != 0

    @mark.override(
        structure={
            "schema.yaml": "properties: {a: {type: array, items: {type: number}}}"
        },
        args=[*args, "--a 1337,INVALID"],
    )
    def test_bad_array_item_type(self, invocation: Invocation) -> None:
        assert isinstance(invocation.exception, BadParameter)
        assert (
            "Unable to convert value: 'INVALID' is not a valid float range."
            in invocation.exception.args
        )
        assert invocation.exit_code != 0

    @mark.override(
        structure={"schema.yaml": "properties: {a: {type: size}}"},
        args=[*args, "--a", "INVALID"],
    )
    def test_bad_size(self, invocation: Invocation) -> None:
        assert isinstance(invocation.exception, BadParameter)
        assert (
            "Failed to parse size! (input 'INVALID' was tokenized as ['INVALID'])"
            in invocation.exception.args
        )
        assert invocation.exit_code != 0

    @mark.override(
        structure={"schema.yaml": "properties: {a: {pattern: '^FOO$'}}"},
        args=[*args, "--a", "INVALID"],
    )
    def test_bad_pattern(self, invocation: Invocation) -> None:
        assert isinstance(invocation.exception, BadParameter)
        assert "'INVALID' does not match pattern '^FOO$'" in invocation.exception.args
        assert invocation.exit_code != 0


class Test_parse_config(BaseTest):
    structure = {
        "modules/echo.py": """
            from cellophane import modules, data, util
            from typing import Mapping

            def describe_type(value):
                if isinstance(value, Mapping):
                    mapping_type = type(value).__name__
                    key_types = sorted({describe_type(k) for k in value.keys()})
                    value_types = sorted({describe_type(v) for v in value.values()})
                    return f"{mapping_type}[{'|'.join(key_types)},{'|'.join(value_types)}]"
                elif isinstance(value, list):
                    list_type = type(value).__name__
                    item_types = sorted({describe_type(i) for i in value})
                    return f"{list_type}[{'|'.join(item_types)}]"
                else:
                    return type(value).__name__

            @modules.pre_hook()
            def echo_config(config, logger, **_):
                for base_key, value in config.items():
                    value_type = describe_type(value)
                    if isinstance(value, data.Container):
                        for sub_key in util.map_nested_keys(data.as_dict(value)):
                            full_key = ".".join([base_key, *sub_key])
                            sub_value = value[*sub_key]
                            sub_value_type = describe_type(sub_value)
                            logger.info(f"{full_key}: {sub_value_type} = {sub_value!r}")
                    elif isinstance(value, Mapping):
                        logger.info(f"{base_key}: {value_type} = {value!r}")
                    elif isinstance(value, list):
                        logger.info(f"{base_key}: {value_type} = {value!r}")
                    else:
                        logger.info(f"{base_key}: {value_type} = {value!r}")
        """,
        "schema.yaml": """
            properties:
                string:
                  type: string
                mIxEdCaSe:
                  type: string
                patterned_string:
                  type: string
                  pattern: "^FOO$"
                formatted_string:
                  type: string
                  format: email
                override:
                  type: string
                number:
                  type: number
                number_range:
                  type: number
                  minimum: 0
                  maximum: 10
                integer:
                  type: integer
                integer_range:
                  type: integer
                  minimum: 0
                  maximum: 10
                boolean:
                  type: object
                  properties:
                    b:
                      type: boolean
                    a:
                      type: boolean
                array:
                  type: array
                typed_array:
                  type: array
                  items:
                    type: number
                nested_array:
                  type: array
                  items:
                    type: array
                    items:
                      type: integer
                mapping_array:
                  type: array
                  items:
                    type: mapping
                mapping:
                  type: mapping
                path:
                  type: path
                size:
                  type: size
                ne:
                  type: object
                  properties:
                    st:
                      type: object
                      properties:
                        ed:
                          type: string
                no_type:
                  default: "DEFAULT"
        """,
    }

    args = ["--workdir", "out"]

    @mark.override(
        args=[*args, "--help"],
    )
    def test_help(self, invocation: Invocation) -> None:
        # FIXME: Checking the help text is non-trivial as it will vary based on the width
        # of the terminal. This tends to cause false failures on GitHub Actions.
        assert invocation.exit_code == 0

    @mark.override(
        structure={
            **structure,
            "config.yaml": """
                string: "string"
                patterned_string: "FOO"
                formatted_string: "DUMMY@TEST.com"
                override: "CONFIG"
                number: 1.0
                integer: 1
                mIxEdCaSe: "MiXeDcAsE"
                boolean:
                  a: true
                  b: false
                array: [1.0, "3", "3.0", 7]
                typed_array: [1.0, "3", "3.0", 7]
                nested_array:
                - ["1", 2, "3", "4"]
                - [5, 6, 7, 8]
                mapping_array:
                - {a: "a"}
                - {b: {c: {d: "d"}}}
                mapping:
                  a: "a"
                  b: 1
                  c: 1.0
                  d:
                    e: "e"
                    f: 42
                path: "path/to/file"
                size: 1 GB
                ne: {st: {ed: "value"}}
            """,
        },
        args=[
            *args,
            "--override CLI",
            "--config_file config.yaml",
        ],
    )
    def test_parse_config_file(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            "string: str = 'string'",
            "patterned_string: str = 'FOO'",
            "formatted_string: str = 'DUMMY@TEST.com'",
            "override: str = 'CLI'",
            "number: float = 1.0",
            "integer: int = 1",
            "mIxEdCaSe: str = 'MiXeDcAsE'",
            "boolean.a: bool = True",
            "boolean.b: bool = False",
            "typed_array: list[float] = [1.0, 3.0, 3.0, 7.0]",
            "nested_array: list[list[int]] = [[1, 2, 3, 4], [5, 6, 7, 8]]",
            "array: list[float|int|str] = [1.0, '3', '3.0', 7]",
            "mapping_array: list[PreservedDict[str,dict[str,dict[str,str]]]|PreservedDict[str,str]] = [{'a': 'a'}, {'b': {'c': {'d': 'd'}}}]",
            "mapping: PreservedDict[str,dict[str,int|str]|float|int|str] = {'a': 'a', 'b': 1, 'c': 1.0, 'd': {'e': 'e', 'f': 42}}",
            "path: PosixPath = PosixPath('path/to/file')",
            "size: int = 1000000000",
            "ne.st.ed: str = 'value'",
            "no_type: str = 'DEFAULT'",
        )

    @mark.override(
        args=[
            *args,
            "--string string",
            "--patterned_string FOO",
            "--formatted_string DUMMY@TEST.com",
            "--override CLI",
            "--number 1.0",
            "--integer 1",
            "--mIxEdCaSe MiXeDcAsE",
            "--boolean_a",
            "--boolean_no_b",
            "--array '1.0,\"3\",\"3.0\",7'",
            "--typed_array '1.0,\"3\",\"3.0\",7'",
            "--nested_array '(\"1\",2,\"3\",4),(5,6,7,8)'",
            "--mapping_array (a=a),b=(c=(d=d))",
            "--mapping a=a,b=1,c=1.0,d=(e=e,f=42)",
            "--path 'path/to/file'",
            "--size '1 GB'",
            "--ne_st_ed value",
        ],
    )
    def test_parse_flags(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            "string: str = 'string'",
            "patterned_string: str = 'FOO'",
            "formatted_string: str = 'DUMMY@TEST.com'",
            "override: str = 'CLI'",
            "number: float = 1.0",
            "integer: int = 1",
            "mIxEdCaSe: str = 'MiXeDcAsE'",
            "boolean.a: bool = True",
            "boolean.b: bool = False",
            "typed_array: list[float] = [1.0, 3.0, 3.0, 7.0]",
            "nested_array: list[list[int]] = [[1, 2, 3, 4], [5, 6, 7, 8]]",
            "array: list[float|int|str] = [1.0, '3', '3.0', 7]",
            "path: PosixPath = PosixPath('path/to/file')",
            "size: int = 1000000000",
            "ne.st.ed: str = 'value'",
            "no_type: str = 'DEFAULT'",
        )
        assert invocation.logs == regex(
            r"mapping_array: .* = \[{'a': 'a'}, {'b': {'c': {'d': 'd'}}}\]",
            r"mapping: .* = {'a': 'a', 'b': 1, 'c': 1.0, 'd': {'e': 'e', 'f': 42}}"
        )

    @mark.override(
        structure={
            **structure,
            "schema.yaml": """
            properties:
              value_a:
                type: string
                default: "DEFAULT_A"
              value_b:
                type: integer
                default: 0
              value_c:
                type: number
                default: 0.0
              list:
                type: array
                items:
                  type: string
              nested:
                type: object
                properties:
                  shallow_node:
                    type: mapping
                  deep:
                    type: object
                    properties:
                      str_node:
                        type: string
                      list_node:
                        type: array
                        items:
                          type: string
            """,
            "path/to/config.yaml": """
                !include:include_a.yaml,include_b.yaml
                nested:
                  shallow_node: !include:include_d.yaml
            """,
            "path/to/include_a.yaml": """
                value_a: "A"
                list: ["x", "y"]
            """,
            "path/to/include_b.yaml": """
                !include:include_c.yaml
                value_b: 42
                list: ["y", "z"]
                nested:
                  deep:
                    list_node: ["y", "z"]
            """,
            "path/to/include_c.yaml": """
                value_c: 13.37
                nested:
                  deep:
                    str_node: "deep_value"
                    list_node: ["x", "y"]
            """,
            "path/to/include_d.yaml": """
                some: "body"
                once: "told me"
            """,
        },
        args=[
            *args,
            "--config_file path/to/config.yaml",
        ],
    )
    def test_parse_config_file_include(self, invocation: Invocation) -> None:
        assert invocation.logs == literal(
            "value_a: str = 'A'",
            "value_b: int = 42",
            "value_c: float = 13.37",
            "list: list[str] = ['x', 'y', 'z']",
            "nested.shallow_node.some: str = 'body'",
            "nested.shallow_node.once: str = 'told me'",
            "nested.deep.str_node: str = 'deep_value'",
            "nested.deep.list_node: list[str] = ['x', 'y', 'z']",
        )
