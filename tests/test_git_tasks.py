"""Regression tests for the git lifecycle and post-copy verification (`tasks/lifecycle.py`).

Real git in temp dirs with a recording `mise` fake; the Copier wiring is covered by the real renders.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import lifecycle
import pytest
from _projects import GIT_IDENTITY, git

SEED_MESSAGE = "seed"


@pytest.fixture
def plain_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A non-git destination holding a scaffold file, with an explicit git identity and no global/system config."""
    for key, value in GIT_IDENTITY.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    dst = tmp_path / "project"
    dst.mkdir()
    (dst / "README.md").write_text("scaffold\n")
    return dst


@pytest.fixture
def work_tree(plain_dir: Path) -> Path:
    """A clean git work tree whose only commit is `seed`."""
    git(plain_dir, "init")
    git(plain_dir, "add", "-A")
    git(plain_dir, "commit", "-m", SEED_MESSAGE)
    return plain_dir


class RecordingMise:
    """Fake `mise` runner that records calls and fails if no commit exists yet."""

    def __init__(self, dst: Path) -> None:
        self.dst = dst
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> None:
        git(self.dst, "rev-parse", "--verify", "HEAD")
        self.calls.append(list(args))


def _subjects(dst: Path) -> list[str]:
    """Commit subjects, newest first."""
    return git(dst, "log", "--format=%s").stdout.splitlines()


def _head(dst: Path) -> str:
    return git(dst, "rev-parse", "HEAD").stdout.strip()


def _add_file(dst: Path) -> None:
    (dst / "change.txt").write_text("change\n")


def _rendered(*paths: str) -> Callable[[], set[str]]:
    """Stub for the lazy render step: the set of paths Copier produced."""
    return lambda: set(paths)


def test_copy_in_plain_directory_inits_repo_and_verifies_after_init_commit(plain_dir: Path):
    mise = RecordingMise(plain_dir)

    lifecycle.run("copy", plain_dir, mise=mise, render=_rendered("README.md"))

    assert _subjects(plain_dir) == [lifecycle.INIT_MESSAGE]
    assert git(plain_dir, "ls-files").stdout.split() == ["README.md"]
    assert mise.calls == [["run", "install"], ["run", "ci"]]


@pytest.mark.parametrize(
    ("operation", "message"),
    [("copy", lifecycle.SCAFFOLD_MESSAGE), ("update", lifecycle.UPDATE_MESSAGE)],
)
def test_work_tree_changes_are_committed_on_top_of_existing_history(work_tree: Path, operation: str, message: str):
    seed = _head(work_tree)
    _add_file(work_tree)

    lifecycle.run(operation, work_tree, mise=RecordingMise(work_tree), render=_rendered("change.txt"))

    assert _subjects(work_tree) == [message, SEED_MESSAGE]
    assert git(work_tree, "rev-parse", "HEAD~1").stdout.strip() == seed
    assert git(work_tree, "status", "--porcelain").stdout == ""


def test_only_rendered_files_are_committed(work_tree: Path):
    _add_file(work_tree)
    (work_tree / "user-notes.md").write_text("mine\n")

    lifecycle.run("copy", work_tree, mise=RecordingMise(work_tree), render=_rendered("change.txt"))

    assert git(work_tree, "show", "--name-only", "--format=", "HEAD").stdout.split() == ["change.txt"]
    assert git(work_tree, "status", "--porcelain").stdout == "?? user-notes.md\n"


def test_modified_rendered_file_is_committed_on_update(work_tree: Path):
    (work_tree / "README.md").write_text("updated\n")

    lifecycle.run("update", work_tree, mise=RecordingMise(work_tree), render=_rendered("README.md"))

    assert git(work_tree, "show", "--name-only", "--format=", "HEAD").stdout.split() == ["README.md"]


def test_rendered_paths_missing_from_destination_are_skipped(work_tree: Path):
    _add_file(work_tree)

    lifecycle.run("copy", work_tree, mise=RecordingMise(work_tree), render=_rendered("change.txt", "missing/file.py"))

    assert git(work_tree, "show", "--name-only", "--format=", "HEAD").stdout.split() == ["change.txt"]


def test_rendered_files_matched_by_gitignore_are_still_committed(work_tree: Path):
    (work_tree / ".gitignore").write_text("ignored.txt\n")
    (work_tree / "ignored.txt").write_text("rendered\n")

    lifecycle.run("copy", work_tree, mise=RecordingMise(work_tree), render=_rendered("ignored.txt"))

    assert git(work_tree, "show", "--name-only", "--format=", "HEAD").stdout.split() == ["ignored.txt"]


def test_staged_files_are_printed_before_commit(work_tree: Path, capsys: pytest.CaptureFixture[str]):
    _add_file(work_tree)

    lifecycle.run("copy", work_tree, mise=RecordingMise(work_tree), render=_rendered("change.txt"))

    assert "A\tchange.txt" in capsys.readouterr().out


@pytest.mark.parametrize("operation", ["copy", "update"])
def test_nothing_to_commit_creates_no_commit(work_tree: Path, operation: str):
    seed = _head(work_tree)

    lifecycle.run(operation, work_tree, mise=RecordingMise(work_tree), render=_rendered())

    assert _head(work_tree) == seed
    assert _subjects(work_tree) == [SEED_MESSAGE]


def test_update_outside_work_tree_does_nothing(plain_dir: Path):
    mise = RecordingMise(plain_dir)

    lifecycle.run("update", plain_dir, mise=mise, render=_rendered())

    assert not (plain_dir / ".git").exists()
    assert mise.calls == []


@pytest.mark.parametrize("operation", ["copy", "update"])
def test_commits_bypass_failing_hooks(work_tree: Path, operation: str):
    hook = work_tree / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    _add_file(work_tree)

    lifecycle.run(operation, work_tree, mise=RecordingMise(work_tree), render=_rendered("change.txt"))

    assert len(_subjects(work_tree)) == 2


@pytest.mark.parametrize("operation", ["copy", "update"])
def test_main_dispatches_to_run_in_current_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, operation: str):
    seen: dict[str, Any] = {}
    monkeypatch.setattr(lifecycle, "run", lambda op, dst, **kwargs: seen.update(op=op, dst=dst, **kwargs))
    monkeypatch.chdir(tmp_path)

    assert lifecycle.main([operation, "--src", "/tpl", "--answers", ".copier-answers.yml"]) == 0
    assert (seen["op"], seen["dst"].resolve()) == (operation, tmp_path.resolve())
    assert callable(seen["render"])
