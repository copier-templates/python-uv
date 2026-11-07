"""Regression tests for the release workflow (`mise run release`)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from _projects import TEMPLATE_ROOT, ProjectRegistry, git, mise_toml


def _root_script() -> Path:
    return TEMPLATE_ROOT / "scripts" / "release.sh"


def test_release_script_is_executable_guarded_bash():
    script = _root_script()
    assert os.access(script, os.X_OK), f"Release script not executable: {script}"
    content = script.read_text()
    assert content.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in content


def test_release_script_help_exits_zero():
    proc = subprocess.run(  # noqa: S603
        [str(_root_script()), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "--version" in proc.stdout
    assert "--yes" in proc.stdout


def test_release_script_rejects_unknown_flags():
    proc = subprocess.run(  # noqa: S603
        [str(_root_script()), "--bogus"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2


def test_release_script_sources_payload_common_helper():
    """Shipped logging lives in one payload file, not duplicated per script."""
    content = _root_script().read_text()
    assert "lib/release-common.sh" in content
    for duplicate in ("log_info() {", "log_ok() {", "log_warn() {", "die() {", "_C_OK="):
        assert duplicate not in content, f"release.sh still defines {duplicate!r}; source lib/release-common.sh"


def test_release_script_delegates_version_math_to_module():
    """Version parsing/bumping/suggestion belongs to `release_version.py`."""
    content = _root_script().read_text()
    assert "release_version.py" in content
    for inline in ("latest_remote_tag() {", "suggested_version() {", "def key("):
        assert inline not in content, f"release.sh still embeds {inline!r}"


def test_suggested_version_supports_exact_version_override():
    """`--version` still releases an exact version regardless of bump math."""
    content = _root_script().read_text()
    assert "--version" in content
    assert "pass either --version or --bump, not both" in content


def _tag(repo: Path, tag: str) -> None:
    git(repo, "tag", tag)


def test_print_version_computes_bump_without_side_effects(tmp_path: Path):
    """`--print-version` previews the KIND bump without touching the tree."""
    repo = _init_release_repo(tmp_path, "main")
    _tag(repo, "0.1.0")
    git(repo, "commit", "-q", "--allow-empty", "-m", "feat: x")
    before = (repo / "pyproject.toml").read_text(encoding="utf-8")

    for bump, expected in (("patch", "0.1.1"), ("minor", "0.2.0"), ("major", "1.0.0")):
        proc = subprocess.run(  # noqa: S603
            [str(_root_script()), "--bump", bump, "--print-version"],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip().splitlines()[-1] == expected
    assert (repo / "pyproject.toml").read_text(encoding="utf-8") == before
    assert not (repo / "CHANGELOG.md").exists()


def test_print_version_works_on_dirty_tree(tmp_path: Path):
    """Preview is pure computation: dirty tree must not block it."""
    repo = _init_release_repo(tmp_path, "main")
    (repo / "dirty.txt").write_text("uncommitted\n", encoding="utf-8")

    proc = subprocess.run(  # noqa: S603
        [str(_root_script()), "--bump", "patch", "--print-version"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().splitlines()[-1] == "0.1.0"


def test_release_rejects_version_with_bump(tmp_path: Path):
    repo = _init_release_repo(tmp_path, "main")

    proc = subprocess.run(  # noqa: S603
        [str(_root_script()), "--version", "0.2.0", "--bump", "minor", "--print-version"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    assert proc.returncode == 1
    assert "either --version or --bump" in proc.stderr


def test_release_rejects_invalid_bump(tmp_path: Path):
    repo = _init_release_repo(tmp_path, "main")

    proc = subprocess.run(  # noqa: S603
        [str(_root_script()), "--bump", "huge", "--print-version"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    assert proc.returncode == 2
    assert "Invalid bump" in proc.stderr


def test_bare_run_prints_verbose_help():
    """Running the script without flags must explain itself."""
    proc = subprocess.run(  # noqa: S603
        [str(_root_script()), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    for marker in ("--bump", "--print-version", "Exit codes:", "Examples:"):
        assert marker in proc.stdout


def test_off_main_prompt_defaults_to_no():
    """Off main/master the interactive prompt must default to (and be able to) abort."""
    content = _root_script().read_text()
    assert "--default=false" in content
    assert 'gum confirm "Release from' in content
    assert "Aborted, nothing changed." in content


def test_release_amends_head_instead_of_new_commit():
    """Release files must amend HEAD, never form a standalone release commit."""
    content = _root_script().read_text()
    assert "git commit --amend --no-edit" in content
    assert 'git commit -m "chore(release)' not in content
    assert "Amend HEAD and tag" in content


def test_release_aborts_when_head_is_release_commit():
    """The script must refuse to amend when HEAD already starts with chore(release)."""
    content = _root_script().read_text()
    assert "last_subject" in content
    assert "chore\\(release\\)" in content
    assert "already a release commit" in content


def test_release_commit_aborts_on_release_head(tmp_path: Path):
    """A HEAD of `chore(release)...` must abort before touching release files."""
    repo = _init_release_repo(tmp_path, "main")
    git(repo, "commit", "-q", "--allow-empty", "-m", "chore(release): prepare for 0.1.0")
    pyproject_before = (repo / "pyproject.toml").read_text(encoding="utf-8")

    proc = subprocess.run(  # noqa: S603
        [str(_root_script())],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )

    assert proc.returncode == 1
    assert "already a release commit" in proc.stderr
    assert (repo / "pyproject.toml").read_text(encoding="utf-8") == pyproject_before
    assert not (repo / "CHANGELOG.md").exists()


def test_release_commit_passes_guard_on_normal_head(tmp_path: Path):
    """A normal HEAD must pass the release-commit guard (later gates may apply)."""
    repo = _init_release_repo(tmp_path, "main")

    proc = subprocess.run(  # noqa: S603
        [str(_root_script())],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )

    assert "already a release commit" not in proc.stderr


def _init_release_repo(path: Path, branch: str) -> Path:
    repo = path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "0.1.0"\n', encoding="utf-8")
    git(repo, "init", "-q", "-b", branch)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "init")
    return repo


def test_off_main_branch_aborts_without_yes(tmp_path: Path):
    """Non-interactive off-main run must stop before touching any release file."""
    repo = _init_release_repo(tmp_path, "feat/side-quest")
    pyproject_before = (repo / "pyproject.toml").read_text(encoding="utf-8")

    proc = subprocess.run(  # noqa: S603
        [str(_root_script())],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )

    assert proc.returncode == 1
    assert "expected main/master" in proc.stderr
    assert "feat/side-quest" in proc.stderr
    assert (repo / "pyproject.toml").read_text(encoding="utf-8") == pyproject_before
    assert not (repo / "CHANGELOG.md").exists()


def test_main_branch_passes_branch_gate(tmp_path: Path):
    """On main the branch gate must not fire (later gates may still apply)."""
    repo = _init_release_repo(tmp_path, "main")

    proc = subprocess.run(  # noqa: S603
        [str(_root_script())],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )

    assert "expected main/master" not in proc.stderr
    assert (repo / "pyproject.toml").read_text(encoding="utf-8").strip().endswith('version = "0.1.0"')


ACT_IMAGE_SCRIPTS = (
    "scripts/maintainer/workflows/prek.sh",
    "scripts/maintainer/workflows/test.sh",
    "scripts/maintainer/test-workflow.sh",
)


@pytest.mark.parametrize("rel", ACT_IMAGE_SCRIPTS, ids=["prek", "test", "test-workflow"])
def test_act_image_reference_is_canonical(rel: str):
    """All ACT-image references must use the same registryless image."""
    canonical = 'ACT_IMAGE="catthehacker/ubuntu:act-24.04"'
    script = TEMPLATE_ROOT / rel
    assert script.is_file(), f"Missing script: {script}"
    content = script.read_text()
    if "ACT_IMAGE=" in content:
        assert canonical in content, f"Non-canonical ACT_IMAGE in {script}"
    assert "ghcr.io" not in content, f"ghcr.io reference in {script}"


def test_rendered_mise_has_release_task_and_gum(projects: ProjectRegistry):
    """Both mise.toml variants must pin gum and expose the release task."""
    for project in (projects.render("basic"), projects.render("python313")):
        data = mise_toml(project)
        assert "gum" in data["tools"]
        assert "release" in data["tasks"]
        assert "release.sh" in data["tasks"]["release"]["run"]


def test_generated_readme_documents_release(projects: ProjectRegistry):
    project = projects.render("basic")
    readme = (project / "README.md").read_text()
    assert "mise run release" in readme


def test_root_only_scripts_are_absent(projects: ProjectRegistry):
    """Maintainer scripts must not leak; the payload release files must ship."""
    project = projects.render("basic")
    for rel in (
        "scripts/maintainer",
        "scripts/README.md",
        "scripts/lib/common.sh",
        "scripts/lib/inject_step.py",
        "scripts/release",
        "scripts/workflows",
        "scripts/test-workflow.sh",
        "scripts/update_python_versions.py",
    ):
        assert not (project / rel).exists(), f"Leaked template-dev file: {rel}"
    lib_entries = {entry.name for entry in (project / "scripts" / "lib").iterdir()}
    assert lib_entries == {"release-common.sh"}, f"Unexpected scripts/lib payload: {sorted(lib_entries)}"
    for rel in (
        "scripts/release.sh",
        "scripts/check-version-tag.sh",
        "scripts/release_version.py",
        "scripts/lib/release-common.sh",
    ):
        assert (project / rel).is_file(), f"Missing shipped release file: {rel}"
