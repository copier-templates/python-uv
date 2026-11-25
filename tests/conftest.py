"""Session-scoped fixtures built on the harness in `_projects.py`."""

from __future__ import annotations

from pathlib import Path

import pytest
from _projects import ProjectRegistry, make_git_template_repo, snapshot_template_root


@pytest.fixture(scope="session")
def template_source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Snapshot of the template working tree (see `snapshot_template_root`)."""
    return snapshot_template_root(tmp_path_factory.mktemp("template-src"))


@pytest.fixture(scope="session")
def projects(template_source: Path, tmp_path_factory: pytest.TempPathFactory) -> ProjectRegistry:
    """Renders each variant once per session: `projects.render("<variant>")`."""
    return ProjectRegistry(template_source, tmp_path_factory.mktemp)


@pytest.fixture(scope="session")
def git_template_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Git-backed copy of this template with tags `v1.0.0` and `v1.0.1`."""
    return make_git_template_repo(tmp_path_factory.mktemp("git-template"))
