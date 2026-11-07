"""Release automation: version resolution, orphan-tag cleanup, workflow pins.

`scripts/maintainer/release/*.sh` holds the logic (unit-tested here with a
stub `gh`); `.github/workflows/release.yml` is thin wiring (pinned by text
assertions). The workflow is root-only: it must never render into generated projects.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from pathlib import Path

import pytest
from _projects import GIT, TEMPLATE_ROOT, ProjectRegistry, git

RELEASE_WORKFLOW = TEMPLATE_ROOT / ".github" / "workflows" / "release.yml"
RESOLVE_SCRIPT = TEMPLATE_ROOT / "scripts" / "maintainer" / "release" / "resolve-version.sh"
CLEANUP_SCRIPT = TEMPLATE_ROOT / "scripts" / "maintainer" / "release" / "cleanup-tag.sh"


def _write_stub_gh(bin_dir: Path) -> None:
    """Stub `gh api` for PR lookups; labels drive the tests."""
    stub = bin_dir / "gh"
    stub.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "$2" == *"/commits/"*"/pulls" ]]; then
  printf '%s' "$STUB_PRS_JSON"
elif [[ "$2" == *"/pulls/"* ]]; then
  printf '%s' "$STUB_PR_JSON"
else
  echo "stub gh: unexpected args: $*" >&2
  exit 3
fi
"""
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)


@pytest.fixture()
def stub_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Env with stub `gh` first on PATH; caller sets STUB_* fixtures."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_stub_gh(bin_dir)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    env.pop("GITHUB_OUTPUT", None)
    monkeypatch.setenv("PATH", env["PATH"])
    return env


def _prs(*entries: dict) -> str:
    return json.dumps(entries)


def _pr(number: int, *labels: str, state: str = "open", base: str = "main") -> dict:
    return {
        "number": number,
        "state": state,
        "base": {"ref": base},
        "head": {"ref": "feat-x"},
        "body": "Implements feature.",
        "labels": [{"name": name} for name in labels],
    }


def _resolve(env: dict[str, str], *args: str, prs: str = "[]", pr: str = "") -> subprocess.CompletedProcess[str]:
    out = Path(env["_OUT"])
    return subprocess.run(  # noqa: S603
        [str(RESOLVE_SCRIPT), "--repo", "o/r", *args, "--output", str(out)],
        check=False,
        capture_output=True,
        text=True,
        env={**env, "STUB_PRS_JSON": prs, "STUB_PR_JSON": pr},
    )


SHA_ARGS = ("--sha", "abc123")


@pytest.fixture()
def resolve_env(stub_env: dict[str, str], tmp_path: Path) -> dict[str, str]:
    out = tmp_path / "github-output"
    out.write_text("")
    return {**stub_env, "_OUT": str(out)}


def _outputs(env: dict[str, str]) -> dict[str, str]:
    pairs = (line.split("=", 1) for line in Path(env["_OUT"]).read_text().splitlines() if "=" in line)
    return dict(pairs)


def test_release_scripts_are_executable_guarded_bash():
    for script in (RESOLVE_SCRIPT, CLEANUP_SCRIPT):
        assert os.access(script, os.X_OK), f"Not executable: {script}"
        content = script.read_text()
        assert content.startswith("#!/usr/bin/env bash")
        assert "set -euo pipefail" in content


def test_resolve_help_and_flags():
    proc = subprocess.run([str(RESOLVE_SCRIPT), "--help"], check=False, capture_output=True, text=True)  # noqa: S603
    assert proc.returncode == 0
    assert "--sha" in proc.stdout and "--pr" in proc.stdout
    proc = subprocess.run([str(RESOLVE_SCRIPT), "--bogus"], check=False, capture_output=True, text=True)  # noqa: S603
    assert proc.returncode == 2


def test_cleanup_help_and_flags():
    proc = subprocess.run([str(CLEANUP_SCRIPT), "--help"], check=False, capture_output=True, text=True)  # noqa: S603
    assert proc.returncode == 0
    assert "--sha" in proc.stdout
    proc = subprocess.run([str(CLEANUP_SCRIPT), "--bogus"], check=False, capture_output=True, text=True)  # noqa: S603
    assert proc.returncode == 2


