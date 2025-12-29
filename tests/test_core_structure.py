"""Core structural tests for the Copier template output."""

from __future__ import annotations

from pathlib import Path

import pytest

# Module-level constants: defined once per module load, not recreated per test
EXPECTED_FILES = [
    ".copier-answers.yml",
    ".gitattributes",
    ".gitignore",
    ".pre-commit-config.yaml",
    "Makefile",
    "pyproject.toml",
    "README.md",
]

EXPECTED_DIRS = ["src", "tests"]


@pytest.mark.parametrize("filename", EXPECTED_FILES, ids=lambda x: f"file:{x}")
def test_expected_file_exists(generated_basic: Path, filename: str):
    """Test each expected file exists. Parametrized for visibility without performance impact.

    Session-scoped fixture ensures fast execution: fixture is created once per session,
    parametrization only multiplies test invocations (not setup overhead).
    """
    file_path = generated_basic / filename
    assert file_path.is_file(), f"Missing expected file: {filename}"


@pytest.mark.parametrize("dirname", EXPECTED_DIRS, ids=lambda x: f"dir:{x}")
def test_expected_dir_exists(generated_basic: Path, dirname: str):
    """Test each expected directory exists. Parametrized for visibility without performance impact."""
    dir_path = generated_basic / dirname
    assert dir_path.is_dir(), f"Missing expected directory: {dirname}"


def test_package_name_matches(generated_basic: Path):
    # The package directory should exist under src
    assert (generated_basic / "src" / "example_proj").is_dir()


def test_answers_contains_author_email(generated_basic: Path):
    # Ensure the author email is captured in the answers file
    answers = (generated_basic / ".copier-answers.yml").read_text()
    assert "test@test.com" in answers


def test_readme_contains_project_description(generated_basic: Path):
    readme = (generated_basic / "README.md").read_text()
    assert "Example description" in readme


def test_dummy_test_exists_in_generated_project(generated_basic: Path):
    """Test that a dummy test file exists in the generated project's tests directory."""
    dummy_test = generated_basic / "tests" / "test_dummy.py"
    assert dummy_test.is_file(), "Missing dummy test file in generated project"
