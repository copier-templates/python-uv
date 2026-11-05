"""Version-vs-tag push gate (Q1-Q13).

`pyproject.toml [project] version` must equal the max-semver plain X.Y.Z tag
reachable from HEAD. Blocks both directions with recovery hints.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from _projects import TEMPLATE_ROOT, ProjectRegistry, load_toml, mise_toml


def _script() -> Path:
    return TEMPLATE_ROOT / "templates" / "scripts" / "check-version-tag.sh"


def test_check_script_exists_executable_guarded_bash():
    script = _script()
    assert script.is_file(), f"Missing check script: {script}"
    assert os.access(script, os.X_OK), f"Check script not executable: {script}"
    content = script.read_text()
    assert content.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in content


def test_check_script_blocks_both_directions_with_hints():
    content = _script().read_text()
    assert "pyproject" in content.lower()
    # Both drift directions must fail with recovery guidance.
    assert "mise run release" in content
    assert "--follow-tags" in content


def test_check_script_help_exits_zero():
    proc = subprocess.run(  # noqa: S603
        [str(_script()), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "pyproject" in proc.stdout.lower()


def test_prek_declares_pre_push_version_tag_hook():
    text = (TEMPLATE_ROOT / "templates" / "prek.toml").read_text()
    assert 'stages = ["pre-push"]' in text
    assert "check-version-tag" in text


def test_mise_tasks_expose_check_version_tag():
    root_tasks = load_toml(TEMPLATE_ROOT / "mise.toml")["tasks"]
    assert "check:version-tag" in root_tasks


def test_rendered_mise_has_check_version_tag(projects: ProjectRegistry):
    data = mise_toml(projects.render("basic"))
    assert "check:version-tag" in data["tasks"]


def test_release_script_shows_local_and_remote_tags():
    content = (TEMPLATE_ROOT / "templates" / "scripts" / "release.sh").read_text()
    assert "ls-remote" in content
    assert "Never push automatically" in content


def test_rendered_project_ships_check_script(projects: ProjectRegistry):
    project = projects.render("basic")
    script = project / "scripts" / "check-version-tag.sh"
    assert script.is_file()
    assert os.access(script, os.X_OK), "Rendered check script must stay executable"
