"""Tests for GitHub workflow integration in generated projects."""

from __future__ import annotations

from pathlib import Path


def test_workflows_present_when_github_integration_enabled(
    generated_with_github_integration: Path,
):
    """Test that GitHub workflows are present when GitHub integration is enabled."""
    workflows_dir = generated_with_github_integration / ".github" / "workflows"
    assert workflows_dir.is_dir(), "GitHub integration should create .github/workflows directory"
    assert (workflows_dir / "test.yml").is_file(), "GitHub integration should include test.yml workflow"


def test_workflows_absent_when_github_integration_disabled(
    generated_without_github_integration: Path,
):
    """Test that GitHub workflows are excluded when GitHub integration is disabled."""
    workflows_dir = generated_without_github_integration / ".github" / "workflows"
    if workflows_dir.exists():
        contents = list(workflows_dir.iterdir())
        assert not contents, (
            f"GitHub integration disabled should not contain workflows, but found: {[item.name for item in contents]}"
        )
