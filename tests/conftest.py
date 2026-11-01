"""Pytest fixtures for validating the Copier template itself.
These tests are NOT copied into generated projects (excluded via _exclude).
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from copier import run_copy
from plumbum import local

# Module-level constant: computed once at import time, not repeatedly during tests
TEMPLATE_ROOT = Path(__file__).resolve().parents[1]

# Module-level constant: absolute path to git (avoids partial-path lint in update tests)
GIT = shutil.which("git")

# Module-level constant: Markdown line added to the template README in the v1.0.1 tag
# of the git-backed fixture repo. Update tests assert it reaches the generated project.
UPDATE_MARKER = "<!-- template-update-marker-v1.0.1 -->"

# Module-level constant: git identity used for every fixture commit (no global config needed)
GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "Copier Tests",
    "GIT_AUTHOR_EMAIL": "copier-tests@example.com",
    "GIT_COMMITTER_NAME": "Copier Tests",
    "GIT_COMMITTER_EMAIL": "copier-tests@example.com",
}


def _snapshot_template_root() -> Path:
    """Copy the current working tree to a temporary non-git directory for Copier tests."""
    snapshot_root = Path(tempfile.mkdtemp(prefix="copier-template-src-")) / "template"
    shutil.copytree(
        TEMPLATE_ROOT,
        snapshot_root,
        ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"),
    )
    return snapshot_root


TEMPLATE_SOURCE = _snapshot_template_root()

# Base data and small helper to produce test data with overrides
BASE_DATA: dict[str, object] = {
    "project_type": "package",
    "project_description": "Example description",
    "author_name": "Test User",
    "author_email": "test@test.com",
    "production_deps": ["httpx[http2]"],
    "dev_deps": ["pytest", "pytest-cov"],
    "github_integration": True,
}


def _make_data(overrides: dict[str, object]) -> dict[str, object]:
    """Return a copy of BASE_DATA merged with overrides."""
    return BASE_DATA | overrides


def _run_copy_from(
    source: Path,
    data: dict[str, object],
    dst_name: str = "_generated",
    vcs_ref: str | None = None,
) -> Path:
    """Render `source` with Copier into a fresh temp dir, optionally pinned to `vcs_ref`."""
    # Resolve the destination: on macOS `mkdtemp` returns `/var/...` while git
    # reports `/private/var/...`, which breaks Copier's `update` path math.
    dst_dir = Path(tempfile.mkdtemp(prefix=f"copier-template-test-{dst_name}-")).resolve()
    extra: dict[str, object] = {"vcs_ref": vcs_ref} if vcs_ref is not None else {}
    with local.env(**GIT_IDENTITY):
        run_copy(
            str(source),
            str(dst_dir),
            data=data,
            defaults=True,
            overwrite=True,
            unsafe=True,
            **extra,
        )
    return dst_dir


def _run_copy(data: dict[str, object], dst_name: str = "_generated") -> Path:
    """Render the working-tree snapshot of this template (`TEMPLATE_SOURCE`)."""
    return _run_copy_from(TEMPLATE_SOURCE, data, dst_name=dst_name)


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


@pytest.fixture(scope="session")
def _session_basic_project() -> Path:
    """Session-scoped: basic generated project (reused across all test modules)."""
    data = _make_data({"project_name": "example_proj"})
    return _run_copy(data, dst_name="basic")


@pytest.fixture(scope="session")
def _session_with_ruff_project() -> Path:
    """Session-scoped: generated project with Ruff (reused across all test modules)."""
    data = _make_data(
        {
            "project_name": "ruff_proj",
            "production_deps": [],
            "dev_deps": ["pytest", "pytest-cov", "ruff"],
        }
    )
    return _run_copy(data, dst_name="ruff")


@pytest.fixture(scope="module")
def generated_basic(_session_basic_project: Path) -> Path:
    """Basic generated project (wraps session fixture for ~50% faster execution)."""
    return _session_basic_project


@pytest.fixture(scope="module")
def generated_with_ruff(_session_with_ruff_project: Path) -> Path:
    """Generated project with Ruff (wraps session fixture for ~50% faster execution)."""
    return _session_with_ruff_project


@pytest.fixture(scope="session")
def _session_python313_project() -> Path:
    """Session-scoped: generated project pinned to Python 3.13.

    Ruff is included in `dev_deps` so the rendered `[tool.ruff] target-version`
    reflects the selected Python version instead of being absent.
    """
    data = _make_data(
        {
            "project_name": "py313_proj",
            "python_version": "3.13",
            "production_deps": [],
            "dev_deps": ["pytest", "pytest-cov", "ruff"],
        }
    )
    return _run_copy(data, dst_name="python313")


@pytest.fixture(scope="module")
def generated_python313(_session_python313_project: Path) -> Path:
    """Generated project pinned to Python 3.13 (wraps session fixture)."""
    return _session_python313_project


@pytest.fixture(scope="session")
def _session_with_license_project() -> Path:
    """Session-scoped: generated project with MIT license (reused across all test modules)."""
    data = _make_data(
        {
            "project_name": "license_proj",
            "include_license": True,
            "license_type": "mit",
        }
    )
    return _run_copy(data, dst_name="license")


@pytest.fixture(scope="module")
def generated_with_license(_session_with_license_project: Path) -> Path:
    """Generated project with license (wraps session fixture for ~50% faster execution)."""
    return _session_with_license_project


@pytest.fixture(scope="session")
def _session_with_license_ruff_project() -> Path:
    """Session-scoped: licensed project with Ruff, so copy tasks run hooks on LICENSE.

    No other fixture combines `include_license` with `ruff`: without this,
    `mise run ci` (and its `end-of-file-fixer` hook) never executes against a
    rendered LICENSE, which is how the trailing-blank-line regression escaped.
    """
    data = _make_data(
        {
            "project_name": "license_ruff_proj",
            "include_license": True,
            "license_type": "mit",
            "production_deps": [],
            "dev_deps": ["pytest", "pytest-cov", "ruff"],
        }
    )
    return _run_copy(data, dst_name="license-ruff")


@pytest.fixture(scope="module")
def generated_with_license_ruff(_session_with_license_ruff_project: Path) -> Path:
    """Licensed project with Ruff (wraps session fixture for ~50% faster execution)."""
    return _session_with_license_ruff_project


@pytest.fixture(scope="session")
def _session_with_github_integration_project() -> Path:
    """Session-scoped: generated project with GitHub integration enabled."""
    data = _make_data(
        {
            "project_name": "github_proj",
            "github_integration": True,
        }
    )
    return _run_copy(data, dst_name="github")


@pytest.fixture(scope="module")
def generated_with_github_integration(_session_with_github_integration_project: Path) -> Path:
    """Generated project with GitHub integration (wraps session fixture for ~50% faster execution)."""
    return _session_with_github_integration_project


@pytest.fixture(scope="session")
def _session_without_github_integration_project() -> Path:
    """Session-scoped: generated project with GitHub integration disabled."""
    data = _make_data(
        {
            "project_name": "no_github_proj",
            "github_integration": False,
        }
    )
    return _run_copy(data, dst_name="no_github")


@pytest.fixture(scope="module")
def generated_without_github_integration(_session_without_github_integration_project: Path) -> Path:
    """Generated project without GitHub integration (wraps session fixture for ~50% faster execution)."""
    return _session_without_github_integration_project


@pytest.fixture(scope="session")
def _session_hyphenated_package_project() -> Path:
    """Session-scoped: generated package project with a hyphenated distribution name."""
    data = _make_data(
        {
            "project_name": "my-app",
            "project_type": "package",
        }
    )
    return _run_copy(data, dst_name="hyphenated-package")


@pytest.fixture(scope="module")
def generated_hyphenated_package(_session_hyphenated_package_project: Path) -> Path:
    """Generated package project with a hyphenated distribution name."""
    return _session_hyphenated_package_project


@pytest.fixture(scope="session")
def _session_app_project() -> Path:
    """Session-scoped: generated application project with a root entrypoint."""
    data = _make_data(
        {
            "project_name": "console_app",
            "project_type": "app",
        }
    )
    return _run_copy(data, dst_name="app")


@pytest.fixture(scope="module")
def generated_app(_session_app_project: Path) -> Path:
    """Generated application project with a root entrypoint."""
    return _session_app_project


@pytest.fixture(scope="session")
def _session_library_project() -> Path:
    """Session-scoped: generated library project with a typed src layout."""
    data = _make_data(
        {
            "project_name": "example_lib",
            "project_type": "lib",
        }
    )
    return _run_copy(data, dst_name="lib")


@pytest.fixture(scope="module")
def generated_library(_session_library_project: Path) -> Path:
    """Generated library project with a typed src layout."""
    return _session_library_project


@pytest.fixture(scope="session")
def _git_template_repo() -> Path:
    """Session-scoped: git-backed copy of this template with two release tags.

    `v1.0.0` is the current working tree; `v1.0.1` appends `UPDATE_MARKER` to
    `templates/README.md.jinja`. Copier `update` tests copy from `v1.0.0` and
    expect the `v1.0.1` change to land in the generated project.
    """
    repo = Path(tempfile.mkdtemp(prefix="copier-template-git-")) / "template"
    shutil.copytree(
        TEMPLATE_ROOT,
        repo,
        ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"),
    )
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
