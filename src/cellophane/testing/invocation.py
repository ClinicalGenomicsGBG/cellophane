import logging
import shlex
from copy import deepcopy
from functools import partial
from pathlib import Path
from textwrap import dedent
from typing import Iterator
from uuid import uuid4

from click.testing import CliRunner
from coverage import Coverage
from pytest import Config, FixtureRequest, LogCaptureFixture, fixture
from pytest_mock import MockerFixture, MockType
from pytest_subprocess import FakeProcess
from pytest_subprocess.fake_process import ProcessRecorder

from cellophane import cellophane

from .util import PathDict


def _mock_python_calls(
    mocker: MockerFixture, mocks: dict | None
) -> dict[str, MockType]:
    return {
        target: mocker.patch(target=target, **(deepcopy(mock or {})))
        for target, mock in (mocks or {}).items()
    }


def _mock_subprocess_calls(
    fp: FakeProcess, mocks: dict | None
) -> dict[str, ProcessRecorder]:
    # Allow multiple invocations of the same command
    fp.keep_last_process(True)
    fp.allow_unregistered(True)

    return {
        key: fp.register_subprocess(shlex.split(key), **mock)
        for key, mock in (mocks or {}).copy().items()
    }


def _create_structure(
    root: Path,
    structure: dict,
    external_root: Path,
    external: dict[str, str] | None = None,
) -> None:
    """Create a directory structure from definition dict."""
    (root / "modules").mkdir(parents=True, exist_ok=True)
    (root / "schema.yaml").touch(exist_ok=True)
    for path, content in structure.items():
        if isinstance(content, dict):
            (root / path).mkdir(parents=True, exist_ok=True)
            _create_structure(root / path, content, external_root)
        else:
            (root / path).write_text(dedent(content).strip())
            (root / path).chmod(0o755)

    for src, dst in (external or {}).items():
        _src = Path(src)
        if not _src.is_absolute():
            _src = (external_root / src).resolve()
        (root / dst).symlink_to(_src)


class BaseTest:
    mocks: dict[str, dict] = {}
    subprocess_mocks: dict[str, dict] = {}
    args: list[str] = []
    structure: dict = PathDict({})
    external: dict[str, str] = {}

    def __init_subclass__(cls) -> None:
        cls.structure = PathDict(cls.structure)
        super().__init_subclass__()


class Invocation:
    args: list[str]
    structure: PathDict
    external: dict[str, str]
    external_root: Path
    working_directory: Path
    logs: list[str]
    output: str
    exception: BaseException | None
    exit_code: int
    mocks: dict[str, MockType]
    subprocess_mocks: dict[str, ProcessRecorder]

    def __init__(
        self,
        args: list[str],
        structure: PathDict,
        working_directory: Path,
        external_root: Path,
        external: dict[str, str] | None = None,
    ):
        if isinstance(args, str):
            args = [args]
        self.args = [split_arg for arg in args for split_arg in shlex.split(arg)]
        self.structure = PathDict(structure)
        self.working_directory = Path(working_directory)
        self.logs = []
        self.output = ""
        self.exception = None
        self.exit_code = 0
        self.mocks = {}
        self.external_root = external_root
        self.external = external or {}

    def __call__(
        self,
        caplog: LogCaptureFixture,
        mocker: MockerFixture,
        fp: FakeProcess,
        pytest_pwd: Path,
        cli_runner: CliRunner,
        mocks: dict[str, dict] | None = None,
        subprocess_mocks: dict[str, dict] | None = None,
    ) -> "Invocation":
        _create_structure(
            root=self.working_directory,
            structure=self.structure,
            external_root=self.external_root,
            external=self.external,
        )
        try:
            mocker.patch("cellophane.cellophane.setup_console_handler")
            entrypoint = cellophane("DUMMY", root=self.working_directory)
            self.mocks = _mock_python_calls(mocker, mocks)
            self.subprocess_mocks = _mock_subprocess_calls(fp, subprocess_mocks)
            logging.debug("BEGIN TEST")
            result = cli_runner.invoke(
                cli=entrypoint,
                args=self.args,
                env={"TERM": "dumb"},
                standalone_mode=False,
            )
        except (SystemExit, Exception) as exc:  # pylint: disable=broad-except
            self.exception: BaseException | None = exc
            self.exit_code = 1
            self.output = ""
        else:
            self.exception = result.exception
            self.exit_code = result.exit_code
            self.output = result.output
        finally:
            logging.debug("END TEST")
            self.logs = caplog.messages.copy()
            # Ensure coverage reports are generated and combined
            cov = Coverage(data_file=pytest_pwd / f".coverage.{uuid4()}")
            cov.combine(
                data_paths=[str(d) for d in self.working_directory.glob(".coverage.*")]
            )

        return self


@fixture(scope="function")
def deferred_invocation(
    tmp_path: Path,
    caplog: LogCaptureFixture,
    mocker: MockerFixture,
    fp: FakeProcess,
    request: FixtureRequest,
    pytestconfig: Config,
) -> Iterator[partial[Invocation]]:
    """Fixture for invoking demuxer."""
    overrides = request.keywords.get("override")
    override_kwargs = overrides.kwargs if overrides else {}

    _args = override_kwargs.get("args", request.cls.args)
    _structure = override_kwargs.get("structure", request.cls.structure)
    _external = override_kwargs.get("external", request.cls.external)
    _mocks = override_kwargs.get("mocks", request.cls.mocks)
    _subprocess_mocks = override_kwargs.get(
        "subprocess_mocks", request.cls.subprocess_mocks
    )
    _extenal_root = Path(request.fspath).parent

    cli_runner = CliRunner()
    with (
        cli_runner.isolated_filesystem(tmp_path) as runner_cwd,
        caplog.at_level(logging.DEBUG),
    ):
        _invocation = Invocation(
            args=_args,
            structure=_structure,
            working_directory=Path(runner_cwd),
            external_root=_extenal_root,
            external=_external,
        )

        yield partial(
            _invocation,
            caplog=caplog,
            mocker=mocker,
            fp=fp,
            pytest_pwd=pytestconfig.invocation_params.dir,
            cli_runner=cli_runner,
            mocks=_mocks,
            subprocess_mocks=_subprocess_mocks,
        )


@fixture(scope="function")
def invocation(deferred_invocation: partial[Invocation]) -> Iterator:
    """Fixture for invoking demuxer."""
    yield deferred_invocation()