def test_resolve_skips_when_no_open_pr(resolve_env: dict[str, str]):
    proc = _resolve(resolve_env, *SHA_ARGS, prs=_prs())
    assert proc.returncode == 0, proc.stderr
    assert _outputs(resolve_env) == {"release": "false"}


def test_resolve_skips_when_pr_has_no_release_label(resolve_env: dict[str, str]):
    proc = _resolve(resolve_env, *SHA_ARGS, prs=_prs(_pr(7, "documentation")))
    assert proc.returncode == 0, proc.stderr
    assert _outputs(resolve_env) == {"release": "false"}


def test_resolve_fails_on_multiple_release_labels(resolve_env: dict[str, str]):
    proc = _resolve(resolve_env, *SHA_ARGS, prs=_prs(_pr(7, "release:patch", "release:minor")))
    assert proc.returncode == 1
    assert "exactly one" in proc.stderr


def test_resolve_fails_on_unknown_release_label(resolve_env: dict[str, str]):
    proc = _resolve(resolve_env, *SHA_ARGS, prs=_prs(_pr(7, "release:hotfix")))
    assert proc.returncode == 1
    assert "unknown release label" in proc.stderr


@pytest.mark.parametrize(
    ("label", "bump"),
    [("release:patch", "patch"), ("release:minor", "minor"), ("release:major", "major")],
    ids=["patch", "minor", "major"],
)
def test_resolve_maps_label_to_bump(resolve_env: dict[str, str], label: str, bump: str):
    proc = _resolve(resolve_env, *SHA_ARGS, prs=_prs(_pr(7, "documentation", label)))
    assert proc.returncode == 0, proc.stderr
    assert _outputs(resolve_env) == {"release": "true", "pr": "7", "head_ref": "feat-x", "bump": bump}


def test_resolve_by_pr_number(resolve_env: dict[str, str]):
    single = json.dumps(_pr(9, "release:minor"))
    proc = _resolve(resolve_env, "--pr", "9", pr=single)
    assert proc.returncode == 0, proc.stderr
    assert _outputs(resolve_env) == {"release": "true", "pr": "9", "head_ref": "feat-x", "bump": "minor"}


def test_resolve_by_pr_skips_closed_pr(resolve_env: dict[str, str]):
    single = json.dumps(_pr(9, "release:minor", state="closed"))
    proc = _resolve(resolve_env, "--pr", "9", pr=single)
    assert proc.returncode == 0, proc.stderr
    assert _outputs(resolve_env) == {"release": "false"}


def test_resolve_rejects_sha_and_pr_together(resolve_env: dict[str, str]):
    proc = _resolve(resolve_env, "--sha", "abc123", "--pr", "9")
    assert proc.returncode == 2


def _init_origin_with_tag(tmp_path: Path, tag_on_main: bool) -> Path:
    """Bare origin + clone; tag 0.3.0 either on main (kept) or a side branch (orphan)."""
    git(tmp_path, "-c", "init.defaultBranch=main", "init", "--bare", "origin.git")
    git(tmp_path, "clone", "origin.git", "work")
    work = tmp_path / "work"
    (work / "app.py").write_text("print('hi')\n")
    git(work, "add", "-A")
    git(work, "commit", "-m", "Init")
    git(work, "push", "origin", "main")
    if tag_on_main:
        git(work, "tag", "0.3.0")
    else:
        git(work, "checkout", "-b", "feat")
        (work / "feature.py").write_text("print('feature')\n")
        git(work, "add", "-A")
        git(work, "commit", "-m", "Feature")
        git(work, "tag", "0.3.0")
        git(work, "checkout", "main")
    git(work, "push", "origin", "0.3.0")
    return work


def _head_sha(work: Path, ref: str = "HEAD") -> str:
    proc = subprocess.run(  # noqa: S603
        [GIT, "rev-parse", ref],
        check=True,
        capture_output=True,
        text=True,
        cwd=work,
    )
    return proc.stdout.strip()


def _cleanup(env: dict[str, str], work: Path, sha: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [str(CLEANUP_SCRIPT), "--sha", sha],
        check=False,
        capture_output=True,
        text=True,
        cwd=work,
        env=env,
    )


