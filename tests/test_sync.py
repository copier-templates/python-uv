"""Root-to-template sync guards.

Root tooling files that also ship in the payload are symlinks into
`templates/` (one source of truth). Workflows are byte copies because GitHub
Actions does not reliably follow symlinked workflow files. Tool pins and the
mise task-name contract are checked against a rendered project.
"""

from __future__ import annotations

import difflib

import pytest
from _projects import TEMPLATE_ROOT, ProjectRegistry, load_toml, mise_toml

SYMLINKED_ROOT_PATHS = ["prek.toml", "cliff.toml", ".editorconfig", "scripts/release.sh"]

# Task names shared by root `mise.toml` and every full-tooling generated project.
TASK_CONTRACT = frozenset(
    {"lint", "lint:python", "lint:shell", "format", "test:unit", "test:integration", "test", "ci", "clean"}
)


@pytest.mark.parametrize("rel_path", SYMLINKED_ROOT_PATHS)
def test_root_file_is_symlink_into_templates(rel_path: str):
    root = TEMPLATE_ROOT / rel_path
    assert root.is_symlink(), f"{rel_path} must be a symlink; edit templates/{rel_path}"
    assert root.resolve() == (TEMPLATE_ROOT / "templates" / rel_path).resolve()


def test_workflow_files_stay_in_sync():
    """Workflow filename sets match and each pair is byte-identical (copies, not symlinks)."""
    root_dir = TEMPLATE_ROOT / ".github" / "workflows"
    payload_dir = TEMPLATE_ROOT / "templates" / ".github" / "workflows"
    root_names = {p.name for p in root_dir.glob("*.yml")}
    payload_names = {p.name for p in payload_dir.glob("*.yml")}
    assert root_names, f"Expected at least one workflow file in {root_dir}"
    assert root_names == payload_names, (
        f"Workflow sets drifted: root-only={sorted(root_names - payload_names)}, "
        f"payload-only={sorted(payload_names - root_names)}"
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
    """Rendered `[tools]` equals root `[tools]` for every tool except `python`."""
    rendered = mise_toml(projects.render("ruff"))["tools"]
    root = load_toml(TEMPLATE_ROOT / "mise.toml")["tools"]
    rendered.pop("python")
    root.pop("python")
    assert rendered == root


def test_mise_task_contract(projects: ProjectRegistry):
    root_tasks = set(load_toml(TEMPLATE_ROOT / "mise.toml")["tasks"])
    rendered_tasks = set(mise_toml(projects.render("ruff"))["tasks"])
    assert root_tasks >= TASK_CONTRACT, sorted(TASK_CONTRACT - root_tasks)
    assert rendered_tasks >= TASK_CONTRACT, sorted(TASK_CONTRACT - rendered_tasks)
