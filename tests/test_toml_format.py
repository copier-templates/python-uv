"""TOML formatting gate (taplo): all `*.toml` stay formatted via the prek hook.

Design: taplo runs only as a prek fixer hook (`taplo-format`, files
`\\.toml$`) — never as a mise task — so `mise run format`/`format:check`
stay Ruff-only while every TOML file is autofixed on commit.
`templates/**/*.jinja` is not valid TOML and never matches the hook filter.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest
from _projects import TEMPLATE_ROOT, ProjectRegistry, load_toml, mise_toml


def _taplo() -> str:
    path = shutil.which("taplo")
    assert path is not None, "taplo must be on PATH (mise toolchain)"
    return path


def test_taplo_pinned_in_root_and_rendered_tools(projects: ProjectRegistry):
    root_tools = load_toml(TEMPLATE_ROOT / "mise.toml")["tools"]
    assert "taplo" in root_tools
    rendered_tools = mise_toml(projects.render("basic"))["tools"]
    assert rendered_tools.get("taplo") == root_tools["taplo"]


def test_mise_tasks_have_no_taplo():
    """taplo lives only in the prek hook; mise format tasks stay Ruff-only."""
    tasks = load_toml(TEMPLATE_ROOT / "mise.toml")["tasks"]
    assert "taplo" not in str(tasks["format"]["run"])
    assert "taplo" not in str(tasks["format:check"]["run"])


def test_rendered_mise_tasks_have_no_taplo(projects: ProjectRegistry):
    tasks = mise_toml(projects.render("basic"))["tasks"]
    assert "taplo" not in str(tasks["format"]["run"])
    assert "taplo" not in str(tasks["format:check"]["run"])


def test_prek_declares_taplo_fixer_with_own_tier():
    config = load_toml(TEMPLATE_ROOT / "templates" / "prek.toml")
    hooks = {hook["id"]: hook for repo in config["repos"] for hook in repo["hooks"]}
    assert "taplo-format" in hooks
    hook = hooks["taplo-format"]
    assert hook.get("priority") in config["priorities"]
    assert config["priorities"][hook["priority"]] < config["priorities"]["checks"]
    assert hook.get("files") == "\\.toml$"


def test_all_root_toml_files_are_taplo_clean():
    owned = sorted(p.name for p in TEMPLATE_ROOT.glob("*.toml"))
    assert owned, "expected root *.toml files"
    proc = subprocess.run(  # noqa: S603
        [_taplo(), "format", "--check", *owned],
        check=False,
        capture_output=True,
        text=True,
        cwd=TEMPLATE_ROOT,
    )
    assert proc.returncode == 0, f"taplo wants to reformat:\n{proc.stdout}\n{proc.stderr}"


@pytest.mark.parametrize("rel_path", ["prek.toml", "pyproject.toml", "cliff.toml", "mise.toml"])
def test_owned_toml_files_parse(rel_path: str):
    load_toml(TEMPLATE_ROOT / rel_path)
