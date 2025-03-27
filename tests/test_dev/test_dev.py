"""Tests for the cellophane.__main__ module."""

# pylint: disable=protected-access,redefined-outer-name

from os import chdir
from pathlib import Path
from shutil import copytree, rmtree
from typing import Iterator
from unittest.mock import MagicMock

from cellophane import dev
from cellophane.testing import literal
from click.testing import CliRunner
from git import Repo
from pytest import LogCaptureFixture, TempPathFactory, fixture, mark, param, raises
from pytest_mock import MockerFixture


@fixture(scope="session")
def session_modules_repo(
    tmp_path_factory: TempPathFactory,
) -> Iterator[dev.ModulesRepo]:
    """Create a dummy modules repository."""
    path = tmp_path_factory.mktemp("modules_repo")
    Repo.init(path)
    repo = dev.ModulesRepo(path)
    repo.create_remote("origin", url=str(path))
    copytree(Path(__file__).parent / "repo", path, dirs_exist_ok=True)
    repo.index.add("**")
    repo.index.commit("Initial commit")
    repo.create_tag("a/1.0.0")
    repo.create_tag("b/1.0.0")
    repo.create_tag("c/1.0.0")
    (path / "modules" / "a" / "A").write_text("2.0.0")
    repo.index.add("**")
    repo.index.commit("Dummy commit")
    repo.create_tag("a/2.0.0")
    repo.create_head("dev")

    repo.remote("origin").push("master")
    repo.remote("origin").push("dev")

    yield repo
    rmtree(path)


@fixture(scope="function")
def modules_repo(
    session_modules_repo: dev.ModulesRepo,
    mocker: MockerFixture,
) -> Iterator[dev.ModulesRepo]:
    """Create a dummy modules repository."""
    mocker.patch(
        "cellophane.dev.ModulesRepo.from_url", return_value=session_modules_repo
    )
    yield session_modules_repo


@fixture(scope="function")
def project_repo(
    tmp_path_factory: TempPathFactory,
    modules_repo: dev.ModulesRepo,
) -> Iterator[dev.ProjectRepo]:
    """Create a dummy cellophane repository."""

    local_path = tmp_path_factory.mktemp("local")
    remote_path = tmp_path_factory.mktemp("remote")
    _pwd = Path(".").absolute()
    chdir(local_path)

    Repo.init(remote_path, bare=True)
    repo = dev.initialize_project(
        "DUMMY", local_path, str(modules_repo.working_dir), "main"
    )
    repo.create_remote("origin", url=f"file://{remote_path}")
    repo.git.push("origin", "master", set_upstream=True)
    yield repo

    rmtree(local_path)
    rmtree(remote_path)
    chdir(_pwd)


class Test_ProjectRepo:
    """Test cellophane repository."""

    def test_initialize(self, project_repo: dev.ProjectRepo) -> None:
        """Test cellophane repository initialization."""
        _path = Path(project_repo.working_dir)
        assert _path.exists()
        assert (_path / "modules").exists()
        assert (_path / "schema.yaml").exists()
        assert (_path / "config.example.yaml").exists()
        assert (_path / "DUMMY.py").exists()
        assert (_path / "__main__.py").exists()
        assert {*project_repo.absent_modules} == {*project_repo.external.modules}
        assert project_repo.modules == set()

    @staticmethod
    def test_initialize_exception_file_exists(project_repo: dev.ProjectRepo) -> None:
        """Test cellophane repository initialization with existing file."""
        with raises(FileExistsError):
            dev.initialize_project(
                "DUMMY", Path(project_repo.working_dir), "DUMMY", "main"
            )

    @staticmethod
    def test_invalid_repository(tmp_path: Path) -> None:
        """Test invalid cellophane repository."""
        with raises(dev.InvalidProjectRepoError):
            dev.ProjectRepo(
                tmp_path,
                modules_repo_url="__INVALID__",
                modules_repo_branch="main",
            )


class Test_ModulesRepo:
    """Test modules repository."""

    @staticmethod
    def test_from_url(modules_repo: dev.ModulesRepo) -> None:
        """Test modules repository initialization from URL."""
        assert modules_repo

    @staticmethod
    def test_invalid_remote_url() -> None:
        """Test invalid remote URL."""
        with raises(dev.InvalidModulesRepoError):
            dev.ModulesRepo.from_url("invalid://INVALID", branch="main")

    @staticmethod
    def test_tags(modules_repo: dev.ModulesRepo) -> None:
        """Test tags."""
        assert modules_repo.tags

    @staticmethod
    def test_url(modules_repo: dev.ModulesRepo) -> None:
        """Test URL."""
        path = modules_repo.working_dir
        assert modules_repo.url == str(path)


