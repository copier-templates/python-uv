"""Ensure excluded paths are not rendered into generated projects."""

from __future__ import annotations

from pathlib import Path

import pytest
import tomllib
from conftest import TEMPLATE_ROOT

# Module-level constants: defined once per module load, not recreated per test
# With `_subdirectory: templates`, only files under `templates/` are copied.
# These dirs must never appear in generated projects (once leaked via root copy).
# `tests/` is deliberately absent from this list: it is this repo's local suite (formerly
# `my_tests/`), but `templates/tests/` is the payload that legitimately renders as the
# generated project's `tests/` package. Local-only modules are guarded by LOCAL_ONLY_FILES.
EXCLUDED_DIRS = [
    ".vscode",
    ".opencode",
    ".chlog",
    ".pytest_cache",
    ".pyscn",
    "docs",
    "examples",
    "hooks",
    "extensions",
    ".github/extensions",
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
# Local-only validation modules: they live in `tests/` alongside the payload's `tests/` package,
# so they are guarded by name. The payload must never render them into generated projects.
LOCAL_ONLY_FILES = [
    "tests/conftest.py",
    "tests/test_exclusions.py",
    "tests/test_conditional_sections.py",
]
# Content markers that must never appear in any text file of a generated project.
LOCAL_ONLY_CONTENT_MARKERS = ["my_tests"]
# Directories skipped by the content-marker leak scan (VCS metadata, virtualenv, caches).
LEAK_SCAN_SKIP_DIRS = {".git", ".venv", "__pycache__"}
PAYLOAD_TESTS_DIR = TEMPLATE_ROOT / "templates" / "tests"
ROOT_PYPROJECT = TEMPLATE_ROOT / "pyproject.toml"
ROOT_MISE_TOML = TEMPLATE_ROOT / "mise.toml"


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


def test_local_only_suite_is_not_a_legacy_dir():
    """`my_tests/` must be gone: the suite was moved to `tests/`, not duplicated."""
    assert not (TEMPLATE_ROOT / "my_tests").exists(), "legacy my_tests/ still exists; the rename must be a move"


def test_pyproject_testpaths_points_at_tests():
    """`[tool.pytest.ini_options].testpaths` must be exactly `["tests"]`."""
    pyproject = tomllib.loads(ROOT_PYPROJECT.read_text())
    testpaths = pyproject["tool"]["pytest"]["ini_options"]["testpaths"]
    assert testpaths == ["tests"], f"testpaths must be ['tests'], got {testpaths!r}"


def test_mise_test_unit_runs_tests_dir():
    """`mise run test:unit` must invoke pytest against `tests/`."""
    mise = tomllib.loads(ROOT_MISE_TOML.read_text())
    run = mise["tasks"]["test:unit"].get("run", "")
    run_text = "\n".join(str(entry) for entry in run) if isinstance(run, list) else str(run)
    # Check the retired path first: `my_tests/` contains `tests/` as a substring.
    assert "my_tests" not in run_text, f"`test:unit` still targets the retired path, got {run_text!r}"
    assert "pytest tests/" in run_text, f"`test:unit` must run `pytest tests/`, got {run_text!r}"


def test_payload_tests_dir_is_untouched():
    """The rename must not touch the `templates/tests/` payload.

    Generated projects legitimately get a `tests/` package from this payload, so the
    local `tests/` directory and the payload must stay separate trees.
    """
    assert (PAYLOAD_TESTS_DIR / "__init__.py.jinja").is_file(), (
        f"payload template missing: {PAYLOAD_TESTS_DIR / '__init__.py.jinja'}"
    )
    assert (PAYLOAD_TESTS_DIR / "unit" / "test_init.py.jinja").is_file(), (
        f"payload template missing: {PAYLOAD_TESTS_DIR / 'unit' / 'test_init.py.jinja'}"
    )
    assert not (PAYLOAD_TESTS_DIR / "test_exclusions.py").exists(), (
        "local-only test module must never be added to the Copier payload"
    )


@pytest.mark.parametrize("relpath", LOCAL_ONLY_FILES, ids=lambda x: f"local_only:{x}")
def test_local_only_test_modules_are_absent(generated_basic: Path, relpath: str):
    """Local-only validation modules must never be rendered into generated projects."""
    assert not (generated_basic / relpath).exists(), f"local-only module leaked into generated project: {relpath}"


def test_payload_tests_package_is_rendered(generated_basic: Path):
    """Positive guard: the `templates/tests/` payload must still render as the generated `tests/` package."""
    for relpath in ("tests/__init__.py", "tests/unit/test_init.py"):
        assert (generated_basic / relpath).is_file(), f"payload file missing from generated project: {relpath}"


def test_no_local_content_markers_leak_into_generated_project(generated_basic: Path):
    """Content-marker leak scan: no local-only marker may appear in any generated text file."""
    leaks: list[str] = []
    for path in generated_basic.rglob("*"):
        rel = path.relative_to(generated_basic)
        if not path.is_file() or LEAK_SCAN_SKIP_DIRS.intersection(rel.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        leaks.extend(f"{rel} contains {marker!r}" for marker in LOCAL_ONLY_CONTENT_MARKERS if marker in text)
    assert not leaks, f"local-only content leaked into generated project: {leaks}"
