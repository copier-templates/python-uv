"""Root-to-template sync guards: symlinks, workflow mirrors, tool pins and the task wiring."""

from __future__ import annotations

import pytest
from _projects import LOCAL_TASKS, SHARED_CATEGORIES, SHARED_REF, TEMPLATE_ROOT, ProjectRegistry, load_toml

SYMLINKED_ROOT_PATHS = [
    "prek.toml",
    "cliff.toml",
    "taplo.toml",
    ".editorconfig",
    "scripts/release.py",
    "scripts/check_version_tag.py",
    "scripts/sync_shared_refs.py",
    "scripts/_version.py",
]  # noqa: SIM905

SHARED_REPO_URL = "https://github.com/copier-templates/shared-dev-tooling.git"
SHARED_PREK_REPO = "https://github.com/copier-templates/shared-dev-tooling"
SHARED_INCLUDES = [f"git::{SHARED_REPO_URL}//tasks/{category}?ref={SHARED_REF}" for category in SHARED_CATEGORIES]
MIN_MISE_VERSION = (2026, 11, 10)


@pytest.mark.parametrize("source", ["root", "rendered"])
def test_mise_imports_shared_task_categories(source: str, projects: ProjectRegistry):
    """Root and rendered mise.toml import the shared core/toml/py/cicd/release tasks under experimental includes."""
    data = load_toml(TEMPLATE_ROOT / "mise.toml") if source == "root" else projects.render("lib-licensed").mise()
    includes = data.get("task_config", {}).get("includes", [])
    assert set(SHARED_INCLUDES) <= set(includes)
    shared_refs = {include.split("?ref=", 1)[1] for include in includes if SHARED_REPO_URL in include}
    assert shared_refs == {SHARED_REF}, f"shared includes must pin one ref: {shared_refs}"
    assert data.get("settings", {}).get("experimental") is True
    min_version = data.get("min_version", "0.0.0")
    assert tuple(int(part) for part in min_version.split(".")) >= MIN_MISE_VERSION


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


@pytest.mark.parametrize("source", ["root", "rendered"])
def test_local_mise_tasks_are_only_thin_wrappers(source: str, projects: ProjectRegistry):
    """Only bootstrap and release remain local; everything else is shared."""
    data = load_toml(TEMPLATE_ROOT / "mise.toml") if source == "root" else projects.render("lib-licensed").mise()
    tasks = data["tasks"]
    assert set(tasks) == LOCAL_TASKS, sorted(set(tasks) - LOCAL_TASKS)
    assert tasks["bootstrap"]["run"] == ["mise trust", {"task": "setup"}, {"task": "mise:doctor"}]
    assert tasks["release"]["run"] == "uv run python scripts/release.py"
    assert not {"lint:python", "format", "test:unit", "clean", "gh:lint", "lint:workflows"} & set(tasks)
