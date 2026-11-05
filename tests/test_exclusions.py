"""Excluded paths must not render into generated projects."""

from __future__ import annotations

import pytest
from _projects import ProjectRegistry

# With `_subdirectory: templates`, only files under `templates/` are copied; these once leaked via the root.
# `tests/` is deliberately absent: `templates/tests/` legitimately renders as the generated `tests/` package.
EXCLUDED_PATHS = [
    ".vscode",
    ".agents",
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
    "copier.yaml",
    "SECURITY.md",
    "AGENTS.md",
    ".env",
    "summary.md",
]


@pytest.mark.parametrize("relpath", EXCLUDED_PATHS)
def test_excluded_paths_are_absent(projects: ProjectRegistry, relpath: str):
    """Copier may leave an empty directory behind, so an excluded directory must be absent or empty."""
    path = projects.render("basic") / relpath
    assert not path.exists() or (path.is_dir() and not any(path.iterdir())), f"Excluded path present: {relpath}"


def test_payload_tests_package_is_rendered(projects: ProjectRegistry):
    """Positive guard: the `templates/tests/` payload must still render as the generated `tests/` package."""
    project = projects.render("basic")
    for relpath in ("tests/__init__.py", "tests/unit/test_init.py"):
        assert (project / relpath).is_file(), f"payload file missing from generated project: {relpath}"


@pytest.mark.parametrize(("variant", "present"), [("github", True), ("no-github", False)])
def test_github_dir_follows_github_integration(projects: ProjectRegistry, variant: str, present: bool):
    project = projects.render(variant)
    assert (project / ".github" / "workflows" / "test.yml").is_file() is present
    assert (project / ".github").exists() is present
