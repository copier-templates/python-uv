"""Root-to-template sync guards: symlinks, workflow mirrors, tool pins and the task wiring."""

from __future__ import annotations

import difflib

import pytest
from _projects import LOCAL_TASKS, SHARED_REF, SHARED_REFS, TEMPLATE_ROOT, ProjectRegistry, load_toml

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
SHARED_INCLUDES = [f"git::{SHARED_REPO_URL}//tasks/{category}?ref={ref}" for category, ref in SHARED_REFS.items()]
MIN_MISE_VERSION = (2026, 11, 10)


@pytest.mark.parametrize("source", ["root", "rendered"])
def test_mise_imports_shared_task_categories(source: str, projects: ProjectRegistry):
    """Root and rendered mise.toml import the shared core/toml/py/cicd tasks, each at its own ref."""
    data = load_toml(TEMPLATE_ROOT / "mise.toml") if source == "root" else projects.render("basic").mise()
    includes = data.get("task_config", {}).get("includes", [])
    assert set(SHARED_INCLUDES) <= set(includes)
    refs = {
        include.split("//tasks/", 1)[1].split("?ref=", 1)[0]: include.split("?ref=", 1)[1]
        for include in includes
        if SHARED_REPO_URL in include
    }
    assert refs == SHARED_REFS, f"shared includes drifted from their per-category refs: {refs}"
    assert data.get("settings", {}).get("experimental") is True
    min_version = data.get("min_version", "0.0.0")
    assert tuple(int(part) for part in min_version.split(".")) >= MIN_MISE_VERSION


@pytest.mark.parametrize("source", ["root", "rendered"])
def test_shared_include_refs_match_prek_rev(source: str, projects: ProjectRegistry):
    """Prek pins the newest shared include ref and blocks updates outside the managed ref set."""
    data = load_toml(TEMPLATE_ROOT / "mise.toml") if source == "root" else projects.render("basic").mise()
    includes = data.get("task_config", {}).get("includes", [])
    shared_includes = [include for include in includes if SHARED_PREK_REPO in include]
    assert shared_includes, "shared task includes must be present"
    assert all("?ref=" in include for include in shared_includes), (
        f"every shared task include must pin a ref: {shared_includes}"
    )
    refs = {include.split("?ref=", 1)[1] for include in shared_includes}
    assert refs == set(SHARED_REFS.values())
    prek = load_toml(TEMPLATE_ROOT / "templates" / "prek.toml")
    shared_repos = [repo for repo in prek["repos"] if repo["repo"] == SHARED_PREK_REPO]
    assert shared_repos, "prek.toml must pin the shared hooks repo"
    assert shared_repos[0]["rev"] == SHARED_REF
    assert set(prek["update"]["repos"][SHARED_PREK_REPO]["include_tags"]) == set(SHARED_REFS.values())


def test_rendered_readme_documents_the_mise_floor(projects: ProjectRegistry):
    """Generated README prerequisites state the mise floor and why experimental mode is required."""
    readme = projects.render("basic").read("README.md")
    prerequisites = readme.split("## Installation", 1)[0]
    assert "2026.11.10" in prerequisites
    assert "experimental" in prerequisites


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


@pytest.mark.parametrize("source", ["root", "rendered"])
def test_local_mise_tasks_are_only_thin_wrappers(source: str, projects: ProjectRegistry):
    """Only bootstrap and release remain local; everything else is shared."""
    data = load_toml(TEMPLATE_ROOT / "mise.toml") if source == "root" else projects.render("lib-licensed").mise()
    tasks = data["tasks"]
    assert set(tasks) == LOCAL_TASKS, sorted(set(tasks) - LOCAL_TASKS)
    assert tasks["bootstrap"]["run"] == ["mise trust", {"task": "setup"}, {"task": "mise:doctor"}]
    assert tasks["release"]["run"] == "uv run python scripts/release.py"
    assert not {"lint:python", "format", "test:unit", "clean", "gh:lint", "lint:workflows"} & set(tasks)


def test_pre_push_hook_keeps_the_version_tag_gate():
    """The shared hooks bump must not drop the pre-push version-tag enforcement."""
    prek = load_toml(TEMPLATE_ROOT / "templates" / "prek.toml")
    hooks = {hook["id"]: hook for repo in prek["repos"] for hook in repo["hooks"]}
    hook = hooks["check-version-tag"]
    assert hook["stages"] == ["pre-push"]
    assert hook["entry"] == "uv run python scripts/check_version_tag.py"


def test_payload_gitattributes_drops_the_shell_rule():
    """Python scripts replace the shell payload, so the `*.sh` line-ending rule is gone."""
    gitattributes = (TEMPLATE_ROOT / "templates" / ".gitattributes.jinja").read_text()
    assert "*.sh" not in gitattributes
    assert "*.py text eol=lf" in gitattributes
