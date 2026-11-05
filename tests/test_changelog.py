"""Regression tests for git-cliff bootstrapping.

`cliff.toml` must ship in generated projects (verbatim payload under
`templates/`; root is a symlink to it).
"""

from __future__ import annotations

from _projects import ProjectRegistry, load_toml


def test_generated_cliff_toml_exists_and_is_valid(projects: ProjectRegistry):
    """Generated projects must ship a parseable git-cliff config."""
    project = projects.render("basic")
    cliff = project / "cliff.toml"
    assert cliff.is_file(), "Missing generated cliff.toml"
    data = load_toml(cliff)
    assert "changelog" in data
    assert "body" in data["changelog"]
    assert data["git"]["conventional_commits"] is True


def test_generated_readme_documents_changelog(projects: ProjectRegistry):
    """Generated README must point at the changelog task."""
    project = projects.render("basic")
    readme = (project / "README.md").read_text()
    assert "mise run changelog" in readme
