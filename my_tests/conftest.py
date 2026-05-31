"""Pytest fixtures for validating the Copier template itself.
These tests are NOT copied into generated projects (excluded via _exclude).
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from copier import run_copy

# Module-level constant: computed once at import time, not repeatedly during tests
TEMPLATE_ROOT = Path(__file__).resolve().parents[1]


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


def _run_copy(data: dict[str, object], dst_name: str = "_generated") -> Path:
    dst_dir = Path(tempfile.mkdtemp(prefix=f"copier-template-test-{dst_name}-"))
    run_copy(
        str(TEMPLATE_SOURCE),
        str(dst_dir),
        data=data,
        defaults=True,
        overwrite=True,
        unsafe=True,
    )
    return dst_dir


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
