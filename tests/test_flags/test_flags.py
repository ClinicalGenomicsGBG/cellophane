from pathlib import Path

from cellophane.cfg import Flag, Schema, get_flags
from pytest import mark, param
from ruamel.yaml import YAML

yaml = YAML()


class Test_flags:
    schemata: list[Path] = [*(Path(__file__).parent / "schemata").rglob("*.yaml")]

    @mark.parametrize("definition", (param(yaml.load(f), id=f.name) for f in schemata))
    def test_flags(self, definition: dict) -> None:
        schema = Schema(definition.get("schema", {}))

        for expected in definition["expected"]:
            config = expected.get("config", {})
            flags = get_flags(schema, config)
            expected = [Flag(**flag) for flag in expected.get("flags", [])]
            assert flags == expected, f"{config=}"
