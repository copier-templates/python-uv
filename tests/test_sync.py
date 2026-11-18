"""Root-to-template sync guards: symlinks, workflow mirrors, tool pins and the task contract."""

from __future__ import annotations

import difflib

import pytest
from _projects import TEMPLATE_ROOT, ProjectRegistry, load_toml

SYMLINKED_ROOT_PATHS = [
    "prek.toml",
    "cliff.toml",
    "taplo.toml",
    ".editorconfig",
    "scripts/release.py",
    "scripts/check_version_tag.py",
]  # noqa: SIM905

# Task names shared by root `mise.toml` and every full-tooling generated project.
TASK_CONTRACT = frozenset(
    {
        "lint",
        "lint:python",
        "lint:types",
        "format",
        "test:unit",
        "test:integration",
        "test",
        "ci",
        "clean",
    }
)


@pytest.mark.parametrize("rel_path", SYMLINKED_ROOT_PATHS)
def test_root_file_is_symlink_into_templates(rel_path: str):
    root = TEMPLATE_ROOT / rel_path
    assert root.is_symlink(), f"{rel_path} must be a symlink; edit templates/{rel_path}"
    assert root.resolve() == (TEMPLATE_ROOT / "templates" / rel_path).resolve()


def test_workflow_files_stay_in_sync():
    root_dir = TEMPLATE_ROOT / ".github" / "workflows"
    payload_dir = TEMPLATE_ROOT / "templates" / ".github" / "workflows"
    root_names = {p.name for p in root_dir.glob("*.yml")}
    payload_names = {p.name for p in payload_dir.glob("*.yml")}
    assert root_names, f"Expected at least one workflow file in {root_dir}"
    assert root_names == payload_names, (
        f"Workflow sets drifted: root-only={sorted(root_names - payload_names)}, payload-only={sorted(payload_names - root_names)}"
    )
    for name in sorted(root_names):
        root, payload = root_dir / name, payload_dir / name
        if root.read_bytes() != payload.read_bytes():
            diff = "\n".join(
                difflib.unified_diff(
                    root.read_text().splitlines(),
                    payload.read_text().splitlines(),
                    fromfile=f".github/workflows/{name}",
                    tofile=f"templates/.github/workflows/{name}",
                    lineterm="",
                )
            )
            raise AssertionError(f"{name} drifted from its template payload:\n{diff}")


def test_tool_pins_match_root_mise_toml(projects: ProjectRegistry):
    """Rendered pins must resolve the root pins.

    Root `mise.toml` may keep a partial pin (`prek = "0.5"`) while the payload ships the resolved
    release (`prek = "0.5.6"`). The guard accepts an exact match or a dotted suffix on the root
    pin, and nothing looser: a removed tool, or a major/minor drift (`0.5` vs `0.4`/`0.6`), still fails.
    """
    rendered = projects.render("basic").mise_tools()
    root = load_toml(TEMPLATE_ROOT / "mise.toml")["tools"]
    tools = (set(rendered) | set(root)) - {"python"}
    assert set(rendered) - {"python"} == set(root) - {"python"}, tools
    drifted = {
        tool: (root[tool], rendered[tool])
        for tool in tools
        # Only a dotted suffix may extend the root pin: `0.5` -> `0.5.6` passes, `0.5` -> `0.4.0`/`0.6.0` does not.
        if not (rendered[tool] == root[tool] or rendered[tool].startswith(root[tool] + "."))
    }
    assert not drifted, f"tool pin drift: {drifted}"


def test_mise_task_contract(projects: ProjectRegistry):
    root_tasks = set(load_toml(TEMPLATE_ROOT / "mise.toml")["tasks"])
    rendered_tasks = set(projects.render("basic").mise()["tasks"])
    assert root_tasks >= TASK_CONTRACT, sorted(TASK_CONTRACT - root_tasks)
    assert "lint:workflows" in root_tasks, "root keeps the actionlint task for CI workflows"
    assert rendered_tasks >= TASK_CONTRACT, sorted(TASK_CONTRACT - rendered_tasks)


def test_payload_gitattributes_drops_the_shell_rule():
    """Python scripts replace the shell payload, so the `*.sh` line-ending rule is gone."""
    gitattributes = (TEMPLATE_ROOT / "templates" / ".gitattributes.jinja").read_text()
    assert "*.sh" not in gitattributes
    assert "*.py text eol=lf" in gitattributes
