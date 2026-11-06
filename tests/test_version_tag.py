"""Version-vs-tag push gate (Q1-Q13).

`pyproject.toml [project] version` must equal the max-semver plain X.Y.Z tag
reachable from HEAD. Blocks both directions with recovery hints.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from _projects import TEMPLATE_ROOT, ProjectRegistry, git, load_toml, mise_toml


def _script() -> Path:
    return TEMPLATE_ROOT / "templates" / "scripts" / "check-version-tag.sh"


def _init_version_repo(tmp_path: Path, version: str) -> Path:
    """Git repo with a pyproject version and no tags yet."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(f'[project]\nname = "demo"\nversion = "{version}"\n', encoding="utf-8")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "init")
    return repo


def _run_check(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [str(_script())],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )


def test_check_script_exists_executable_guarded_bash():
    script = _script()
    assert script.is_file(), f"Missing check script: {script}"
    assert os.access(script, os.X_OK), f"Check script not executable: {script}"
    content = script.read_text()
    assert content.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in content


def test_check_script_blocks_both_directions_with_hints():
    content = _script().read_text()
    assert "pyproject" in content.lower()
    # Both drift directions must fail with recovery guidance.
    assert "mise run release" in content
    assert "--follow-tags" in content


def test_check_script_sources_payload_helper_and_version_module():
    """Shared logging and version math come from the payload, not inline heredocs."""
    content = _script().read_text()
    assert "lib/release-common.sh" in content
    assert "release_version.py" in content
    for inline in ("def key(", "tuple(map(int"):
        assert inline not in content, f"check-version-tag.sh still embeds {inline!r}"


def test_check_script_passes_when_no_tags_are_reachable(tmp_path: Path):
    repo = _init_version_repo(tmp_path, "0.3.0")

    proc = _run_check(repo)

    assert proc.returncode == 0, proc.stderr
    assert "OK" in proc.stdout


def test_check_script_passes_when_head_is_unborn(tmp_path: Path):
    """A fresh repo has no HEAD yet; the tag comparison must not fail on it."""
    repo = tmp_path / "unborn"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "0.1.0"\n', encoding="utf-8")
    git(repo, "init", "-q", "-b", "main")

    proc = _run_check(repo)

    assert proc.returncode == 0, proc.stderr
    assert "No X.Y.Z tags reachable" in proc.stdout
    assert "Could not compare tags by semver." not in proc.stderr


def test_check_script_passes_when_version_matches_latest_tag(tmp_path: Path):
    repo = _init_version_repo(tmp_path, "0.3.0")
    git(repo, "tag", "0.3.0")

    proc = _run_check(repo)

    assert proc.returncode == 0, proc.stderr
    assert "matches latest tag" in proc.stdout


def test_check_script_blocks_version_ahead_of_latest_tag(tmp_path: Path):
    repo = _init_version_repo(tmp_path, "0.4.0")
    git(repo, "tag", "0.3.0")

    proc = _run_check(repo)

    assert proc.returncode == 1
    assert "Blocked:" in proc.stderr
    assert "ahead" in proc.stderr
    assert "mise run release" in proc.stderr
    assert "--follow-tags" in proc.stderr


def test_check_script_blocks_tag_ahead_of_version(tmp_path: Path):
    repo = _init_version_repo(tmp_path, "0.3.0")
    git(repo, "tag", "0.4.0")

    proc = _run_check(repo)

    assert proc.returncode == 1
    assert "Blocked:" in proc.stderr
    assert "Never delete the tag" in proc.stderr
    assert "mise run release" in proc.stderr
    assert "--follow-tags" in proc.stderr


def test_check_script_compares_tags_numerically(tmp_path: Path):
    """0.10.0 is newer than 0.9.0; a lexicographic comparison would block this repo."""
    repo = _init_version_repo(tmp_path, "0.10.0")
    git(repo, "tag", "0.9.0")
    git(repo, "tag", "0.10.0")

    proc = _run_check(repo)

    assert proc.returncode == 0, proc.stderr


def test_check_script_avoids_bash4_only_builtins():
    # macOS ships bash 3.2, which lacks `mapfile`/`readarray`.
    assert not re.search(r"^\s*(mapfile|readarray)\b", _script().read_text(), re.M)


def test_check_script_help_exits_zero():
    proc = subprocess.run(  # noqa: S603
        [str(_script()), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "pyproject" in proc.stdout.lower()


def test_prek_pre_push_hook_runs_mise_version_tag_task():
    config = load_toml(TEMPLATE_ROOT / "templates" / "prek.toml")
    hooks = {hook["id"]: hook for repo in config["repos"] for hook in repo["hooks"]}
    hook = hooks["check-version-tag"]
    assert hook.get("stages") == ["pre-push"]
    assert hook["entry"] == "mise run check:version-tag"


def test_mise_tasks_expose_check_version_tag():
    root_tasks = load_toml(TEMPLATE_ROOT / "mise.toml")["tasks"]
    assert "check:version-tag" in root_tasks


def test_rendered_mise_has_check_version_tag(projects: ProjectRegistry):
    data = mise_toml(projects.render("basic"))
    assert "check:version-tag" in data["tasks"]


def test_release_script_shows_local_and_remote_tags():
    content = (TEMPLATE_ROOT / "templates" / "scripts" / "release.sh").read_text()
    assert "ls-remote" in content
    assert "Never push automatically" in content


def test_rendered_project_ships_check_script(projects: ProjectRegistry):
    project = projects.render("basic")
    script = project / "scripts" / "check-version-tag.sh"
    assert script.is_file()
    assert os.access(script, os.X_OK), "Rendered check script must stay executable"