class Test_update_example_config:
    """Test updating example config."""

    def test_update_example_config(self, tmp_path: Path) -> None:
        """Test updating example config."""
        chdir(tmp_path)
        (tmp_path / "modules").mkdir()
        (tmp_path / "schema.yaml").touch()

        dev.update_example_config(tmp_path)

        assert (tmp_path / "config.example.yaml").exists()


class Test_ask_modules_branch:
    """Test asking for modules and branches."""

    @mark.parametrize(
        "valid_modules,exception",
        [
            param(["DUMMY_a", "DUMMY_b"], None, id="valid"),
            param([], dev.NoModulesError, id="invalid"),
        ],
    )
    def test_ask_modules(
        self,
        mocker: MockerFixture,
        valid_modules: list[str],
        exception: type[Exception],
    ) -> None:
        """Test asking for modules."""
        _checkbox_mock = MagicMock()
        mocker.patch("cellophane.dev.util.checkbox", return_value=_checkbox_mock)
        assert (
            raises(exception, dev.ask_modules, valid_modules)
            if exception
            else dev.ask_modules(valid_modules) and _checkbox_mock.ask.call_count == 1
        )

    def test_ask_version(
        self,
        mocker: MockerFixture,
        modules_repo: dev.ModulesRepo,
    ) -> None:
        """Test asking for branch."""
        _select_mock = MagicMock(ask=MagicMock(return_value="latest"))
        mocker.patch("cellophane.dev.util.select", return_value=_select_mock)
        assert dev.ask_version(
            [*modules_repo.modules.keys()][0],
            valid=[("foo/1.33.7", "1.33.7")],
        )
        assert _select_mock.ask.call_count == 1


