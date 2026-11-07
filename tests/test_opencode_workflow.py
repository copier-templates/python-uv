"""OpenCode agent workflow ships with GitHub-integrated projects."""

from __future__ import annotations

from pathlib import Path

from _projects import TEMPLATE_ROOT, ProjectRegistry

ROOT_WORKFLOW = TEMPLATE_ROOT / ".github" / "workflows" / "opencode.yml"
PAYLOAD_WORKFLOW = TEMPLATE_ROOT / "templates" / ".github" / "workflows" / "opencode.yml"


def _workflow_text() -> str:
    return PAYLOAD_WORKFLOW.read_text()


def test_opencode_workflow_root_and_payload_stay_in_sync():
    assert ROOT_WORKFLOW.is_file()
    assert PAYLOAD_WORKFLOW.is_file()
    assert ROOT_WORKFLOW.read_bytes() == PAYLOAD_WORKFLOW.read_bytes()


def test_opencode_workflow_triggers_on_comment_commands():
    text = _workflow_text()
    assert "issue_comment" in text
    assert "pull_request_review_comment" in text
    assert "types: [created]" in text
    assert "'/oc'" in text
    assert "'/opencode'" in text


def test_opencode_workflow_pins_agent_action():
    text = _workflow_text()
    assert "anomalyco/opencode/github@latest" in text
    assert "secrets.OPENCODE_API_KEY" in text
    assert "use_github_token: true" in text


def test_opencode_workflow_follows_github_integration(projects: ProjectRegistry):
    with_github = projects.render("github") / ".github" / "workflows" / "opencode.yml"
    assert with_github.is_file()
    without_github: Path = projects.render("no-github") / ".github"
    assert not without_github.exists()
