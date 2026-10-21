"""Regression tests for git-cliff bootstrapping.

`cliff.toml` must ship both in this repo and in generated projects (verbatim
payload under `templates/`, mirroring the `prek.toml` precedent), and the
`git-cliff` tool pin must stay in sync between both `mise.toml` files.
"""

from __future__ import annotations

from pathlib import Path

import tomllib
from conftest import TEMPLATE_ROOT


def test_generated_cliff_toml_exists_and_is_valid(generated_basic: Path):
    """Generated projects must ship a parseable git-cliff config."""
    cliff = generated_basic / "cliff.toml"
    assert cliff.is_file(), "Missing generated cliff.toml"
    data = tomllib.loads(cliff.read_text())
    assert "changelog" in data
    assert "body" in data["changelog"]
    assert data["git"]["conventional_commits"] is True


def test_generated_readme_documents_changelog(generated_basic: Path):
    """Generated README must point at the changelog task."""
    readme = (generated_basic / "README.md").read_text()
    assert "mise run changelog" in readme


def test_cliff_toml_stays_in_sync():
    """Root and template-payload cliff.toml must be identical (verbatim copy)."""
    root = (TEMPLATE_ROOT / "cliff.toml").read_text()
    payload = (TEMPLATE_ROOT / "templates" / "cliff.toml").read_text()
    assert root == payload, "cliff.toml drifted from templates/cliff.toml"


def test_git_cliff_pin_matches_root_mise_toml(generated_basic: Path):
    """Generated mise.toml must pin the same git-cliff version as this repo."""
    root_pin = tomllib.loads((TEMPLATE_ROOT / "mise.toml").read_text())["tools"]["git-cliff"]
    generated_pin = tomllib.loads((generated_basic / "mise.toml").read_text())["tools"]["git-cliff"]
    assert generated_pin == root_pin
