"""The `scripts/` seam: top-level Payload adapters, root-only maintainer tooling.

Root `scripts/` keeps only symlinks into `templates/scripts/` (the Payload),
plus this directory's README and the root-only `maintainer/` tree. Maintainer
scripts never render into generated projects.
"""

from __future__ import annotations

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
    ("scripts/maintainer/lib/inject_step.py", "scripts/lib/inject_step.py"),
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
