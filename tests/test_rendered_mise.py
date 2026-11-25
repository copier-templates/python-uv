"""Rendered mise.toml contracts: GitHub gating (shared includes stay owned by `test_sync.py`)."""

from __future__ import annotations

from _projects import LOCAL_TASKS, ProjectRegistry


def test_mise_github_only_changes_the_workflow_payload(projects: ProjectRegistry):
    """GitHub integration adds workflows, not tasks or tools; the shared gh:lint self-skips instead."""
    without = projects.render("lib-licensed").mise()
    with_github = projects.render("basic").mise()
    assert set(without["tasks"]) == set(with_github["tasks"]) == LOCAL_TASKS
    assert without["tools"] == with_github["tools"]
    for tools in (without["tools"], with_github["tools"]):
        assert "actionlint" not in tools
        assert "jactionlint" in tools
    assert "gh:lint" not in without["tasks"]
    assert "lint:workflows" not in with_github["tasks"]
