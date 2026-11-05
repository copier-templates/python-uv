"""Rendered pyproject fields, README sections and mise.toml task graph: always-on tooling and real variance."""

from __future__ import annotations

import pytest
from _projects import ProjectRegistry, mise_toml, pyproject, refs

BASE_TASKS = {
    "install",
    "lint",
    "lint:shell",
    "lint:types",
    "test",
    "test:unit",
    "test:integration",
    "hooks",
    "doctor",
    "bootstrap",
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

GITHUB_TASKS = {"lint:workflows", "ci:docker"}


@pytest.mark.parametrize("snippet", ["Running Tests", "Code Quality", "img.shields.io/badge/mise", "mise.jdx.dev"])
def test_readme_always_documents_tests_and_quality(projects: ProjectRegistry, snippet: str):
    assert snippet in (projects.render("basic") / "README.md").read_text()


def test_default_render_always_includes_pytest_cov_ruff_and_ty_tooling(projects: ProjectRegistry):
    project = projects.render("basic")

    assert pyproject(project)["dependency-groups"]["dev"] == ["pytest>=9,<10", "pytest-cov", "ruff", "ty>=0.0.34"]
    tool = pyproject(project)["tool"]
    assert {"pytest", "coverage", "ruff", "ty"} <= set(tool)
    assert any(opt.startswith("--cov=") for opt in tool["pytest"]["addopts"])


def test_extra_dev_deps_are_appended_to_the_always_on_tooling(projects: ProjectRegistry):
    dev = pyproject(projects.render("extra-dev-deps"))["dependency-groups"]["dev"]

    assert dev == ["pytest>=9,<10", "pytest-cov", "ruff", "ty>=0.0.34", "hypothesis>=6"]


def test_pytest_config_uses_native_table_without_ini_options(projects: ProjectRegistry):
    """pytest 9 rejects a pyproject that declares both `[tool.pytest]` and `[tool.pytest.ini_options]`."""
    pytest_table = pyproject(projects.render("basic"))["tool"]["pytest"]

    assert "ini_options" not in pytest_table
    assert pytest_table["strict"] is True
    assert "--import-mode=importlib" in pytest_table["addopts"]


def test_ty_config_is_strict_and_scoped_to_source_and_tests(projects: ProjectRegistry):
    tool = pyproject(projects.render("basic"))["tool"]

    assert tool["ty"]["src"]["include"] == ["src", "tests"]
    assert tool["ty"]["terminal"]["error-on-warning"] is True
    assert tool["ty"]["rules"]["unsound-return-statement"] == "error"
    assert set(tool["ty"]["rules"].values()) == {"error"}


def test_ty_src_scope_follows_app_layout(projects: ProjectRegistry):
    assert pyproject(projects.render("app"))["tool"]["ty"]["src"]["include"] == ["main.py", "tests"]


def test_coverage_report_enforces_fail_under_98(projects: ProjectRegistry):
    assert pyproject(projects.render("basic"))["tool"]["coverage"]["report"]["fail_under"] == 98


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
    data = mise_toml(projects.render("no-github"))
    assert set(data["tasks"]) == BASE_TASKS
    assert refs(data["tasks"]["lint"]) == ["lint:python", "lint:types", "lint:shell"]
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
    content = (projects.render("github") / "mise.toml").read_text()
    assert "#!/usr/bin/env bash" in content
    assert "((" in content
    assert "[[ -d .github/workflows ]]" in content
    assert "if [ " not in content
    assert "while [ " not in content


def test_mise_toml_lint_type_checks_with_ty(projects: ProjectRegistry):
    tasks = mise_toml(projects.render("basic"))["tasks"]

    assert tasks["lint:types"]["run"] == "uv run ty check"


def test_mise_toml_github_tasks_and_tools_are_gated(projects: ProjectRegistry):
    """GitHub-only tooling (actionlint, act, lint:workflows, ci:docker) ships only with github_integration."""
    without = mise_toml(projects.render("no-github"))
    assert not GITHUB_TASKS & set(without["tasks"])
    assert "act" not in without["tools"]
    assert "actionlint" not in without["tools"]

    with_github = mise_toml(projects.render("github"))
    assert set(with_github["tasks"]) >= GITHUB_TASKS
    assert {"act", "actionlint"} <= set(with_github["tools"])
    assert refs(with_github["tasks"]["lint"]) == ["lint:python", "lint:types", "lint:shell", "lint:workflows"]


def test_mise_toml_agent_entrypoints(projects: ProjectRegistry):
    """Generated projects must expose doctor/bootstrap/hooks/changelog/clean:all.

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
    assert "git-cliff" in tasks["changelog"]["run"]
    assert ".venv/" in tasks["clean:all"]["run"]
    assert ".venv/" not in tasks["clean"]["run"]


def test_mise_toml_workflows_lint_skips_missing_workflows(projects: ProjectRegistry):
    """Workflow lint must skip gracefully when the repo has no workflow files."""
    run = mise_toml(projects.render("github"))["tasks"]["lint:workflows"]["run"]
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
    assert lint["per-file-ignores"]["tests/**/*.py"] == ["S101", "S105", "S106", "ANN"]
    assert lint["isort"]["known-first-party"] == ["example_proj"]


def test_pyproject_ruff_matches_appomni_rule_set_and_line_length(projects: ProjectRegistry):
    ruff = pyproject(projects.render("basic"))["tool"]["ruff"]

    assert ruff["line-length"] == 160
    assert {"RUF", "PTH", "BLE", "G", "PGH003", "ANN201", "ANN202", "ANN204"} <= set(ruff["lint"]["select"])
    assert {"RUF001", "RUF002", "RUF003", "G004"} <= set(ruff["lint"]["ignore"])


def test_pyproject_registers_markers_and_package_coverage(projects: ProjectRegistry):
    """Generated packaged projects should register markers and use source_pkgs coverage."""
    tool = pyproject(projects.render("basic"))["tool"]

    assert tool["pytest"]["markers"] == [
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
    options = pyproject(projects.render("app"))["tool"]["pytest"]

    assert options["pythonpath"] == ["."]
    assert options["testpaths"] == ["tests"]


def test_pyproject_package_configures_pythonpath_for_src_layout(projects: ProjectRegistry):
    """Packaged projects keep resolving imports from `src`."""
    assert pyproject(projects.render("basic"))["tool"]["pytest"]["pythonpath"] == ["src"]
