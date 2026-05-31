"""Ensure excluded paths are not rendered into generated projects."""

from __future__ import annotations

from pathlib import Path

import pytest

# Module-level constants: defined once per module load, not recreated per test
# Note: .github is excluded from this list because it now includes ISSUE_TEMPLATE which should be in generated projects
EXCLUDED_DIRS = [
    ".git",
    ".vscode",
    ".chlog",
    ".pytest_cache",
    "docs",
    "my_tests",
    "examples",
    "hooks",
    ".github/extensions",
    "src/copier_python_uv.egg-info",
]
EXCLUDED_FILES = ["copier.yaml", "SECURITY.md", "uv.lock"]


@pytest.mark.parametrize("dirname", EXCLUDED_DIRS, ids=lambda x: f"excluded_dir:{x}")
def test_excluded_directories_are_absent(generated_basic: Path, dirname: str):
    """Test excluded directories are absent. Parametrized for visibility without performance impact.

    Directories listed as excluded must not be present in the generated project.
    Note: Copier may create empty directories even if files are excluded.
    This test checks that the directory either doesn't exist OR is empty.

    Session-scoped fixture ensures fast execution: fixture is created once per session,
    parametrization only multiplies test invocations (not setup overhead).
    """
    p = generated_basic / dirname
    if p.exists():
        contents = list(p.iterdir())
        assert len(contents) == 0, (
            f"Excluded directory {dirname} should be empty but contains: {[item.name for item in contents]}"
        )


@pytest.mark.parametrize("filename", EXCLUDED_FILES, ids=lambda x: f"excluded_file:{x}")
def test_excluded_files_are_absent(generated_basic: Path, filename: str):
    """Test excluded files are absent. Parametrized for visibility without performance impact.

    Files listed as excluded must not be present in the generated project.
    """
    p = generated_basic / filename
    assert not p.exists(), f"Excluded artifact present: {filename}"
