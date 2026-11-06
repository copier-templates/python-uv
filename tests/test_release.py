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


def _shell_function(name: str) -> str:
    """Extract a top-level shell function from the release script."""
    content = _root_script().read_text()
    start = content.index(f"{name}() {{")
    end = content.index("\n}\n", start) + len("\n}\n")
    return content[start:end]


def test_latest_remote_tag_sorts_numerically():
    """`git ls-remote` output -> highest plain X.Y.Z tag (regression: sort bug)."""
    helper = _shell_function("latest_remote_tag")

    refs = "\n".join(
        [
            "aaa\trefs/tags/0.9.0",
            "bbb\trefs/tags/0.10.0",
            "ccc\trefs/tags/0.10.0^{}",
            "ddd\trefs/tags/v1.0.0",
            "eee\trefs/tags/latest",
            "",
        ]
    )
    proc = subprocess.run(  # noqa: S603
        ["bash", "-c", f'{helper}\nlatest_remote_tag "$1"', "_", refs],  # noqa: S607
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "0.10.0"


def test_suggested_version_never_uses_semver_bump():
    """`feat`/breaking commits must never suggest a minor/major bump."""
    content = _root_script().read_text()
    assert "--bumped-version" not in content, "release suggestion must not use git-cliff's semver bump"


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (("0.2.1", "", ""), "0.2.1"),  # first release: keep pyproject version
        (("0.2.1", "0.2.1", ""), "0.2.2"),  # patch above the local tag
        (("0.2.1", "", "0.2.5"), "0.2.6"),  # patch above the remote tag
        (("0.1.0", "0.9.9", "0.10.0"), "0.10.1"),  # numeric, never minor
        (("0.3.0", "0.2.1", ""), "0.3.1"),  # pyproject ahead of tags
    ],
    ids=["first-release", "above-local", "above-remote", "numeric-never-minor", "pyproject-ahead"],
)
def test_suggested_version_always_bumps_patch(args: tuple[str, str, str], expected: str):
    """Patch above the highest known version, never a minor/major bump."""
    helper = _shell_function("suggested_version")
    proc = subprocess.run(  # noqa: S603
        ["bash", "-c", f'{helper}\nsuggested_version "$@"', "_", *args],  # noqa: S607
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == expected


def test_off_main_prompt_defaults_to_no():
    """Off main/master the interactive prompt must default to (and be able to) abort."""
    content = _root_script().read_text()
    assert "--default=false" in content
    assert 'gum confirm "Release from' in content
    assert "Aborted, nothing changed." in content


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
    "scripts/workflows/prek.sh",
    "scripts/workflows/test.sh",
    "scripts/test-workflow.sh",
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
    """Template-dev scripts must not leak; the release script must ship."""
    project = projects.render("basic")
    for rel in (
        "scripts/lib",
        "scripts/workflows",
        "scripts/test-workflow.sh",
        "scripts/README.md",
        "scripts/update_python_versions.py",
    ):
        assert not (project / rel).exists(), f"Leaked template-dev file: {rel}"
    assert (project / "scripts" / "release.sh").is_file()
