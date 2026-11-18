"""Git lifecycle and post-copy verification (`tasks/lifecycle.py`), driven through `run()` and `main()`.

Real git in temp dirs, a recording verify fake, and a fake `mise` on `PATH` for the CLI seam.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from collections.abc import Callable
from pathlib import Path

import lifecycle
import pytest
import yaml
from _projects import GIT_ENV, VARIANTS, GitRepo, RenderedProject, run_copy_from

SEED_MESSAGE = "seed"


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every test an explicit identity and keep global/system git config out of the way."""
    for key, value in GIT_ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def plain_dir(tmp_path: Path) -> Path:
    """A non-git destination holding a scaffold file."""
    dst = tmp_path / "project"
    dst.mkdir()
    (dst / "README.md").write_text("scaffold\n")
    return dst


@pytest.fixture
def work_tree(plain_dir: Path) -> Path:
    """A clean git work tree whose only commit is `seed`."""
    GitRepo.init(plain_dir).commit_all(SEED_MESSAGE)
    return plain_dir


class RecordingVerify:
    """Fake post-commit verifier: fails unless a commit exists and counts the single call."""

    def __init__(self, dst: Path) -> None:
        self.repo = GitRepo(dst)
        self.calls = 0

    def __call__(self) -> None:
        self.repo.run("rev-parse", "--verify", "HEAD")
        self.calls += 1


def _fake_mise(directory: Path, log: Path, expected_subject: str) -> Path:
    """A `mise` that requires the lifecycle commit, then records the task it was asked to run."""
    bin_dir = directory / "bin"
    bin_dir.mkdir()
    script = bin_dir / "mise"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f'test "$(git log -1 --format=%s)" = {shlex.quote(expected_subject)}\n'
        "git rev-parse --verify HEAD >/dev/null\n"
        f"printf '%s\\n' \"$*\" >> {shlex.quote(str(log))}\n"
    )
    script.chmod(0o755)
    return bin_dir


def _pre_render(template_source: Path, dst: Path, answers_file: Path) -> Path:
    """Render files only, then persist the answers for `lifecycle.main`. Returns the resolved project path."""
    answers = dict(VARIANTS["basic"].answers)
    path = run_copy_from(template_source, dst, answers, skip_tasks=True)
    answers_file.write_text(yaml.safe_dump(answers))
    return path


