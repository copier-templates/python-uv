"""Core structural tests for the Copier template output."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

# Module-level constants: defined once per module load, not recreated per test
EXPECTED_FILES = [
    ".copier-answers.yml",
    ".gitattributes",
    ".gitignore",
    ".pre-commit-config.yaml",
    "mise.toml",
    "pyproject.toml",
    "README.md",
    "uv.lock",
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


def test_generated_unit_test_has_standard_module_spacing(generated_basic: Path):
    test_file = (generated_basic / "tests" / "unit" / "test_init.py").read_text()

    assert '"""Test the main application entry point."""\n\nfrom ' in test_file
    assert test_file.endswith("\n")
    assert not test_file.endswith("\n\n")


def test_generated_library_unit_test_has_standard_eof(generated_library: Path):
    test_file = (generated_library / "tests" / "unit" / "test_init.py").read_text()

    assert test_file.endswith("\n")
    assert not test_file.endswith("\n\n")


def test_initial_commit_includes_uv_lock(generated_basic: Path):
    git = shutil.which("git")
    assert git is not None

    committed_files = subprocess.run(  # noqa: S603
        [git, "ls-tree", "-r", "--name-only", "HEAD"],
        cwd=generated_basic,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()

    assert "uv.lock" in committed_files
