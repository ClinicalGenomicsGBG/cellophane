
import json
import os
from os import chdir
from pathlib import Path
from shutil import copytree
from typing import Iterator

from cellophane import dev
from git import Repo
from pytest import TempPathFactory, fixture
from pytest_mock import MockerFixture


@fixture(scope="session")
def modules_repo_path(tmp_path_factory: TempPathFactory) -> Iterator[Path]:
    """Create a dummy modules repository."""
    path = tmp_path_factory.mktemp("modules_repo")
    repo = Repo.init(path)
    repo.create_remote("origin", url=str(path))
    modules_json: dict = {
        module: {
            "path": f"modules/{module}/",
            "latest": "2.0.0",
            "versions": {
                "dev": {
                    "cellophane": [">0.0.0"],
                    "tag": "dev",
                },
                "1.0.0": {
                    "cellophane": ["dev", "1.0.0"],
                    "tag": f"{module}/1.0.0",
                },
                "2.0.0": {
                    "cellophane": ["dev", "2.0.0"],
                    "tag": f"{module}/2.0.0",
                },
            },
        }
        for module in ("a", "b", "c", "d")
    }
    modules_json["c"].pop("latest")
    modules_json["c"]["versions"].pop("1.0.0")
    modules_json["c"]["versions"].pop("2.0.0")
    modules_json["c"]["versions"]["dev"]["cellophane"] = ["9001.0.0"]
    modules_json["d"]["path"] = "modules/SOME_OTHER_PATH/"
    with open(path / "modules.json", "w") as file:
        json.dump(modules_json, file)
    repo.index.add("**")
    repo.index.commit("Initial commit")
    for module in ("a", "b", "c", "d"):
        dir_name = module if module != "d" else "SOME_OTHER_PATH"
        (path / "modules" / dir_name).mkdir(parents=True)
        (path / "modules" / dir_name / module.upper()).write_text("1.0.0")
        (path / "modules" / dir_name / "requirements.txt").write_text("foo==1.0.0")
        repo.index.add(f"modules/{dir_name}")
        repo.index.commit(f"Add module {module}/1.0.0")
        repo.create_tag(f"{module}/1.0.0")
        (path / "modules" / dir_name / module.upper()).write_text("2.0.0")
        repo.index.add(f"modules/{dir_name}")
        repo.index.commit(f"Update module {module}/2.0.0")
        repo.create_tag(f"{module}/2.0.0")
    repo.create_head("dev")
    repo.remote("origin").push("master")
    repo.remote("origin").push("dev")
    yield path


@fixture(scope="function")
def modules_repo(
    modules_repo_path: Path,
    mocker: MockerFixture,
    tmp_path: Path,
) -> Iterator[dev.ModulesRepo]:
    """Create a dummy modules repository."""
    copytree(modules_repo_path, f"{tmp_path}/modules_repo", copy_function=os.link)
    modules_repo = dev.ModulesRepo(f"{tmp_path}/modules_repo")
    modules_repo.remote("origin").set_url(f"{tmp_path}/modules_repo")
    mocker.patch("cellophane.dev.ModulesRepo.from_url", return_value=modules_repo)
    yield modules_repo


@fixture(scope="session")
def project_repo_path(
    tmp_path_factory: TempPathFactory,
    modules_repo_path: Path,
) -> Iterator[tuple[Path, Path]]:
    """Create a dummy cellophane repository."""

    path = path = tmp_path_factory.mktemp("project_repo")
    local_path = path / "local"
    remote_path = path / "remote"
    local_path.mkdir(parents=True, exist_ok=True)
    remote_path.mkdir(parents=True, exist_ok=True)
    Repo.init(remote_path, bare=True)

    project_repo = dev.initialize_project(
        name="DUMMY",
        path=local_path,
        modules_repo_url=f"file://{modules_repo_path}",
        modules_repo_branch="master",
    )
    project_repo.create_remote("origin", url=f"file://{remote_path}")
    project_repo.git.push("origin", "master", set_upstream=True)

    yield local_path, remote_path


@fixture(scope="function")
def project_repo(
    project_repo_path: tuple[Path, Path],
    modules_repo: dev.ModulesRepo,
    tmp_path: Path,
) -> Iterator[dev.ProjectRepo]:
    """Create a dummy cellophane repository."""
    path = tmp_path / "project_repo"
    local_path, remote_path = project_repo_path
    copytree(local_path, f"{path}/local")
    copytree(remote_path, f"{path}/remote", copy_function=os.link)

    project_repo = dev.ProjectRepo(
        path=path / "local",
        modules_repo_url=f"file://{modules_repo.url}",
        modules_repo_branch="master",
    )
    project_repo.remote("origin").set_url(f"file://{path}/remote")

    _cwd = Path.cwd().absolute()
    chdir(path / "local")
    yield project_repo
    chdir(_cwd)