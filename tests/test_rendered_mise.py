"""Rendered mise.toml contracts: task graph, CI order, lint/fix split, gating and entrypoints."""

from __future__ import annotations

from _projects import ProjectRegistry, refs

BASE_TASKS = set(
    """install lint lint:types test test:unit test:integration hooks hooks:update doctor bootstrap
    changelog release clean lint:python fix:python format format:check fix ci ci:full check:version-tag""".split()  # noqa: SIM905
)
GITHUB_TASKS = {"lint:workflows"}


def test_mise_task_graph_is_always_complete(projects: ProjectRegistry):
    data = projects.render("extra-dev-no-github").mise()
    tasks = data["tasks"]
    assert set(tasks) == BASE_TASKS
    assert refs(tasks["lint"]) == ["lint:python", "lint:types"]
    assert refs(tasks["test"]) == ["test:unit", "test:integration"]
    assert data["env"]["_"]["file"] == ".env"


def test_mise_ci_runs_ordered_readonly_steps(projects: ProjectRegistry):
    """CI fails fast on version drift, then lint, format:check and tests."""
    tasks = projects.render("basic").mise()["tasks"]
    assert refs(tasks["ci"]) == ["check:version-tag", "lint", "format:check", "test:unit"]
    assert refs(tasks["ci:full"]) == ["check:version-tag", "lint", "format:check", "test"]
    assert tasks["ci"]["env"]["CI"] == tasks["ci:full"]["env"]["CI"] == "true"


def test_mise_lint_is_check_only_and_fix_tasks_mutate(projects: ProjectRegistry):
    tasks = projects.render("basic").mise()["tasks"]
    assert "ruff check" in tasks["lint:python"]["run"]
    assert "--fix" not in tasks["lint:python"]["run"]
    assert "ty check" in tasks["lint:types"]["run"]
    assert "--fix" in tasks["fix:python"]["run"]
    assert "ruff format" in tasks["format"]["run"]
    assert "--check" not in tasks["format"]["run"]
    assert "--check" in tasks["format:check"]["run"]


def test_mise_github_tasks_and_tools_are_gated(projects: ProjectRegistry):
    """GitHub-only workflow lint ships only with github_integration and skips a missing workflows directory."""
    without = projects.render("extra-dev-no-github").mise()
    assert not GITHUB_TASKS & set(without["tasks"])
    assert "actionlint" not in without["tools"]
    assert "act" not in without["tools"]
    assert "ci:docker" not in without["tasks"]

    with_github = projects.render("github").mise()
    assert set(with_github["tasks"]) >= GITHUB_TASKS
    assert "actionlint" in with_github["tools"]
    assert "act" not in with_github["tools"]
    assert "ci:docker" not in with_github["tasks"]
    assert refs(with_github["tasks"]["lint"]) == ["lint:python", "lint:types", "lint:workflows"]
    assert "[[ -d .github/workflows ]]" in with_github["tasks"]["lint:workflows"]["run"]


def test_mise_agent_entrypoints(projects: ProjectRegistry):
    """Generated projects expose bootstrap, doctor, hooks, changelog and clean entrypoints over the toolchain."""
    tasks = projects.render("basic").mise()["tasks"]
    assert refs(tasks["bootstrap"]) == ["install", "doctor"]
    assert tasks["bootstrap"]["run"][0] == "mise trust"
    assert "uv sync --dev" in tasks["install"]["run"]
    assert "mise doctor" in tasks["doctor"]["run"]
    assert "prek run --all-files" in tasks["hooks"]["run"]
    assert tasks["hooks:update"]["run"] == "prek update"
    assert "git-cliff" in tasks["changelog"]["run"]
    assert refs(tasks["doctor"]) == []


def test_mise_pytest_split_tolerates_missing_integration(projects: ProjectRegistry):
    """pytest is split into unit/integration tasks; the skip is inline and a fresh project has no integration dir."""
    project = projects.render("app")
    tasks = project.mise()["tasks"]
    assert "uv run pytest tests/unit/" in tasks["test:unit"]["run"]
    integration = tasks["test:integration"]["run"]
    assert "[[ -d tests/integration ]]" in integration
    assert "uv run pytest tests/integration/" in integration
    assert refs(tasks["test"]) == ["test:unit", "test:integration"]
    assert not (project.path / "tests" / "integration").exists(), "PRD: no new scaffold directories"