def test_cli_commits_render_then_runs_install_and_ci(
    template_source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    answers_file = tmp_path / "answers.yml"
    dst = _pre_render(template_source, tmp_path / "project", answers_file)
    log = tmp_path / "mise.log"
    monkeypatch.setenv("PATH", f"{_fake_mise(tmp_path, log, lifecycle.SCAFFOLD_MESSAGE)}:{os.environ['PATH']}")
    monkeypatch.chdir(dst)

    assert lifecycle.main(["copy", "--src", str(template_source), "--answers", str(answers_file)]) == 0

    project = RenderedProject(dst, dict(VARIANTS["basic"].answers))
    assert project.subjects() == [lifecycle.SCAFFOLD_MESSAGE, lifecycle.INIT_MESSAGE]
    assert {"README.md", "pyproject.toml", ".copier-answers.yml"} <= project.commit_files()
    assert project.tracked("HEAD~1") == set(), "the init commit must stay empty"
    assert log.read_text().splitlines() == ["run install", "run ci"]


def test_cli_update_commits_template_changes(template_source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    answers_file = tmp_path / "answers.yml"
    dst = _pre_render(template_source, tmp_path / "project", answers_file)
    GitRepo.init(dst).commit_all(SEED_MESSAGE)
    readme = dst / "README.md"
    readme.write_text(readme.read_text() + "\nlocal change\n")
    log = tmp_path / "mise.log"
    monkeypatch.setenv("PATH", f"{_fake_mise(tmp_path, log, lifecycle.UPDATE_MESSAGE)}:{os.environ['PATH']}")
    monkeypatch.chdir(dst)

    assert lifecycle.main(["update", "--src", str(template_source), "--answers", str(answers_file)]) == 0

    project = RenderedProject(dst, dict(VARIANTS["basic"].answers))
    assert project.subjects() == [lifecycle.UPDATE_MESSAGE, SEED_MESSAGE]
    assert project.commit_files() == {"README.md"}
    assert log.read_text().splitlines() == ["run install", "run ci"]


def test_uv_pin_written_by_pin_task_is_committed(work_tree: Path):
    """`uv python pin` writes `.python-version` outside Copier's render set; the lifecycle commit must carry it."""
    repo = GitRepo(work_tree)
    repo.write(".python-version", "3.12\n")

    lifecycle.run("update", work_tree, verify=RecordingVerify(work_tree), render=_rendered())

    assert repo.files() == {".python-version"}
    assert repo.status() == ""


def test_absent_uv_pin_is_skipped_without_failing(work_tree: Path):
    """A generated path the pin step never wrote is filtered out, so a run without it still commits the render."""
    _add_file(work_tree)

    lifecycle.run("copy", work_tree, verify=RecordingVerify(work_tree), render=_rendered("change.txt"))

    assert GitRepo(work_tree).files() == {"change.txt"}
    assert GitRepo(work_tree).status() == ""


def test_generated_files_and_dropped_odd_names_commit_together(work_tree: Path):
    """A generated lock and a dropped non-ASCII name share one commit: NUL-delimited paths survive the union."""
    repo = GitRepo(work_tree)
    repo.write("naïve notes.txt", "odd name\n")
    repo.commit_all("add odd name")
    repo.write("uv.lock", "lock\n")
    (repo.path / "naïve notes.txt").unlink()

    lifecycle.run("update", work_tree, verify=RecordingVerify(work_tree), render=_rendered())

    assert repo.files() == {"naïve notes.txt", "uv.lock"}


def test_copy_outside_work_tree_creates_empty_init_then_scaffold_commit(plain_dir: Path):
    lifecycle.run("copy", plain_dir, verify=RecordingVerify(plain_dir), render=_rendered("README.md"))

    repo = GitRepo(plain_dir)
    assert repo.subjects() == [lifecycle.SCAFFOLD_MESSAGE, lifecycle.INIT_MESSAGE]
    root = repo.run("rev-list", "--max-parents=0", "HEAD").stdout.strip()
    assert root == repo.run("rev-parse", "HEAD~1").stdout.strip()
    assert repo.tracked("HEAD~1") == set()
    assert repo.files() == {"README.md"}


def test_copy_outside_work_tree_without_rendered_files_keeps_empty_init_commit(plain_dir: Path):
    verify = RecordingVerify(plain_dir)

    lifecycle.run("copy", plain_dir, verify=verify, render=_rendered())

    repo = GitRepo(plain_dir)
    assert repo.subjects() == [lifecycle.INIT_MESSAGE]
    assert repo.tracked() == set()
    assert repo.status() == "?? README.md\n"
    assert verify.calls == 1


def test_update_outside_work_tree_is_noop(plain_dir: Path):
    verify = RecordingVerify(plain_dir)

    lifecycle.run("update", plain_dir, verify=verify, render=_rendered("README.md"))

    assert not (plain_dir / ".git").exists()
    assert verify.calls == 0
    assert (plain_dir / "README.md").read_text() == "scaffold\n"


@pytest.mark.parametrize(
    ("operation", "message"), [("copy", lifecycle.SCAFFOLD_MESSAGE), ("update", lifecycle.UPDATE_MESSAGE)]
)
def test_work_tree_changes_are_committed_on_top_of_existing_history(work_tree: Path, operation: str, message: str):
    repo = GitRepo(work_tree)
    seed = repo.head()
    _add_file(work_tree)

    lifecycle.run(operation, work_tree, verify=RecordingVerify(work_tree), render=_rendered("change.txt"))

    assert repo.subjects() == [message, SEED_MESSAGE]
    assert repo.run("rev-parse", "HEAD~1").stdout.strip() == seed
    assert repo.status() == ""


def test_only_rendered_files_are_committed_and_printed(work_tree: Path, capsys: pytest.CaptureFixture[str]):
    repo = GitRepo(work_tree)
    _add_file(work_tree)
    repo.write("user-notes.md", "mine\n")
    repo.write("staged-notes.md", "mine\n")
    repo.run("add", "staged-notes.md")

    lifecycle.run("copy", work_tree, verify=RecordingVerify(work_tree), render=_rendered("change.txt"))

    assert repo.files() == {"change.txt"}
    assert "?? user-notes.md" in repo.status()
    assert repo.run("diff", "--cached", "--name-only").stdout == "staged-notes.md\n"
    assert "A\tchange.txt" in capsys.readouterr().out


def _modified_readme(dst: Path) -> None:
    (dst / "README.md").write_text("updated\n")


def _drop_tracked(dst: Path) -> None:
    repo = GitRepo(dst)
    repo.write("naïve notes.txt", "odd name\n")
    repo.commit_all("add odd name")
    (dst / "README.md").unlink()
    (dst / "naïve notes.txt").unlink()


def _add_gitignored(dst: Path) -> None:
    (dst / ".gitignore").write_text("ignored.txt\n")
    (dst / "ignored.txt").write_text("rendered\n")


def _add_file(dst: Path) -> None:
    (dst / "change.txt").write_text("change\n")


def _rendered(*paths: str) -> Callable[[], set[str]]:
    """Stub for the lazy render step: the set of paths Copier produced."""
    return lambda: set(paths)


@pytest.mark.parametrize(
    ("prepare", "operation", "render", "committed", "status"),
    [
        (_modified_readme, "update", ("README.md",), {"README.md"}, ""),
        (_drop_tracked, "update", (), {"README.md", "naïve notes.txt"}, ""),
        (_add_gitignored, "copy", ("ignored.txt",), {"ignored.txt"}, "?? .gitignore\n"),
        (_add_file, "copy", ("change.txt", "missing/file.py"), {"change.txt"}, ""),
    ],
    ids=["modified", "deleted", "gitignored", "missing-render"],
)
def test_rendered_changes_are_committed_exactly(
    work_tree: Path,
    prepare: Callable[[Path], None],
    operation: str,
    render: tuple[str, ...],
    committed: set[str],
    status: str,
):
    prepare(work_tree)

    lifecycle.run(operation, work_tree, verify=RecordingVerify(work_tree), render=_rendered(*render))

    repo = GitRepo(work_tree)
    assert repo.files() == committed
    assert repo.status() == status


def test_render_failure_surfaces_copier_stderr(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    answers = tmp_path / ".copier-answers.yml"
    answers.write_text("_src_path: /missing\n")

    with pytest.raises(subprocess.CalledProcessError):
        lifecycle.render_paths(tmp_path / "missing-template", answers)

    assert capsys.readouterr().err.strip()


@pytest.mark.parametrize("operation", ["copy", "update"])
def test_nothing_to_commit_creates_no_commit(work_tree: Path, operation: str):
    repo = GitRepo(work_tree)
    seed = repo.head()

    lifecycle.run(operation, work_tree, verify=RecordingVerify(work_tree), render=_rendered())

    assert repo.head() == seed
    assert repo.subjects() == [SEED_MESSAGE]


@pytest.mark.parametrize("operation", ["copy", "update"])
def test_commits_bypass_failing_hooks(work_tree: Path, operation: str):
    hook = work_tree / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    _add_file(work_tree)

    lifecycle.run(operation, work_tree, verify=RecordingVerify(work_tree), render=_rendered("change.txt"))

    assert len(GitRepo(work_tree).subjects()) == 2
