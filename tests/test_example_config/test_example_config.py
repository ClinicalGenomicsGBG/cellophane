from pathlib import Path

from cellophane.cfg import Schema
from pytest import mark, param
from ruamel.yaml import YAML

yaml = YAML()


class Test:
    schemata: list[Path] = [*(Path(__file__).parent / "schemata").rglob("*.yaml")]

    @mark.parametrize("definition", (param(yaml.load(f), id=f.name) for f in schemata))
    def test(self, definition: dict) -> None:
        schema: Schema = Schema(definition.get("schema", {}))
        assert schema.example_config == definition.get("expected", "")
