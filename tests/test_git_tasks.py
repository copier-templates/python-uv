"""Regression tests for the git lifecycle and post-copy verification (`tasks/lifecycle.py`).

Real git in temp dirs with a recording `mise` fake; the Copier wiring is covered by the real renders.
"""

from __future__ import annotations

import os
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


def test_copy_in_plain_directory_inits_repo_and_verifies_after_init_commit(plain_dir: Path):
    mise = RecordingMise(plain_dir)

    lifecycle.run("copy", plain_dir, verify_ci=True, mise=mise)

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

    lifecycle.run(operation, work_tree, verify_ci=False, mise=RecordingMise(work_tree))

    assert _subjects(work_tree) == [message, SEED_MESSAGE]
    assert git(work_tree, "rev-parse", "HEAD~1").stdout.strip() == seed
    assert git(work_tree, "status", "--porcelain").stdout == ""


@pytest.mark.parametrize("operation", ["copy", "update"])
def test_nothing_to_commit_creates_no_commit(work_tree: Path, operation: str):
    seed = _head(work_tree)

    lifecycle.run(operation, work_tree, verify_ci=False, mise=RecordingMise(work_tree))

    assert _head(work_tree) == seed
    assert _subjects(work_tree) == [SEED_MESSAGE]


def test_update_outside_work_tree_does_nothing(plain_dir: Path):
    mise = RecordingMise(plain_dir)

    lifecycle.run("update", plain_dir, verify_ci=True, mise=mise)

    assert not (plain_dir / ".git").exists()
    assert mise.calls == []


@pytest.mark.parametrize("operation", ["copy", "update"])
def test_commits_bypass_failing_hooks(work_tree: Path, operation: str):
    hook = work_tree / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    _add_file(work_tree)

    lifecycle.run(operation, work_tree, verify_ci=False, mise=RecordingMise(work_tree))

    assert len(_subjects(work_tree)) == 2


@pytest.mark.parametrize(
    ("verify_ci", "expected"),
    [(False, [["run", "install"]]), (True, [["run", "install"], ["run", "ci"]])],
    ids=["no-ci", "ci"],
)
def test_verification_runs_install_then_ci_only_when_requested(
    work_tree: Path, verify_ci: bool, expected: list[list[str]]
):
    _add_file(work_tree)
    mise = RecordingMise(work_tree)

    lifecycle.run("copy", work_tree, verify_ci=verify_ci, mise=mise)

    assert mise.calls == expected


@pytest.mark.parametrize(
    ("argv", "operation", "verify_ci"),
    [(["copy", "--verify-ci=True"], "copy", True), (["update"], "update", False)],
    ids=["copy-ci", "update-default-no-ci"],
)
def test_main_dispatches_to_run_in_current_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, argv: list[str], operation: str, verify_ci: bool
):
    seen: dict[str, Any] = {}
    monkeypatch.setattr(lifecycle, "run", lambda op, dst, **kwargs: seen.update(op=op, dst=dst, ci=kwargs["verify_ci"]))
    monkeypatch.chdir(tmp_path)

    assert lifecycle.main(argv) == 0
    assert (seen["op"], seen["dst"].resolve(), seen["ci"]) == (operation, tmp_path.resolve(), verify_ci)
