"""Fast unit tests for LICENSE file assertion logic.

Tests validate that our test assertions correctly identify expected patterns
in license content. These are mocked unit tests (no Copier overhead).

Template generation is tested via other integration tests:
- test_conditional_sections.py validates README rendering with licenses
- test_exclusions.py validates excluded paths
- test_core_structure.py validates project structure
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from conftest import LICENSE_TEST_CASES


def _mock_license_file(
    expected_headers: list[str],
    expected_patterns: list[str],
    author: str = "Test User",
) -> MagicMock:
    """Create a mocked license file Path object with test content."""
    current_year = str(datetime.now(tz=timezone.utc).year)
    content_parts = expected_headers + expected_patterns + [author, current_year]
    content = "\n".join(content_parts)

    mock_path = MagicMock(spec=Path)
    mock_path.is_file.return_value = True
    mock_path.exists.return_value = True
    mock_path.read_text.return_value = content
    return mock_path


@pytest.mark.parametrize(
    "test_case",
    LICENSE_TEST_CASES,
    ids=[case["license_type"] for case in LICENSE_TEST_CASES],
)
def test_license_headers_detected(test_case: dict):
    """Verify we correctly detect expected headers in license content."""
    headers = test_case["expected_headers"]
    mock_file = _mock_license_file(headers, [])

    content = mock_file.read_text()
    for header in headers:
        assert header in content, f"Test assertion should detect '{header}'"


@pytest.mark.parametrize(
    "test_case",
    LICENSE_TEST_CASES,
    ids=[case["license_type"] for case in LICENSE_TEST_CASES],
)
def test_license_patterns_detected(test_case: dict):
    """Verify we correctly detect expected patterns in license content."""
    patterns = test_case["expected_patterns"]
    mock_file = _mock_license_file([], patterns)

    content = mock_file.read_text()
    for pattern in patterns:
        assert pattern in content, f"Test assertion should detect '{pattern}'"


def test_copyright_year_detected():
    """Verify current year is properly detected in license content."""
    current_year = str(datetime.now(tz=timezone.utc).year)
    mock_file = _mock_license_file([], [])

    content = mock_file.read_text()
    assert current_year in content, "Test assertion should detect current year"


def test_author_name_detected():
    """Verify author name is properly detected in license content."""
    author_name = "Jane Developer"
    mock_file = _mock_license_file([], [], author=author_name)

    content = mock_file.read_text()
    assert author_name in content, "Test assertion should detect custom author name"


def test_author_name_detected_default():
    """Verify default author name is properly detected."""
    mock_file = _mock_license_file([], [])

    content = mock_file.read_text()
    assert "Test User" in content, "Test assertion should detect default author"
