"""Rendered pyproject fields, README sections and mise.toml task graph: always-on tooling and real variance."""

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
    "lint:python",
    "fix:python",
    "format",
    "format:check",
    "fix",
    "ci",
    "ci:full",
}


@pytest.mark.parametrize("snippet", ["Running Tests", "Code Quality", "img.shields.io/badge/mise", "mise.jdx.dev"])
def test_readme_always_documents_tests_and_quality(projects: ProjectRegistry, snippet: str):
    assert snippet in (projects.render("basic") / "README.md").read_text()


def test_default_render_always_includes_pytest_cov_and_ruff_tooling(projects: ProjectRegistry):
    project = projects.render("basic")

    assert pyproject(project)["dependency-groups"]["dev"] == ["pytest", "pytest-cov", "ruff"]
    tool = pyproject(project)["tool"]
    assert {"pytest", "coverage", "ruff"} <= set(tool)
    assert any(opt.startswith("--cov=") for opt in tool["pytest"]["ini_options"]["addopts"])


def test_extra_dev_deps_are_appended_to_the_always_on_tooling(projects: ProjectRegistry):
    dev = pyproject(projects.render("extra-dev-deps"))["dependency-groups"]["dev"]

    assert dev == ["pytest", "pytest-cov", "ruff", "hypothesis>=6"]


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
    project = projects.render("license")
    content = (project / "LICENSE").read_bytes()
    assert content, "LICENSE must not be empty"
    assert content.endswith(b"\n") and not content.endswith(b"\n\n"), (
        "LICENSE must end with exactly one newline for end-of-file-fixer"
    )
    text = content.decode("utf-8")
    offenders = [n for n, line in enumerate(text.split("\n"), 1) if line != line.rstrip(" \t")]
    assert not offenders, f"LICENSE has trailing whitespace on lines {offenders}"


def test_mise_toml_task_graph_is_always_complete(projects: ProjectRegistry):
    data = mise_toml(projects.render("basic"))
    assert set(data["tasks"]) == BASE_TASKS
    assert refs(data["tasks"]["lint"]) == ["lint:python", "lint:shell", "lint:workflows"]
    assert refs(data["tasks"]["test"]) == ["test:unit", "test:integration"]
    assert data["env"]["_"]["file"] == ".env"


def test_mise_toml_ci_runs_ordered_readonly_steps(projects: ProjectRegistry):
    """CI must run lint, format:check, hooks, test:unit in order via run steps."""
    tasks = mise_toml(projects.render("basic"))["tasks"]
    assert refs(tasks["ci"]) == ["lint", "format:check", "hooks", "test:unit"]
    assert refs(tasks["ci:full"]) == ["lint", "format:check", "hooks", "test"]
    assert tasks["ci"]["env"]["CI"] == tasks["ci:full"]["env"]["CI"] == "true"


def test_mise_toml_lint_is_check_only_and_fix_task_mutates(projects: ProjectRegistry):
    """Lint must be check-only for CI; mutation lives in fix tasks."""
    tasks = mise_toml(projects.render("basic"))["tasks"]
    assert tasks["lint:python"]["run"] == "uv run ruff check ."
    assert "ruff check --fix" in tasks["fix:python"]["run"]
    assert tasks["format"]["run"] == "uv run ruff format ."
    assert tasks["format:check"]["run"] == "uv run ruff format --check ."


def test_mise_toml_shell_lint_covers_all_scripts(projects: ProjectRegistry):
    """Shell lint task must discover *.sh files and run shellcheck on them."""
    shell_run = mise_toml(projects.render("basic"))["tasks"]["lint:shell"]["run"]
    assert "shellcheck" in shell_run
    assert "*.sh" in shell_run


def test_mise_toml_uses_modern_bash(projects: ProjectRegistry):
    """Rendered mise tasks must use modern bash (`[[ ]]`, `(( ))`), not legacy POSIX tests."""
    content = (projects.render("basic") / "mise.toml").read_text()
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
    tasks = mise_toml(projects.render("basic"))["tasks"]
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
    lint = pyproject(projects.render("basic"))["tool"]["ruff"]["lint"]

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
    assert lint["isort"]["known-first-party"] == ["example_proj"]


def test_pyproject_registers_markers_and_package_coverage(projects: ProjectRegistry):
    """Generated packaged projects should register markers and use source_pkgs coverage."""
    tool = pyproject(projects.render("basic"))["tool"]

    assert tool["pytest"]["ini_options"]["markers"] == [
        "unit: marks tests as unit tests",
        "integration: marks tests as integration tests",
    ]
    assert tool["coverage"]["run"]["source_pkgs"] == ["example_proj"]
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
