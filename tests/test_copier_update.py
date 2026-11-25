"""`copier update` against the git-backed template repo: `v1.0.0` renders, `v1.0.1` adds `UPDATE_MARKER`."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from _projects import (
    BASE_DATA,
    GIT_ENV,
    PYTHON_VERSION_ANSWER_LINE,
    UPDATE_MARKER,
    GitRepo,
    RenderedProject,
    run_copy_from,
)
from copier import run_update


def test_update_restores_python_version_for_legacy_project(
    git_template_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A legacy project without the answer or pin gets both back, and the update commit carries the pin."""
    for key, value in GIT_ENV.items():
        monkeypatch.setenv(key, value)
    data = BASE_DATA | {"project_name": "update_proj"}
    path = run_copy_from(git_template_repo, tmp_path / "update", data, vcs_ref="v1.0.0", skip_tasks=True)
    project = RenderedProject(path, data)

    answers_path = path / ".copier-answers.yml"
    answers, dropped = re.subn(r"(?m)^python_version:.*\n", "", answers_path.read_text())
    assert dropped == 1, "the v1.0.0 render should record exactly one python_version answer to drop"
    answers_path.write_text(answers)
    assert not (path / ".python-version").exists(), "the legacy render must start without a uv pin"

    GitRepo.init(path).commit_all("drop python_version answer and pin")
    run_update(str(path), defaults=True, overwrite=True, unsafe=True)

    restored = answers_path.read_text()
    assert re.search(PYTHON_VERSION_ANSWER_LINE.format(version=r"3\.12"), restored), (
        f"copier update must restore the python_version answer:\n{restored}"
    )
    assert project.repo().subjects()[0] == "chore: update from copier template"
    assert "python" not in project.mise_tools(), "updated project must not pin Python in mise.toml"
    assert UPDATE_MARKER in project.read("README.md"), (
        "copier update must apply the v1.0.1 template change to README.md"
    )
    committed = project.repo().files()
    assert ".python-version" in committed, f"update commit must carry the restored pin: {committed}"
    assert project.repo().run("show", "HEAD:.python-version").stdout == "3.12\n", "the update commit must carry the pin"
