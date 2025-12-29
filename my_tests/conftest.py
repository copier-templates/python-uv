"""Pytest fixtures for validating the Copier template itself.
These tests are NOT copied into generated projects (excluded via _exclude).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from copier import run_copy

# Module-level constant: computed once at import time, not repeatedly during tests
TEMPLATE_ROOT = Path(__file__).resolve().parents[1]

# Base data and small helper to produce test data with overrides
BASE_DATA: dict[str, object] = {
    "project_description": "Example description",
    "author_name": "Test User",
    "author_email": "test@test.com",
    "production_deps": ["requests"],
    "dev_deps": ["pytest", "pytest-cov"],
}


def _make_data(overrides: dict[str, object]) -> dict[str, object]:
    """Return a copy of BASE_DATA merged with overrides."""
    return BASE_DATA | overrides


def _run_copy(data: dict[str, object], dst_name: str = "_generated") -> Path:
    dst_dir = Path(tempfile.mkdtemp(prefix=f"copier-template-test-{dst_name}-"))
    run_copy(
        str(TEMPLATE_ROOT),
        str(dst_dir),
        data=data,
        defaults=True,
        overwrite=True,
        unsafe=True,
        vcs_ref="HEAD",  # Use current git HEAD instead of latest tag
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
            "dev_deps": ["pytest", "pytest-cov"],
        }
    )
    return _run_copy(data, dst_name="license")


@pytest.fixture(scope="module")
def generated_with_license(_session_with_license_project: Path) -> Path:
    """Generated project with license (wraps session fixture for ~50% faster execution)."""
    return _session_with_license_project


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
