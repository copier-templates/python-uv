"""Ensure excluded paths are not rendered into generated projects."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import TEMPLATE_ROOT

# Module-level constants: defined once per module load, not recreated per test
# With `_subdirectory: templates`, only files under `templates/` are copied.
# These dirs must never appear in generated projects (once leaked via root copy).
EXCLUDED_DIRS = [
    ".vscode",
    ".chlog",
    ".pytest_cache",
    ".pyscn",
    "docs",
    "my_tests",
    "examples",
    "hooks",
    "extensions",
    ".github/extensions",
    "scripts",
    "src/copier_python_uv.egg-info",
    "templates",
    "licenses",
]
EXCLUDED_FILES = [
    "copier.yaml",
    "SECURITY.md",
    "AGENTS.md",
    ".env",
    "summary.md",
]


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


def test_all_jinja_templates_live_under_templates_dir():
    """Regression test: every `*.jinja` file must live under `templates/`."""
    jinja_files = list(TEMPLATE_ROOT.rglob("*.jinja"))
    assert jinja_files, "Expected at least one *.jinja template"
    outside = [
        p.relative_to(TEMPLATE_ROOT) for p in jinja_files if "templates" not in p.relative_to(TEMPLATE_ROOT).parts
    ]
    assert not outside, f"Jinja templates outside templates/: {outside}"


def test_copier_subdirectory_is_templates():
    """Regression test: `copier.yaml` must render payload from `templates/`."""
    copier_config = (TEMPLATE_ROOT / "copier.yaml").read_text()
    assert "_subdirectory: templates" in copier_config
