"""Pytest fixtures for validating the Copier template itself.

These tests are NOT copied into generated projects (excluded via _exclude).
The render pipeline (template snapshot, Copier helpers, variant data) lives in
`_projects.py`; a single session-scoped `projects` registry renders each
variant once, and thin module-scoped fixtures keep the public `generated_*`
fixture names stable.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from _projects import (
    ALIASES,
    GIT_IDENTITY,
    TEMPLATE_ROOT,  # noqa: F401 (re-exported for test modules)
    ProjectRegistry,
    _make_data,  # noqa: F401 (re-exported for test modules)
    _run_copy,
    _run_copy_from,  # noqa: F401 (re-exported for test modules)
    _snapshot_template_root,
)
from plumbum import local

# Module-level constant: absolute path to git (avoids partial-path lint in update tests)
GIT = shutil.which("git")

# Module-level constant: Markdown line added to the template README in the v1.0.1 tag
# of the git-backed fixture repo. Update tests assert it reaches the generated project.
UPDATE_MARKER = "<!-- template-update-marker-v1.0.1 -->"


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run `git <args>` in `cwd`, failing the test on a non-zero exit code."""
    assert GIT is not None, "git executable not found on PATH"
    return subprocess.run(
        [GIT, *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _render_project(data: dict[str, object], dst_name: str) -> Path:
    """Render the working-tree snapshot with Copier; injected into the registry."""
    return _run_copy(data, dst_name=dst_name)


@pytest.fixture(scope="session")
def projects() -> ProjectRegistry:
    """Session-scoped registry: renders each (variant, overrides) pair exactly once."""
    return ProjectRegistry(_render_project)


@pytest.fixture(scope="module")
def generated_basic(projects: ProjectRegistry) -> Path:
    """Basic generated project (rendered once by the session-scoped registry)."""
    return projects.render(ALIASES["generated_basic"])


@pytest.fixture(scope="module")
def generated_with_ruff(projects: ProjectRegistry) -> Path:
    """Generated project with Ruff (rendered once by the session-scoped registry)."""
    return projects.render(ALIASES["generated_with_ruff"])


@pytest.fixture(scope="module")
def generated_python313(projects: ProjectRegistry) -> Path:
    """Generated project pinned to Python 3.13 (rendered once by the session-scoped registry)."""
    return projects.render(ALIASES["generated_python313"])


@pytest.fixture(scope="module")
def generated_with_license(projects: ProjectRegistry) -> Path:
    """Generated project with license (rendered once by the session-scoped registry)."""
    return projects.render(ALIASES["generated_with_license"])


@pytest.fixture(scope="module")
def generated_with_license_ruff(projects: ProjectRegistry) -> Path:
    """Licensed project with Ruff (rendered once by the session-scoped registry)."""
    return projects.render(ALIASES["generated_with_license_ruff"])


@pytest.fixture(scope="module")
def generated_with_github_integration(projects: ProjectRegistry) -> Path:
    """Generated project with GitHub integration (rendered once by the session-scoped registry)."""
    return projects.render(ALIASES["generated_with_github_integration"])


@pytest.fixture(scope="module")
def generated_without_github_integration(projects: ProjectRegistry) -> Path:
    """Generated project without GitHub integration (rendered once by the session-scoped registry)."""
    return projects.render(ALIASES["generated_without_github_integration"])


@pytest.fixture(scope="module")
def generated_hyphenated_package(projects: ProjectRegistry) -> Path:
    """Generated package project with a hyphenated distribution name."""
    return projects.render(ALIASES["generated_hyphenated_package"])


@pytest.fixture(scope="module")
def generated_app(projects: ProjectRegistry) -> Path:
    """Generated application project with a root entrypoint."""
    return projects.render(ALIASES["generated_app"])


@pytest.fixture(scope="module")
def generated_library(projects: ProjectRegistry) -> Path:
    """Generated library project with a typed src layout."""
    return projects.render(ALIASES["generated_library"])


@pytest.fixture(scope="session")
def _git_template_repo() -> Path:
    """Session-scoped: git-backed copy of this template with two release tags.

    `v1.0.0` is the current working tree; `v1.0.1` appends `UPDATE_MARKER` to
    `templates/README.md.jinja`. Copier `update` tests copy from `v1.0.0` and
    expect the `v1.0.1` change to land in the generated project.
    """
    repo = _snapshot_template_root()
    readme = repo / "templates" / "README.md.jinja"
    existing = readme.read_text()
    marker_suffix = f"{UPDATE_MARKER}\n" if existing.endswith("\n") else f"\n{UPDATE_MARKER}\n"
    with local.env(**GIT_IDENTITY):
        _git(repo, "init")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "Template snapshot")
        _git(repo, "tag", "v1.0.0")
        with readme.open("a", encoding="utf-8") as handle:
            handle.write(marker_suffix)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "Document update marker")
        _git(repo, "tag", "v1.0.1")
    return repo


# License test data: used by unit tests in test_licenses.py
LICENSE_TEST_CASES = [
    {
        "license_type": "mit",
        "spdx_identifier": "MIT",
        "expected_headers": ["MIT License"],
        "expected_patterns": ["Copyright (c) 2025", "Permission is hereby granted"],
    },
    {
        "license_type": "apache-2.0",
        "spdx_identifier": "Apache-2.0",
        "expected_headers": ["Apache License", "Version 2.0"],
        "expected_patterns": ["Copyright 2025", "Licensed under the Apache License"],
    },
    {
        "license_type": "gpl-2.0",
        "spdx_identifier": "GPL-2.0-only",
        "expected_headers": ["GNU GENERAL PUBLIC LICENSE", "Version 2"],
        "expected_patterns": ["Copyright (C) 2025", "free software"],
    },
    {
        "license_type": "gpl-3.0",
        "spdx_identifier": "GPL-3.0-only",
        "expected_headers": ["GNU GENERAL PUBLIC LICENSE", "Version 3"],
        "expected_patterns": ["Copyright (C) 2025", "free software"],
    },
    {
        "license_type": "lgpl-2.0",
        "spdx_identifier": "LGPL-2.0-only",
        "expected_headers": ["GNU LIBRARY GENERAL PUBLIC LICENSE", "Version 2"],
        "expected_patterns": ["Copyright (C) 2025", "library is free software"],
    },
    {
        "license_type": "lgpl-2.1",
        "spdx_identifier": "LGPL-2.1-only",
        "expected_headers": ["GNU LESSER GENERAL PUBLIC LICENSE", "Version 2.1"],
        "expected_patterns": ["Copyright (C) 2025", "library is free software"],
    },
    {
        "license_type": "lgpl-3.0",
        "spdx_identifier": "LGPL-3.0-only",
        "expected_headers": ["GNU LESSER GENERAL PUBLIC LICENSE", "Version 3"],
        "expected_patterns": ["Copyright (C) 2025", "library is free software"],
    },
    {
        "license_type": "mpl-2.0",
        "spdx_identifier": "MPL-2.0",
        "expected_headers": ["Mozilla Public License Version 2.0"],
        "expected_patterns": ["1. Definitions", "2. License Grants"],
    },
]
