"""Conditional README sections, pyproject fields and mise.toml task graphs by render variant."""

from __future__ import annotations

import pytest
from _projects import ProjectRegistry, mise_toml, pyproject, refs

BASE_TASKS = {
    "install",
    "lint",
    "lint:shell",
    "lint:workflows",
    "test",
    "test:unit",
    "test:integration",
    "hooks",
    "doctor",
    "bootstrap",
    "ci:docker",
    "changelog",
    "release",
    "clean",
    "clean:all",
}
RUFF_TASKS = {"lint:python", "fix:python", "format", "format:check", "fix", "ci", "ci:full"}


@pytest.mark.parametrize(
    ("variant", "snippet", "present"),
    [
        ("basic", "Running Tests", True),
        ("ruff", "Code Quality", True),
        ("basic", "Code Quality", False),
        ("basic", "img.shields.io/badge/mise", True),
        ("basic", "mise.jdx.dev", True),
    ],
)
def test_readme_sections_follow_dev_deps(projects: ProjectRegistry, variant: str, snippet: str, present: bool):
    readme = (projects.render(variant) / "README.md").read_text()
    assert (snippet in readme) is present


def test_pyproject_preserves_httpx_http2_production_dependency(projects: ProjectRegistry):
    assert pyproject(projects.render("basic"))["project"]["dependencies"] == ["httpx[http2]"]


def test_pyproject_license_fields_follow_license_selection(projects: ProjectRegistry):
    selected = pyproject(projects.render("license"))["project"]
    assert selected["license"] == "MIT"
    assert selected["license-files"] == ["LICENSE"]

    unselected = pyproject(projects.render("basic"))["project"]
    assert "license" not in unselected
    assert "license-files" not in unselected


def test_rendered_license_is_hook_clean(projects: ProjectRegistry):
    """Rendered LICENSE must pass fixer hooks (single trailing newline, no trailing space).

    Regression: the include tag in `LICENSE.jinja` appended its own newline,
    so `end-of-file-fixer` rewrote LICENSE and failed `mise run ci`. The
    fixture copy already runs ci; these assertions pinpoint the file.
    """
    project = projects.render("license-ruff")
    content = (project / "LICENSE").read_bytes()
    assert content, "LICENSE must not be empty"
    assert content.endswith(b"\n") and not content.endswith(b"\n\n"), (
        "LICENSE must end with exactly one newline for end-of-file-fixer"
    )
    text = content.decode("utf-8")
    offenders = [n for n, line in enumerate(text.split("\n"), 1) if line != line.rstrip(" \t")]
    assert not offenders, f"LICENSE has trailing whitespace on lines {offenders}"


@pytest.mark.parametrize(
    ("variant", "tasks", "lint_refs"),
    [
        ("ruff", BASE_TASKS | RUFF_TASKS, ["lint:python", "lint:shell", "lint:workflows"]),
        ("basic", BASE_TASKS, ["lint:shell", "lint:workflows"]),
    ],
)
def test_mise_toml_task_graph_follows_ruff(
    projects: ProjectRegistry, variant: str, tasks: set[str], lint_refs: list[str]
):
    data = mise_toml(projects.render(variant))
    assert set(data["tasks"]) == tasks
    assert refs(data["tasks"]["lint"]) == lint_refs
    assert refs(data["tasks"]["test"]) == ["test:unit", "test:integration"]
    assert data["env"]["_"]["file"] == ".env"


def test_mise_toml_ci_runs_ordered_readonly_steps(projects: ProjectRegistry):
    """CI must run lint, format:check, hooks, test:unit in order via run steps."""
    tasks = mise_toml(projects.render("ruff"))["tasks"]
    assert refs(tasks["ci"]) == ["lint", "format:check", "hooks", "test:unit"]
    assert refs(tasks["ci:full"]) == ["lint", "format:check", "hooks", "test"]
    assert tasks["ci"]["env"]["CI"] == tasks["ci:full"]["env"]["CI"] == "true"


def test_mise_toml_lint_is_check_only_and_fix_task_mutates(projects: ProjectRegistry):
    """Lint must be check-only for CI; mutation lives in fix tasks."""
    tasks = mise_toml(projects.render("ruff"))["tasks"]
    assert tasks["lint:python"]["run"] == "uv run ruff check ."
    assert "ruff check --fix" in tasks["fix:python"]["run"]
    assert tasks["format"]["run"] == "uv run ruff format ."
    assert tasks["format:check"]["run"] == "uv run ruff format --check ."


