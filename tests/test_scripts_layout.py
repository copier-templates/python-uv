"""The `scripts/` seam: top-level Payload adapters, root-only maintainer tooling.

Root `scripts/` keeps only symlinks into `templates/scripts/` (the Payload),
plus this directory's README and the root-only `maintainer/` tree. Maintainer
scripts never render into generated projects.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from _projects import TEMPLATE_ROOT, ProjectRegistry, load_toml

SCRIPTS = TEMPLATE_ROOT / "scripts"
PAYLOAD = TEMPLATE_ROOT / "templates"

PAYLOAD_FILES = (
    "scripts/release.sh",
    "scripts/check-version-tag.sh",
    "scripts/release_version.py",
    "scripts/lib/release-common.sh",
)

MAINTAINER_MOVES = (
    ("scripts/maintainer/release", "scripts/release"),
    ("scripts/maintainer/lib/common.sh", "scripts/lib/common.sh"),
    ("scripts/maintainer/workflows", "scripts/workflows"),
    ("scripts/maintainer/test-workflow.sh", "scripts/test-workflow.sh"),
    ("scripts/maintainer/update_python_versions.py", "scripts/update_python_versions.py"),
)


def _resolves_into_payload(path: Path) -> bool:
    """True when `path` is a symlink whose target lives under `templates/`."""
    return path.is_symlink() and path.resolve().is_relative_to(PAYLOAD.resolve())


def _is_payload_adapter(path: Path) -> bool:
    """A symlink into the Payload, or a directory containing only such symlinks."""
    if _resolves_into_payload(path):
        return True
    if path.is_dir():
        entries = [entry for entry in path.iterdir() if entry.name != "__pycache__"]
        return bool(entries) and all(_resolves_into_payload(entry) for entry in entries)
    return False


def test_top_level_scripts_are_payload_adapters():
    """Root scripts must be symlinks into `templates/scripts/`, never real copies."""
    assert SCRIPTS.is_dir(), f"Missing scripts directory: {SCRIPTS}"
    allowed = {"README.md", "maintainer", "__pycache__"}
    offenders = sorted(
        entry.name for entry in SCRIPTS.iterdir() if entry.name not in allowed and not _is_payload_adapter(entry)
    )
    assert not offenders, (
        "Top-level scripts/ must hold only symlinks into templates/ (plus README.md and maintainer/); "
        f"found real files: {offenders}"
    )


@pytest.mark.parametrize("rel", PAYLOAD_FILES)
def test_payload_adapter_is_a_relative_symlink_into_templates(rel: str):
    """Adapters must be relative symlinks so the checkout works from any path."""
    link = TEMPLATE_ROOT / rel
    assert link.is_symlink(), f"Payload adapter is not a symlink: {rel}"
    target = os.readlink(link)
    assert not os.path.isabs(target), f"{rel} uses an absolute symlink target: {target}"
    assert link.resolve().is_relative_to(PAYLOAD.resolve()), f"{rel} must resolve into templates/"


@pytest.mark.parametrize(("new_path", "old_path"), MAINTAINER_MOVES)
def test_maintainer_tooling_lives_under_scripts_maintainer(new_path: str, old_path: str):
    """Maintainer-only tooling lives under `scripts/maintainer/`, not at the scripts root."""
    assert (TEMPLATE_ROOT / new_path).exists(), f"Missing maintainer path: {new_path}"
    assert not (TEMPLATE_ROOT / old_path).exists(), f"Legacy top-level path still present: {old_path}"


def test_maintainer_tooling_never_renders(projects: ProjectRegistry):
    """Root maintainer tooling must not leak; the Payload release files must ship."""
    assert (SCRIPTS / "maintainer").is_dir(), "root maintainer tooling must exist before checking it does not ship"
    project = projects.render("basic")
    assert not (project / "scripts" / "maintainer").exists(), "Leaked maintainer tooling into generated project"
    for rel in PAYLOAD_FILES:
        assert (project / rel).is_file(), f"Missing shipped Payload file: {rel}"


def test_mise_update_task_uses_maintainer_path():
    """`mise run update:python-versions` drives the maintainer copy of the script."""
    task = load_toml(TEMPLATE_ROOT / "mise.toml")["tasks"]["update:python-versions"]
    assert "scripts/maintainer/update_python_versions.py" in task["run"]
    assert "scripts/update_python_versions.py" not in task["run"]


def test_release_workflow_uses_maintainer_paths():
    """`release.yml` calls the maintainer release CLIs, not their old top-level paths."""
    workflow = (TEMPLATE_ROOT / ".github" / "workflows" / "release.yml").read_text()
    for rel in (
        "scripts/maintainer/release/resolve-version.sh",
        "scripts/maintainer/release/cleanup-tag.sh",
    ):
        assert rel in workflow, f"release.yml must call {rel}"
    assert "scripts/release/" not in workflow


def test_python_version_marker_names_maintainer_path():
    """The managed marker names the script's maintainer path, matching the module constant."""
    copier_yaml = (TEMPLATE_ROOT / "copier.yaml").read_text()
    assert (
        "# python-version-choices: begin "
        "(managed by scripts/maintainer/update_python_versions.py, do not edit)" in copier_yaml
    )
    assert "managed by scripts/update_python_versions.py" not in copier_yaml


@pytest.mark.parametrize("rel", ["CODING_STANDARDS.md", "docs/architecture.md"])
def test_docs_describe_the_scripts_seam(rel: str):
    """Maintainer docs describe the Payload-vs-maintainer split and the new paths."""
    text = (TEMPLATE_ROOT / rel).read_text()
    assert "scripts/maintainer/" in text, f"{rel} must document scripts/maintainer/"
    assert "scripts/release/" not in text, f"{rel} still documents the old scripts/release/ path"


def test_architecture_tree_nests_maintainer_under_scripts():
    """The architecture tree must show `maintainer/` as a child of `scripts/`, not a sibling."""
    lines = (TEMPLATE_ROOT / "docs" / "architecture.md").read_text().splitlines()
    scripts_index = next(index for index, line in enumerate(lines) if "── scripts/" in line)
    nested = lines[scripts_index + 1]
    assert "maintainer/" in nested, f"expected maintainer/ directly under scripts/, got: {nested!r}"
    assert nested.startswith("│"), "maintainer/ must be drawn as a child of scripts/ in the tree"


def test_scripts_readme_names_the_real_layout_tests_and_maintainer_wording():
    """README must point at the layout tests that actually assert the seam."""
    readme = (SCRIPTS / "README.md").read_text()
    assert "tests/test_scripts_layout.py" in readme
    assert "tests/test_exclusions.py" not in readme
    assert "Maintainer tooling" in readme


def test_scripts_readme_documents_tag_collision_recovery():
    """A release can abort on an existing tag; README must say how to recover without moving it."""
    readme = (SCRIPTS / "README.md").read_text().lower()
    assert "already exists" in readme
    assert "never move a published tag" in readme
    assert "delete the stale" in readme or "git tag -d" in readme
