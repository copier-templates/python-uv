"""Regression tests for the release workflow (`mise run release`)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from _projects import TEMPLATE_ROOT, ProjectRegistry, mise_toml


def _root_script() -> Path:
    return TEMPLATE_ROOT / "scripts" / "release.sh"


def test_release_script_is_executable_guarded_bash():
    script = _root_script()
    assert os.access(script, os.X_OK), f"Release script not executable: {script}"
    content = script.read_text()
    assert content.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in content


def test_release_script_help_exits_zero():
    proc = subprocess.run(  # noqa: S603
        [str(_root_script()), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "--version" in proc.stdout
    assert "--yes" in proc.stdout


def test_release_script_rejects_unknown_flags():
    proc = subprocess.run(  # noqa: S603
        [str(_root_script()), "--bogus"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2


def test_act_image_reference_is_canonical():
    """All ACT-image references must use the same registryless image."""
    canonical = 'ACT_IMAGE="catthehacker/ubuntu:act-24.04"'
    scripts = (
        TEMPLATE_ROOT / "scripts" / "workflows" / "prek.sh",
        TEMPLATE_ROOT / "scripts" / "workflows" / "test.sh",
        TEMPLATE_ROOT / "scripts" / "test-workflow.sh",
    )
    for script in scripts:
        assert script.is_file(), f"Missing script: {script}"
        content = script.read_text()
        if "ACT_IMAGE=" in content:
            assert canonical in content, f"Non-canonical ACT_IMAGE in {script}"
        assert "ghcr.io" not in content, f"ghcr.io reference in {script}"


def test_rendered_mise_has_release_task_and_gum(projects: ProjectRegistry):
    """Both mise.toml variants must pin gum and expose the release task."""
    for project in (projects.render("basic"), projects.render("ruff")):
        data = mise_toml(project)
        assert "gum" in data["tools"]
        assert "release" in data["tasks"]
        assert "release.sh" in data["tasks"]["release"]["run"]


def test_generated_readme_documents_release(projects: ProjectRegistry):
    project = projects.render("basic")
    readme = (project / "README.md").read_text()
    assert "mise run release" in readme


def test_root_only_scripts_are_absent(projects: ProjectRegistry):
    """Template-dev scripts must not leak; the release script must ship."""
    project = projects.render("basic")
    for rel in (
        "scripts/lib",
        "scripts/workflows",
        "scripts/test-workflow.sh",
        "scripts/README.md",
        "scripts/update_python_versions.py",
    ):
        assert not (project / rel).exists(), f"Leaked template-dev file: {rel}"
    assert (project / "scripts" / "release.sh").is_file()
