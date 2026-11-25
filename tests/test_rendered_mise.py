"""Rendered mise.toml contracts: GitHub gating (shared includes stay owned by `test_sync.py`)."""

from __future__ import annotations

from _projects import LOCAL_TASKS, ProjectRegistry


def test_mise_github_only_changes_the_workflow_payload(projects: ProjectRegistry):
    """GitHub integration adds workflows and the cicd include, not local tasks or tools."""
    without = projects.render("lib-licensed").mise()
    with_github = projects.render("basic").mise()
    assert set(without["tasks"]) == set(with_github["tasks"]) == LOCAL_TASKS
    assert without["tools"] == with_github["tools"]
    for tools in (without["tools"], with_github["tools"]):
        assert "actionlint" not in tools
        assert "jactionlint" in tools
    assert "gh:lint" not in without["tasks"]
    assert "lint:workflows" not in with_github["tasks"]


def test_mise_cicd_include_follows_github_integration(projects: ProjectRegistry):
    """The cicd shared include renders only when github_integration is enabled."""
    without = projects.render("lib-licensed").mise()
    with_github = projects.render("basic").mise()
    without_includes = without.get("task_config", {}).get("includes", [])
    with_includes = with_github.get("task_config", {}).get("includes", [])
    assert any("//tasks/cicd/github" in include for include in with_includes)
    assert not any("//tasks/cicd/github" in include for include in without_includes)
    for category in ("core", "toml", "py"):
        assert any(f"//tasks/{category}" in include for include in without_includes)
        assert any(f"//tasks/{category}" in include for include in with_includes)
