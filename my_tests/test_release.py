"""Regression tests for the release workflow (`mise run release`)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import tomllib
from conftest import TEMPLATE_ROOT


def _root_script() -> Path:
    return TEMPLATE_ROOT / "scripts" / "release.sh"


def _payload_script() -> Path:
    return TEMPLATE_ROOT / "templates" / "scripts" / "release.sh"


def test_release_scripts_are_identical():
    """Root and payload release scripts must stay byte-identical (verbatim copy)."""
    assert _root_script().read_bytes() == _payload_script().read_bytes()


def test_release_scripts_are_executable_guarded_bash():
    for script in (_root_script(), _payload_script()):
        assert script.is_file(), f"Missing release script: {script}"
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


def test_rendered_mise_has_release_task_and_gum(generated_basic: Path, generated_with_ruff: Path):
    """Both mise.toml variants must pin gum and expose the release task."""
    for project in (generated_basic, generated_with_ruff):
        data = tomllib.loads((project / "mise.toml").read_text())
        assert data["tools"]["gum"] == "2.0.2"
        assert "release" in data["tasks"]
        assert "release.sh" in data["tasks"]["release"]["run"]


def test_release_pins_match_root_mise_toml(generated_basic: Path):
    """Generated pins must match this repo's mise.toml (no drift)."""
    root_tools = tomllib.loads((TEMPLATE_ROOT / "mise.toml").read_text())["tools"]
    generated_tools = tomllib.loads((generated_basic / "mise.toml").read_text())["tools"]
    assert generated_tools["gum"] == root_tools["gum"]
    assert generated_tools["git-cliff"] == root_tools["git-cliff"]


def test_generated_readme_documents_release(generated_basic: Path):
    readme = (generated_basic / "README.md").read_text()
    assert "mise run release" in readme


def test_root_only_scripts_are_absent(generated_basic: Path):
    """Template-dev scripts must not leak; the release script must ship."""
    for rel in ("scripts/lib", "scripts/workflows", "scripts/test-workflow.sh", "scripts/README.md"):
        assert not (generated_basic / rel).exists(), f"Leaked template-dev file: {rel}"
    assert (generated_basic / "scripts" / "release.sh").is_file()
