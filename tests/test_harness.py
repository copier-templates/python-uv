"""Regression tests for the harness: the template snapshot and the render cache."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from _projects import ProjectRegistry, git, snapshot_template_root


@pytest.fixture
def snapshot_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Git repo with tracked, executable, symlinked, untracked, ignored, and deleted-but-tracked files."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    (repo / ".gitignore").write_text("junk/\n", encoding="utf-8")
    (repo / "gone.txt").write_text("deleted\n", encoding="utf-8")
    (repo / "run.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (repo / "run.sh").chmod(0o755)
    (repo / "link.sh").symlink_to("run.sh")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "init")
    (repo / "gone.txt").unlink()
    (repo / "untracked.txt").write_text("untracked\n", encoding="utf-8")
    (repo / "junk").mkdir()
    (repo / "junk" / "leftover.pyc").write_text("ignored\n", encoding="utf-8")
    return repo


def test_snapshot_holds_what_git_would_commit(tmp_path: Path, snapshot_repo: Path) -> None:
    """Tracked + untracked-non-ignored files, minus deleted ones; modes kept and symlinks not dereferenced."""
    snapshot = snapshot_template_root(tmp_path / "snapshot", snapshot_repo)

    files = {path.relative_to(snapshot).as_posix() for path in snapshot.rglob("*") if path.is_file()}
    assert files == {".gitignore", "run.sh", "link.sh", "untracked.txt"}
    assert stat.S_IMODE((snapshot / "run.sh").stat().st_mode) == 0o755
    assert os.readlink(snapshot / "link.sh") == "run.sh"


def test_render_caches_identical_calls(projects: ProjectRegistry) -> None:
    """A second render of the same variant reuses the first directory."""
    assert projects.render("basic") == projects.render("basic")
