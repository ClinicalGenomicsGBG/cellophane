import logging
from pathlib import Path
from typing import Callable, Iterator
from warnings import warn

import pytest
from click.testing import CliRunner
from pytest_mock import MockerFixture
from pytest_subprocess import FakeProcess
from ruamel.yaml import YAML

from .invocation import Invocation
from .util import literal

_YAML = YAML(typ="unsafe")


@pytest.fixture(scope="function")
def run_definition(
    request: pytest.FixtureRequest,
    caplog: pytest.LogCaptureFixture,
    pytestconfig: pytest.Config,
    mocker: MockerFixture,
    fp: FakeProcess,
    tmp_path: Path,
) -> Iterator[Callable]:
    cli_runner = CliRunner()
    with (
        cli_runner.isolated_filesystem(tmp_path) as runner_cwd,
        caplog.at_level(logging.DEBUG),
    ):

        def inner(definition: dict) -> None:
            _args = [
                f"{flag}" if value is None
                else f"{flag} {','.join('{k}={v}' for k, v in value.items())}" if isinstance(value, dict)
                else f"{flag} {','.join(value)}" if isinstance(value, list)
                else f"{flag} {','.join(value)}" if isinstance(value, tuple)
                else f"{flag} '{value}'" if isinstance(value, str) and " " in value
                else f"{flag} {value}"
                for flag, value in definition.get("args", {}).items()
            ]
            _invocation = Invocation(
                args=_args,
                structure=definition.get("structure", {}),
                working_directory=Path(runner_cwd),
                external_root=Path(request.fspath).parent,
                external=definition.get("external"),
            )
            _invocation(
                caplog=caplog,
                mocker=mocker,
                fp=fp,
                pytest_pwd=pytestconfig.invocation_params.dir,
                cli_runner=cli_runner,
                mocks=definition.get("mocks"),
                subprocess_mocks=definition.get("subprocess_mocks"),
            )
            assert _invocation.logs == literal(*definition.get("logs", []))
            assert _invocation.output == literal(*definition.get("output", []))

        yield inner


def parametrize_from_yaml(paths: list[Path]) -> Callable:
    warn(
        "YAML test definitions will be removed in a future release. "
        "Please check the documentation for more information regarding the new "
        "testing API.",
        DeprecationWarning,
        stacklevel=2,
    )

    def wrapper(func: Callable) -> Callable:
        definitions = (pytest.param(d, id=d.pop("id")) for p in paths for d in _YAML.load(p))
        return pytest.mark.parametrize("definition", definitions)(func)

    return wrapper

'{"meta": {"str": "cntn_str", "int": "cntn_int", "float": "cntn_float", "bool": "cntn_bool"}}'