class Test_module_cli:
    """Test module CLI."""

    runner = CliRunner()

    @fixture(scope="function", autouse=True)
    def mock_logging(self, mocker: MockerFixture) -> Iterator[None]:
        mocker.patch("cellophane.dev.cli.logs.setup_console_handler")
        yield

    def test_invalid_project_repo(
        self,
        tmp_path: Path,
        caplog: LogCaptureFixture,
    ) -> None:
        """Test module CLI with invalid project repository."""
        chdir(tmp_path)
        result = self.runner.invoke(dev.main, "module add")
        assert caplog.messages == literal("Invalid cellophane repository")
        assert result.exit_code == 1

    def test_invalid_modules_repo(
        self,
        project_repo: dev.ProjectRepo,
        mocker: MockerFixture,
        caplog: LogCaptureFixture,
    ) -> None:
        """Test module CLI with invalid project repository."""
        mocker.patch(
            "cellophane.dev.repo.ModulesRepo.from_url",
            side_effect=dev.InvalidModulesRepoError("INVALID"),
        )
        result = self.runner.invoke(dev.main, "--modules-repo INVALID module add")
        assert caplog.messages == literal("Invalid modules repository")
        assert result.exit_code == 1

    def test_dirty_repo(
        self,
        project_repo: dev.ProjectRepo,
        caplog: LogCaptureFixture,
    ) -> None:
        """Test module CLI with dirty cellophane repository."""
        (Path(project_repo.working_dir) / "DIRTY").touch()
        project_repo.index.add("DIRTY")
        result = self.runner.invoke(dev.main, "module add")
        assert caplog.messages == literal("Repository has uncommited changes")
        assert result.exit_code == 1

    def test_add(
        self,
        project_repo: dev.ProjectRepo,
        mocker: MockerFixture,
        caplog: LogCaptureFixture,
    ) -> None:
        """Test module add."""
        self.runner.invoke(dev.main, "module add a@1.0.0")
        assert "feat(cellophane): Added 'a@1.0.0'" in project_repo.head.commit.message

        previous_head = project_repo.head.commit
        self.runner.invoke(dev.main, "module add a@1.0.0")
        assert caplog.messages == literal("Module 'a' is not valid")
        assert previous_head == project_repo.head.commit

        original_head = project_repo.head.commit
        mocker.patch(
            "cellophane.dev.cli.update_example_config", side_effect=Exception("DUMMY")
        )
        self.runner.invoke(dev.main, "module add b@1.0.0")
        assert caplog.messages == literal("Unable to add 'b@1.0.0': Exception('DUMMY')")
        assert original_head == project_repo.head.commit

        self.runner.invoke(dev.main, "module add c")
        assert caplog.messages == literal("No compatible versions for module 'c'")

    def test_update(
        self,
        project_repo: dev.ProjectRepo,
        mocker: MockerFixture,
        caplog: LogCaptureFixture,
    ) -> None:
        """Test module update."""
        self.runner.invoke(dev.main, "module add a@1.0.0")
        project_repo.remote("origin").push()

        self.runner.invoke(dev.main, "module update a@dev")
        assert "chore(cellophane): Updated 'a->dev'" in project_repo.head.commit.message

        self.runner.invoke(dev.main, "module update a@latest")
        assert "chore(cellophane): Updated 'a->2.0.0'" in project_repo.head.commit.message

        self.runner.invoke(dev.main, "module update a@1.0.0")
        assert "chore(cellophane): Updated 'a->1.0.0'" in project_repo.head.commit.message

        self.runner.invoke(dev.main, "module update a@INVALID")
        assert caplog.messages == literal("Version 'INVALID' is invalid for 'a'")

        original_head = project_repo.head.commit
        mocker.patch(
            "cellophane.dev.cli.update_example_config", side_effect=Exception("DUMMY")
        )
        self.runner.invoke(dev.main, "module update a@dev")
        assert caplog.messages == literal("Unable to update 'a->dev': Exception('DUMMY')")
        assert original_head == project_repo.head.commit

    def test_rm(
        self,
        project_repo: dev.ProjectRepo,
        mocker: MockerFixture,
        caplog: LogCaptureFixture,
    ) -> None:
        """Test module rm."""
        self.runner.invoke(dev.main, "module add a@1.0.0 b@1.0.0")
        project_repo.remote("origin").push()

        self.runner.invoke(dev.main, "module rm a")
        assert "feat(cellophane): Removed 'a'" in project_repo.head.commit.message

        previous_head = project_repo.head.commit
        self.runner.invoke(dev.main, "module rm a")
        assert caplog.messages == literal("Module 'a' is not valid")
        assert previous_head == project_repo.head.commit

        previous_head = project_repo.head.commit
        mock = mocker.patch(
            "cellophane.dev.cli.update_example_config", side_effect=Exception("DUMMY")
        )
        self.runner.invoke(dev.main, "module rm b")
        assert caplog.messages == literal("Unable to remove 'b': Exception('DUMMY')")
        assert previous_head == project_repo.head.commit
        mocker.stop(mock)

        self.runner.invoke(dev.main, "module rm b")
        previous_head = project_repo.head.commit
        self.runner.invoke(dev.main, "module rm")
        assert caplog.messages == literal("No modules to select from")
        assert previous_head == project_repo.head.commit


class Test_cli_init:
    """Test cellophane CLI for initializing a new project."""

    runner = CliRunner()

    @fixture(scope="function", autouse=True)
    def mock_logging(self, mocker: MockerFixture) -> Iterator[None]:
        mocker.patch("cellophane.dev.cli.logs.setup_console_handler")
        yield

    @fixture(scope="class")
    def project_path(self, tmp_path_factory: TempPathFactory) -> Path:
        """Create a temporary project path."""
        return tmp_path_factory.mktemp("DUMMY")

    @mark.parametrize(
        "command,exit_code",
        [
            param("init DUMMY", 0, id="init"),
            param("init DUMMY", 1, id="init_exists"),
            param("init DUMMY --force", 0, id="init_force"),
        ],
    )
    def test_init_cli(
        self,
        project_path: Path,
        command: str,
        exit_code: int,
    ) -> None:
        """Test cellophane CLI for initializing a new project."""
        chdir(project_path)
        result = self.runner.invoke(dev.main, command)
        assert result.exit_code == exit_code

    def test_init_cli_unhandled_exception(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """Test exception handling in cellophane CLI for initializing a new project."""
        mocker.patch(
            "cellophane.dev.cli.initialize_project",
            side_effect=Exception("DUMMY"),
        )
        chdir(tmp_path)
        result = self.runner.invoke(dev.main, "init DUMMY")
        assert result.exit_code == 1