def _origin_has_tag(work: Path, tag: str) -> bool:
    proc = subprocess.run(  # noqa: S603
        [GIT, "ls-remote", "origin", f"refs/tags/{tag}"],
        check=False,
        capture_output=True,
        text=True,
        cwd=work,
    )
    return bool(proc.stdout.strip())


def test_cleanup_skips_without_pointing_tags(stub_env: dict[str, str], tmp_path: Path):
    work = _init_origin_with_tag(tmp_path, tag_on_main=False)
    proc = _cleanup(stub_env, work, _head_sha(work, "main"))
    assert proc.returncode == 0, proc.stderr
    assert "nothing to clean" in proc.stdout
    assert _origin_has_tag(work, "0.3.0")


def test_cleanup_deletes_orphan_tag(stub_env: dict[str, str], tmp_path: Path):
    work = _init_origin_with_tag(tmp_path, tag_on_main=False)
    proc = _cleanup(stub_env, work, _head_sha(work, "feat"))
    assert proc.returncode == 0, proc.stderr
    assert "orphan tag 0.3.0" in proc.stdout
    assert not _origin_has_tag(work, "0.3.0")


def test_cleanup_keeps_mainline_tag(stub_env: dict[str, str], tmp_path: Path):
    work = _init_origin_with_tag(tmp_path, tag_on_main=True)
    proc = _cleanup(stub_env, work, _head_sha(work, "main"))
    assert proc.returncode == 0, proc.stderr
    assert "on mainline; keeping" in proc.stdout
    assert _origin_has_tag(work, "0.3.0")


def _workflow_text() -> str:
    return RELEASE_WORKFLOW.read_text()


def test_release_workflow_triggers():
    text = _workflow_text()
    assert 'workflows: ["Test"]' in text
    assert "types: [completed]" in text
    assert "workflow_dispatch" in text
    assert "types: [closed]" in text


def test_release_job_gates_on_green_pr_ci():
    text = _workflow_text()
    assert "github.event.workflow_run.event == 'pull_request'" in text
    assert "github.event.workflow_run.conclusion == 'success'" in text


def test_release_job_uses_release_token_with_write():
    text = _workflow_text()
    assert "secrets.RELEASE_TOKEN" in text
    assert "contents: write" in text
    assert "pull-requests: write" in text


def test_release_job_never_plain_force_pushes():
    text = _workflow_text()
    assert "--force-with-lease" in text
    assert len(re.findall(r"--force(?!-with-lease)", text)) == 0


def test_release_job_merges_with_merge_commit():
    text = _workflow_text()
    assert "--merge" in text
    assert "--squash" not in text
    assert "--rebase" not in text


def test_release_job_uses_bot_identity():
    text = _workflow_text()
    assert "github-actions[bot]" in text
    assert "41898282+github-actions[bot]@users.noreply.github.com" in text


def test_release_job_calls_release_scripts():
    text = _workflow_text()
    assert "scripts/maintainer/release/resolve-version.sh" in text
    assert "scripts/maintainer/release/cleanup-tag.sh" in text
    assert "scripts/release/resolve-version.sh" not in text
    assert "scripts/release/cleanup-tag.sh" not in text
    assert "./scripts/release.sh" in text
    assert "--print-version" in text
    assert "mise run ci" in text


def test_release_workflow_resolves_version_from_labels():
    text = _workflow_text()
    assert "milestone" not in text
    assert "Fixes" not in text
    script = RESOLVE_SCRIPT.read_text()
    assert "release:patch" in script
    assert "milestone" not in script.lower()


def test_cleanup_job_guards_unmerged_and_mainline():
    workflow = _workflow_text()
    assert "merged == false" in workflow
    script = CLEANUP_SCRIPT.read_text()
    assert "merge-base --is-ancestor" in script
    assert "push --delete" in script


def test_release_workflow_is_root_only(projects: ProjectRegistry):
    assert RELEASE_WORKFLOW.is_file()
    assert not (TEMPLATE_ROOT / "templates" / ".github" / "workflows" / "release.yml").exists()
    project = projects.render("github")
    assert not (project / ".github" / "workflows" / "release.yml").exists()
    assert not (project / "scripts" / "maintainer").exists()
    assert not (project / "scripts" / "release").exists()