def test_mise_toml_shell_lint_covers_all_scripts(projects: ProjectRegistry):
    """Shell lint task must discover *.sh files and run shellcheck on them."""
    shell_run = mise_toml(projects.render("ruff"))["tasks"]["lint:shell"]["run"]
    assert "shellcheck" in shell_run
    assert "*.sh" in shell_run


def test_mise_toml_uses_modern_bash(projects: ProjectRegistry):
    """Rendered mise tasks must use modern bash (`[[ ]]`, `(( ))`), not legacy POSIX tests."""
    content = (projects.render("ruff") / "mise.toml").read_text()
    assert "#!/usr/bin/env bash" in content
    assert "((" in content
    assert "[[ -d .github/workflows ]]" in content
    assert "if [ " not in content
    assert "while [ " not in content


def test_mise_toml_agent_entrypoints(projects: ProjectRegistry):
    """Generated projects must expose doctor/bootstrap/hooks/ci:docker/changelog/clean:all.

    Regression: a bare `uv sync` in `install` silently drops dev packages when the
    environment sets `UV_NO_DEV`, leaving `.venv` without pytest so `mise run test`
    fails with `Failed to spawn: pytest`. The explicit `--dev` flag overrides it.
    """
    tasks = mise_toml(projects.render("ruff"))["tasks"]
    assert refs(tasks["bootstrap"]) == ["install", "doctor"]
    assert tasks["bootstrap"]["run"][0] == "mise trust"
    assert "uv sync --dev" in tasks["install"]["run"]
    assert "mise doctor" in tasks["doctor"]["run"]
    assert "prek run --all-files" in tasks["hooks"]["run"]
    assert "act push -j test" in tasks["ci:docker"]["run"]
    assert "git-cliff" in tasks["changelog"]["run"]
    assert ".venv/" in tasks["clean:all"]["run"]
    assert ".venv/" not in tasks["clean"]["run"]


def test_mise_toml_workflows_lint_skips_without_github(projects: ProjectRegistry):
    """Workflow lint must skip gracefully when github_integration is disabled."""
    run = mise_toml(projects.render("no-github"))["tasks"]["lint:workflows"]["run"]
    assert "[[ -d .github/workflows ]]" in run
    assert "No workflows found, skipping." in run


def test_pyproject_configures_ruff_rules_for_generated_projects(projects: ProjectRegistry):
    """Generated pyproject.toml should include the expanded Ruff config."""
    lint = pyproject(projects.render("ruff"))["tool"]["ruff"]["lint"]

    assert {
        "E",
        "W",
        "F",
        "I",
        "Q",
        "B",
        "C4",
        "C90",
        "SIM",
        "DTZ",
        "ARG",
        "PLE",
        "PLW",
        "PLC",
        "UP",
        "S",
    }.issubset(set(lint["select"]))
    assert lint["per-file-ignores"]["tests/unit/**/*.py"] == ["ARG001"]
    assert lint["per-file-ignores"]["tests/**/*.py"] == ["S101", "S105", "S106"]
    assert lint["isort"]["known-first-party"] == ["ruff_proj"]


def test_pyproject_registers_markers_and_package_coverage(projects: ProjectRegistry):
    """Generated packaged projects should register markers and use source_pkgs coverage."""
    tool = pyproject(projects.render("ruff"))["tool"]

    assert tool["pytest"]["ini_options"]["markers"] == [
        "unit: marks tests as unit tests",
        "integration: marks tests as integration tests",
    ]
    assert tool["coverage"]["run"]["source_pkgs"] == ["ruff_proj"]
    assert "source" not in tool["coverage"]["run"]


def test_pyproject_app_configures_pythonpath_for_pytest(projects: ProjectRegistry):
    """App tests import from the root `main` module, so pytest needs `pythonpath = ["."]`.

    Regression: without it `mise run test` fails at collection with
    `ModuleNotFoundError: No module named 'main'`.
    """
    options = pyproject(projects.render("app"))["tool"]["pytest"]["ini_options"]

    assert options["pythonpath"] == ["."]
    assert options["testpaths"] == ["tests"]


def test_pyproject_package_configures_pythonpath_for_src_layout(projects: ProjectRegistry):
    """Packaged projects keep resolving imports from `src`."""
    assert pyproject(projects.render("basic"))["tool"]["pytest"]["ini_options"]["pythonpath"] == ["src"]
