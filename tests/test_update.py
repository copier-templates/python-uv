"""`copier update` behaviour against the git-backed template repo (`git_template_repo`).

The repo carries tags `v1.0.0` (the working tree) and `v1.0.1` (adds `UPDATE_MARKER`
to the README template); projects are generated from `v1.0.0` and updated to `v1.0.1`.
"""

from __future__ import annotations

import re
from pathlib import Path

from _projects import (
    BASE_DATA,
    GIT_IDENTITY,
    PYTHON_VERSION_ANSWER_LINE,
    UPDATE_MARKER,
    git,
    mise_tools,
    run_copy_from,
)
from copier import run_update
from plumbum import local


def test_update_restores_python_version_for_legacy_project(git_template_repo: Path, tmp_path: Path):
    """`copier update` must re-ask the new question and template it from the default.

    Simulates a project generated from `v1.0.0` whose answers file predates the
    `python_version` question: the answer is dropped, then the project is updated
    to `v1.0.1`, which must restore the answer and the rendered pins.
    """
    data = BASE_DATA | {"project_name": "update_proj"}
    project = run_copy_from(git_template_repo, tmp_path / "update", data, vcs_ref="v1.0.0")

    answers_path = project / ".copier-answers.yml"
    answers, dropped = re.subn(r"(?m)^python_version:.*\n", "", answers_path.read_text())
    assert dropped == 1, "the v1.0.0 render should record exactly one python_version answer to drop"
    answers_path.write_text(answers)

    with local.env(**GIT_IDENTITY):
        git(project, "add", "-A")
        git(project, "commit", "-m", "drop python_version answer")
        run_update(str(project), defaults=True, overwrite=True, unsafe=True)

    restored = answers_path.read_text()
    assert re.search(PYTHON_VERSION_ANSWER_LINE.format(version=r"3\.12"), restored), (
        f"copier update must restore the python_version answer:\n{restored}"
    )
    assert mise_tools(project)["python"] == "3.12", "updated project must pin the default Python in mise.toml"
    assert UPDATE_MARKER in (project / "README.md").read_text(), (
        "copier update must apply the v1.0.1 template change to README.md"
    )
