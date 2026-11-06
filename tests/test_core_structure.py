"""Structure of a rendered default project."""

from __future__ import annotations

import re

import pytest
from _projects import ProjectRegistry, git

EXPECTED_FILES = [
    ".copier-answers.yml",
    ".gitattributes",
    ".gitignore",
    "prek.toml",
    "cliff.toml",
    "mise.toml",
    "pyproject.toml",
    "whitelist_vulture.py",
    "README.md",
    "uv.lock",
]
EXPECTED_DIRS = ["src", "tests"]


def test_expected_files_and_dirs_exist(projects: ProjectRegistry):
    project = projects.render("basic")
    missing = [f for f in EXPECTED_FILES if not (project / f).is_file()]
    missing += [d for d in EXPECTED_DIRS if not (project / d).is_dir()]
    assert not missing, f"Missing expected paths: {missing}"


@pytest.mark.parametrize("variant", ["basic", "lib"])
def test_generated_unit_test_has_standard_module_spacing(projects: ProjectRegistry, variant: str):
    test_file = (projects.render(variant) / "tests" / "unit" / "test_init.py").read_text()

    assert re.match(r'""".*"""\n\n(from|import) ', test_file)
    assert test_file.endswith("\n")
    assert not test_file.endswith("\n\n")


def test_render_from_snapshot_records_init_commit_with_lock(projects: ProjectRegistry):
    """The lifecycle script ran via `_copier_conf.src_path` (the snapshot is not a git repo)."""
    project = projects.render("basic")

    assert git(project, "log", "--format=%s").stdout.splitlines() == ["Init commit"]
    assert "uv.lock" in git(project, "ls-tree", "-r", "--name-only", "HEAD").stdout.splitlines()
