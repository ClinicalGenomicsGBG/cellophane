from pathlib import Path
from typing import Callable

from cellophane.testing import parametrize_from_yaml


@parametrize_from_yaml([Path(__file__).parent / "test_legacy.yaml"])
def test_integration(definition: dict, run_definition: Callable) -> None:
    run_definition(definition)
