"""Tests for the cellophane.__main__ module."""

from os import chdir
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from cellophane import dev
from cellophane.testing import literal
from click.testing import CliRunner
from pytest import LogCaptureFixture, TempPathFactory, fixture, mark, param, raises
from pytest_mock import MockerFixture

from .fixtures import *  # noqa: F403


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
            dev.initialize_project("DUMMY", Path(project_repo.working_dir), "DUMMY", "main")

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
    def test_invalid_modules_json(modules_repo: dev.ModulesRepo) -> None:
        """Test modules repository initialization from URL."""
        repo = modules_repo
        index = repo.index
        local_path = Path(modules_repo.working_dir)
        (local_path / "modules.json").write_text("INVALID")

        index.add("modules.json")
        index.commit("Invalid modules.json")
        index.write()
        repo.remote("origin").push("master")
        with raises(dev.InvalidModulesRepoError):
            repo.modules

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
            valid_versions=[("foo/1.33.7", "1.33.7")],
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
        assert "Invalid cellophane project repository '.'" in result.stdout
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
        assert "Invalid cellophane modules repository 'INVALID'" in result.stdout
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

    def test_no_module_selected(self, project_repo: dev.ProjectRepo, mocker: MockerFixture) -> None:
        mocker.patch("questionary.question.Question.ask", return_value=None)
        original_head = project_repo.head.commit
        result = self.runner.invoke(dev.main, "module add")
        assert "No modules selected" in result.stdout
        assert project_repo.head.commit == original_head

    def test_no_version_selected(self, project_repo: dev.ProjectRepo, mocker: MockerFixture) -> None:
        mocker.patch("questionary.question.Question.ask", return_value=None)
        original_head = project_repo.head.commit
        result = self.runner.invoke(dev.main, "module add a")
        assert "No version selected" in result.stdout
        assert project_repo.head.commit == original_head

    def test_unhandled_exception(self, project_repo: dev.ProjectRepo, mocker: MockerFixture) -> None:
        mocker.patch("cellophane.dev.cli.module_action", side_effect=Exception("DUMMY"))
        result = self.runner.invoke(dev.main, "module add a@1.0.0")
        assert "Unhandled Exception: Exception('DUMMY')" in result.stdout
        assert result.exit_code == 1

    def test_add(
        self,
        project_repo: dev.ProjectRepo,
        mocker: MockerFixture,
        caplog: LogCaptureFixture,
    ) -> None:
        """Test module add."""
        repo = project_repo
        result = self.runner.invoke(dev.main, "module add a@1.0.0")
        assert "chore(cellophane): Add module a@1.0.0" in repo.head.commit.message, result.stdout

        previous_head = repo.head.commit
        result = self.runner.invoke(dev.main, "module add a@1.0.0")
        assert "Module 'a' is not valid" in result.stdout, result.exception
        assert previous_head == repo.head.commit

        original_head = project_repo.head.commit
        mock = mocker.patch("cellophane.dev.cli.update_example_config", side_effect=Exception("DUMMY"))
        result = self.runner.invoke(dev.main, "module add b@1.0.0")
        assert "Add module b@1.0.0 failed: Exception('DUMMY')" in result.stdout
        assert original_head == project_repo.head.commit
        mocker.stop(mock)

        self.runner.invoke(dev.main, "module add c")
        assert caplog.messages == literal("No compatible versions for module 'c'")

        result = self.runner.invoke(dev.main, "module add c@latest")
        assert "Version 'latest' is invalid for module 'c'" in result.stdout

        mocker.patch("questionary.question.Question.ask", return_value=("2.0.0", "d/2.0.0"))
        result = self.runner.invoke(dev.main, "module add d")
        assert "Add module d@2.0.0" in result.stdout
        assert "chore(cellophane): Add module d@2.0.0" in repo.head.commit.message

    def test_update(
        self,
        project_repo: dev.ProjectRepo,
        mocker: MockerFixture,
        caplog: LogCaptureFixture,
    ) -> None:
        """Test module update."""
        self.runner.invoke(dev.main, "module add a@1.0.0")
        repo.remote("origin").push()
        original_head = repo.head.commit

        result = self.runner.invoke(dev.main, "module update a@dev")
        assert "chore(cellophane): Update module a->dev" in repo.head.commit.message, result.stdout

        result = self.runner.invoke(dev.main, "module update a@latest")
        assert "chore(cellophane): Update module a->2.0.0" in repo.head.commit.message, result.stdout

        result = self.runner.invoke(dev.main, "module update a@1.0.0")
        assert repo.head.commit == original_head, repo.git.log()

        result = self.runner.invoke(dev.main, "module update a@INVALID")
        assert result.stdout == literal("Version 'INVALID' is invalid for module 'a'")

        original_head = project_repo.head.commit
        mocker.patch("cellophane.dev.cli.update_example_config", side_effect=Exception("DUMMY"))
        result = self.runner.invoke(dev.main, "module update a@dev")
        assert "Update module a->dev failed: Exception('DUMMY')" in result.stdout
        assert original_head == project_repo.head.commit

    def test_rm(
        self,
        project_repo: dev.ProjectRepo,
        mocker: MockerFixture,
        caplog: LogCaptureFixture,
    ) -> None:
        """Test module rm."""
        repo = project_repo
        result = self.runner.invoke(dev.main, "module add a@1.0.0 b@1.0.0")
        repo.remote("origin").push()

        self.runner.invoke(dev.main, "module rm a")
        assert "chore(cellophane): Remove module a" in repo.head.commit.message

        previous_head = project_repo.head.commit
        self.runner.invoke(dev.main, "module rm a")
        assert caplog.messages == literal("Module 'a' is not valid")
        assert previous_head == project_repo.head.commit

        previous_head = repo.head.commit
        mock = mocker.patch("cellophane.dev.cli.update_example_config", side_effect=Exception("DUMMY"))
        result = self.runner.invoke(dev.main, "module rm b")
        assert "Remove module b failed: Exception('DUMMY')" in result.stdout
        assert previous_head == repo.head.commit
        mocker.stop(mock)

        self.runner.invoke(dev.main, "module rm b")
        previous_head = project_repo.head.commit
        self.runner.invoke(dev.main, "module rm")
        assert caplog.messages == literal("No modules to select from")
        assert previous_head == project_repo.head.commit

    def test_action_rewrite_add_rm(
        self,
        project_repo: dev.ProjectRepo,
    ) -> None:
        repo = project_repo

        # If a module is added and removed, the add commit should be removed.
        original_head = repo.head.commit
        add_result = self.runner.invoke(dev.main, "module add a@1.0.0")
        rm_result = self.runner.invoke(dev.main, "module rm a")
        assert add_result.exit_code == 0, add_result.stdout
        assert rm_result.exit_code == 0, add_result.stdout
        assert repo.head.commit == original_head

    def test_action_rewrite_rm_add(
        self,
        project_repo: dev.ProjectRepo,
    ) -> None:
        repo = project_repo

        # If a module is added and removed, the add commit should be removed.
        self.runner.invoke(dev.main, "module add a@1.0.0")
        project_repo.remote("origin").push()
        original_head = repo.head.commit

        rm_result = self.runner.invoke(dev.main, "module rm a")
        add_result = self.runner.invoke(dev.main, "module add a@1.0.0")

        assert rm_result.exit_code == 0, rm_result.stdout
        assert add_result.exit_code == 0, add_result.stdout
        assert repo.head.commit == original_head, add_result.stdout

        rm_result = self.runner.invoke(dev.main, "module rm a")
        add_result = self.runner.invoke(dev.main, "module add a@2.0.0")

        assert rm_result.exit_code == 0, rm_result.stdout
        assert add_result.exit_code == 0, add_result.stdout
        assert "chore(cellophane): Update module a->2.0.0" in repo.head.commit.message

    def test_action_rewrite_add_update(
        self,
        project_repo: dev.ProjectRepo,
    ) -> None:
        repo = project_repo
        # If module is added and updated, the add commit is removed and the
        # update commit is changed to an add commit with the new version.
        add_result = self.runner.invoke(dev.main, "module add a@1.0.0")
        add_commit = repo.head.commit
        updade_result = self.runner.invoke(dev.main, "module update a@dev")
        updade_commit = repo.head.commit
        all_commits = [*repo.iter_commits()]
        assert add_result.exit_code == 0, add_result.stdout
        assert updade_result.exit_code == 0, updade_result.stdout
        assert add_commit not in all_commits
        assert updade_commit in all_commits

    def test_action_rewrite_update_update(
        self,
        project_repo: dev.ProjectRepo,
        modules_repo: dev.ModulesRepo,
    ) -> None:
        repo = project_repo

        self.runner.invoke(dev.main, "module add a@1.0.0")
        project_repo.remote("origin").push()
        update_result_1 = self.runner.invoke(dev.main, "module update a@dev")
        update_head_1 = repo.head.commit

        # If a module is updated twice, the first update commit should be removed
        (Path(modules_repo.working_dir) / "modules" / "a" / "A").write_text("UPDATED")
        modules_repo.heads["dev"].checkout()
        modules_repo.index.add("modules/a/A")
        modules_repo.index.write()
        modules_repo.index.commit("Update module a")
        modules_repo.remote("origin").push("dev")

        update_result_2 = self.runner.invoke(dev.main, "module update a@dev")
        update_head_2 = repo.head.commit

        assert update_result_1.exit_code == 0, update_result_1.stdout
        assert update_result_2.exit_code == 0, update_result_2.stdout

        all_commits = [*repo.iter_commits()]
        assert update_head_1 not in all_commits, repo.git.log()
        assert "chore(cellophane): Update module a->dev" in update_head_2.message

    def test_action_rewrite_abort(
        self,
        project_repo: dev.ProjectRepo,
        mocker: MockerFixture,
    ) -> None:
        repo = project_repo

        class ProjectRepoMock(dev.ProjectRepo):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, **kwargs)
                self.git_orig = self.git
                self.git = MagicMock(wraps=self.git_orig)
                self.git.rebase = self._rebase

            def _rebase(self, *args: Any, **kwargs: Any) -> Any:
                if "--onto" in args[0]:
                    raise Exception("DUMMY")
                else:
                    return self.git_orig.rebase(*args, **kwargs)

        mocker.patch("cellophane.dev.cli.ProjectRepo", ProjectRepoMock)

        original_head = repo.head.commit
        result_1 = self.runner.invoke(dev.main, "module add a@1.0.0")
        commit_1 = repo.head.commit
        result_2 = self.runner.invoke(dev.main, "module update a@dev")
        commit_2 = repo.head.commit

        all_commits = [*repo.iter_commits()]

        assert result_1.exit_code == 0, result_1.stdout
        assert result_2.exit_code == 0, result_2.stdout
        assert commit_1 != original_head, repo.git.log()
        assert commit_2 != commit_1, repo.git.log()

        assert original_head in all_commits
        assert commit_1 in all_commits
        assert commit_2 in all_commits


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
        modules_repo: dev.ModulesRepo,
    ) -> None:
        """Test cellophane CLI for initializing a new project."""
        chdir(project_path)
        result = self.runner.invoke(dev.main, f"--modules-repo {modules_repo.working_dir} {command}")
        assert result.exit_code == exit_code, result.stdout

    def test_init_cli_unhandled_exception(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
        modules_repo: dev.ModulesRepo,
    ) -> None:
        """Test exception handling in cellophane CLI for initializing a new project."""
        mocker.patch(
            "cellophane.dev.cli.initialize_project",
            side_effect=Exception("DUMMY"),
        )
        chdir(tmp_path)
        result = self.runner.invoke(dev.main, f"--modules-repo {modules_repo.working_dir} init DUMMY")
        assert result.exit_code == 1
