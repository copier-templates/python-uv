"""Regression tests for the local workflow harness (`scripts/maintainer/workflow_test.py`).

Profiles are JSON data under `scripts/maintainer/workflows/`; the shell entry
point is a thin `exec` adapter and `lib/inject_step.py` is gone. Only pure
behavior is pinned here: Docker and `act` are never invoked.
"""

from __future__ import annotations

import ast
import functools
import importlib.util
import json
import os
import re
import subprocess
import sys
import types
from pathlib import Path

import pytest
from _projects import TEMPLATE_ROOT, git

MAINTAINER = TEMPLATE_ROOT / "scripts" / "maintainer"
HARNESS = MAINTAINER / "workflow_test.py"
PROFILES_DIR = MAINTAINER / "workflows"
ADAPTER = MAINTAINER / "test-workflow.sh"
COMMON = MAINTAINER / "lib" / "common.sh"
CANONICAL_IMAGE = "catthehacker/ubuntu:act-24.04"
PROFILE_NAMES = ("prek", "test")
HARNESS_HELPERS = (
    "ensure_docker",
    "run_actionlint",
    "stage_workflows",
    "inject_snippet",
    "run_act",
    "print_summary",
    "repo_root",
)

SAMPLE_WORKFLOW = """\
name: Sample

on:
  workflow_dispatch:

jobs:
  alpha:
    runs-on: ubuntu-latest
    steps:
      - name: Alpha first
        run: echo alpha
  beta:
    runs-on: ubuntu-latest
    steps:
      - name: Beta first
        run: echo beta
"""

NO_STEPS_WORKFLOW = """\
name: No steps

on:
  workflow_dispatch:

jobs:
  notify:
    runs-on: ubuntu-latest
"""

NO_STEPS_THEN_STEPS_WORKFLOW = """\
name: No steps then steps

on:
  workflow_dispatch:

jobs:
  notify:
    runs-on: ubuntu-latest
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Build
        run: echo build
"""

SAMPLE_SNIPPET = """\
      - name: "[act-local] shim"
        run: echo shim
"""

ACT_LOG = """\
[Test/Test] [1/4] Success - Checkout repository [0.3s]
[Test/Test] [2/4] Success - Install toolchain [12.4s]
[Test/Test] [2/4] Success - Install toolchain [10.1s]
[Test/Test] [3/4] Failure - Run tests [5.6s]
[Test/Test] [4/4] Success - Upload artifact [0.2s]
[Test/Test] 🏁  Job failed
"""

ACT_SUCCESS_LOG = """\
[Test/Test] [1/1] Success - Run tests [0.1s]
[Test/Test] 🏁  Job succeeded
"""

FAKE_ACT_SCRIPT = """\
#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$PWD" > "$FAKE_ACT_CWD"
printf '%s\\n' "$@" > "$FAKE_ACT_ARGS"
if [[ -n ${FAKE_ACT_STDOUT:-} ]]; then
  cat "$FAKE_ACT_STDOUT"
fi
exit "${FAKE_ACT_RC:-0}"
"""

FAKE_TOOL_SCRIPTS = {
    "actionlint": "#!/usr/bin/env bash\nexit 0\n",
    "docker": "#!/usr/bin/env bash\nprintf 'Docker version 0.0.0-fake\\n'\n",
}


@functools.lru_cache(maxsize=1)
def _harness() -> types.ModuleType:
    """Import the harness by path: a missing file fails the test, not collection."""
    assert HARNESS.is_file(), f"Missing workflow harness: {HARNESS}"
    spec = importlib.util.spec_from_file_location("workflow_test", HARNESS)
    assert spec is not None and spec.loader is not None, f"Unimportable harness: {HARNESS}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_harness(*args: str, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    assert HARNESS.is_file(), f"Missing workflow harness: {HARNESS}"
    return subprocess.run(  # noqa: S603
        [sys.executable, str(HARNESS), *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
    )


def _install_fake_tools(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir()
    for name, content in {"act": FAKE_ACT_SCRIPT, **FAKE_TOOL_SCRIPTS}.items():
        path = bin_dir / name
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)
    return bin_dir


def _fake_act_env(tmp_path: Path, bin_dir: Path, *, log: str, rc: int = 0) -> dict[str, str]:
    stdout_path = tmp_path / "fake-act-stdout.log"
    stdout_path.write_text(log, encoding="utf-8")
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    env["FAKE_ACT_CWD"] = str(tmp_path / "fake-act-cwd")
    env["FAKE_ACT_ARGS"] = str(tmp_path / "fake-act-args")
    env["FAKE_ACT_STDOUT"] = str(stdout_path)
    env["FAKE_ACT_RC"] = str(rc)
    return env


def _init_act_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    workflows = repo / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "test.yml").write_text("name: Test\non: pull_request\njobs: {}\n", encoding="utf-8")
    git(repo, "init", "-q")
    return repo


def _read_act_args(tmp_path: Path) -> list[str]:
    return (tmp_path / "fake-act-args").read_text(encoding="utf-8").splitlines()


# --- profiles: JSON data replaces the sourced `.sh` files -------------------


def test_profile_json_files_replace_sourced_shell_profiles():
    assert {path.name for path in PROFILES_DIR.glob("*.json")} == {f"{name}.json" for name in PROFILE_NAMES}
    shells = sorted(path.name for path in PROFILES_DIR.glob("*.sh"))
    assert not shells, f"Legacy sourced workflow profiles remain: {shells}"


def test_profiles_never_reference_ghcr_registry():
    paths = sorted(PROFILES_DIR.glob("*.json"))
    assert paths, f"No JSON workflow profiles under {PROFILES_DIR}"
    for path in paths:
        assert "ghcr.io" not in path.read_text(), f"ghcr.io reference in {path}"


def test_load_profiles_returns_name_keyed_profile_mapping():
    """`load_profiles(dir)` returns `{name: Profile}` for every `*.json` in `dir`."""
    module = _harness()
    profiles = module.load_profiles(PROFILES_DIR)
    assert set(profiles) == set(PROFILE_NAMES)
    assert all(isinstance(profile, module.Profile) for profile in profiles.values())


def test_load_profile_rejects_missing_keys_with_a_friendly_value_error(tmp_path: Path):
    path = tmp_path / "broken.json"
    path.write_text(json.dumps({"workflow_file": ".github/workflows/test.yml"}), encoding="utf-8")

    with pytest.raises(ValueError, match=rf"{re.escape(str(path))}: missing required key"):
        _harness().load_profile(path)


def test_load_profile_rejects_invalid_values_with_a_friendly_value_error(tmp_path: Path):
    path = tmp_path / "broken.json"
    path.write_text(
        json.dumps(
            {
                "workflow_file": ".github/workflows/test.yml",
                "event": "pull_request",
                "job": "test",
                "image": "example/image:tag",
                "needs_git_shim": "yes",
                "shim_snippet": None,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r'"needs_git_shim" must be true or false'):
        _harness().load_profile(path)


def test_prek_profile_pins_scheduled_auto_update():
    profile = _harness().load_profiles(PROFILES_DIR)["prek"]
    assert profile.workflow_file == ".github/workflows/prek.yml"
    assert profile.event == "workflow_dispatch"
    assert profile.job == "auto-update"
    assert profile.image == CANONICAL_IMAGE
    assert profile.needs_git_shim is True
    assert profile.shim_snippet == "prek-shim.yml"


def test_test_profile_pins_pull_request_job_without_shim():
    profile = _harness().load_profiles(PROFILES_DIR)["test"]
    assert profile.workflow_file == ".github/workflows/test.yml"
    assert profile.event == "pull_request"
    assert profile.job == "test"
    assert profile.image == CANONICAL_IMAGE
    assert profile.needs_git_shim is False
    assert profile.shim_snippet is None


def test_every_profile_references_existing_workflow_and_snippet():
    profiles = _harness().load_profiles(PROFILES_DIR)
    for name, profile in profiles.items():
        assert (TEMPLATE_ROOT / profile.workflow_file).is_file(), f"{name}: missing {profile.workflow_file}"
        if profile.needs_git_shim:
            assert profile.shim_snippet is not None, f"{name}: shim flag without snippet"
            assert (PROFILES_DIR / profile.shim_snippet).is_file(), f"{name}: missing {profile.shim_snippet}"


def test_default_image_matches_the_canonical_registryless_image():
    """The fallback image must not drift from the pinned profiles."""
    module = _harness()
    assert module.DEFAULT_IMAGE == CANONICAL_IMAGE
    assert "ghcr.io" not in HARNESS.read_text(encoding="utf-8")


def test_harness_parses_as_python39():
    """The harness must run on the README-promised system python3 (3.9)."""
    ast.parse(HARNESS.read_text(encoding="utf-8"), feature_version=(3, 9))


# --- inject_step: act-local snippet insertion --------------------------------


def test_inject_step_inserts_snippet_as_first_step_of_named_job():
    result = _harness().inject_step(SAMPLE_WORKFLOW, "beta", SAMPLE_SNIPPET)
    lines = result.splitlines()
    beta = lines.index("  beta:")
    steps = lines.index("    steps:", beta)
    first_step = lines.index("      - name: Beta first", steps)
    begin = next(i for i, line in enumerate(lines) if "# ACT-LOCAL-BEGIN" in line)
    end = next(i for i, line in enumerate(lines) if "# ACT-LOCAL-END" in line)

    assert result.count("# ACT-LOCAL-BEGIN") == 1
    assert begin == steps + 1, "the injected block must follow the job's `steps:` line"
    assert begin < end < first_step, "the injected block must precede the original first step"
    assert "\n".join(lines[begin + 1 : end]) + "\n" == SAMPLE_SNIPPET, "snippet bytes must be preserved"


@pytest.mark.parametrize(
    "workflow_text",
    [
        SAMPLE_WORKFLOW,
        SAMPLE_WORKFLOW.replace("\n", "\r\n"),
        SAMPLE_WORKFLOW.rstrip("\n"),
    ],
    ids=["lf", "crlf", "no-trailing-newline"],
)
def test_inject_step_leaves_the_rest_of_the_workflow_byte_identical(workflow_text: str):
    module = _harness()
    result = module.inject_step(workflow_text, "beta", SAMPLE_SNIPPET)
    begin = result.index(f"      {module.BEGIN_MARKER}")
    end = result.index(f"      {module.END_MARKER}\n") + len(f"      {module.END_MARKER}\n")

    assert result[:begin] + result[end:] == workflow_text


def test_inject_step_rejects_unknown_job():
    with pytest.raises(ValueError):
        _harness().inject_step(SAMPLE_WORKFLOW, "gamma", SAMPLE_SNIPPET)


def test_inject_step_rejects_job_without_steps():
    with pytest.raises(ValueError):
        _harness().inject_step(NO_STEPS_WORKFLOW, "notify", SAMPLE_SNIPPET)


def test_inject_step_does_not_borrow_steps_from_a_later_job():
    with pytest.raises(ValueError, match=r"no 'steps:'"):
        _harness().inject_step(NO_STEPS_THEN_STEPS_WORKFLOW, "notify", SAMPLE_SNIPPET)


# --- stage_workflows: scratch copy -------------------------------------------


def test_stage_workflows_copies_only_top_level_workflow_yaml(tmp_path: Path):
    repo = tmp_path / "repo"
    workflows = repo / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "one.yml").write_text("name: one\n")
    (workflows / "two.yml").write_text("name: two\n")
    (workflows / "ignored.yaml").write_text("name: ignored\n")
    (workflows / "notes.txt").write_text("notes\n")
    (workflows / "nested").mkdir()
    (workflows / "nested" / "three.yml").write_text("name: three\n")
    (repo / "root.yml").write_text("name: root\n")
    dest = tmp_path / "stage"

    _harness().stage_workflows(repo, dest)

    assert {path.name for path in dest.iterdir()} == {"one.yml", "two.yml"}
    assert (dest / "one.yml").read_text() == "name: one\n"
    assert (dest / "two.yml").read_text() == "name: two\n"


# --- act log summary ---------------------------------------------------------


def test_summarize_returns_sorted_unique_step_results():
    assert _harness().summarize(ACT_LOG) == [
        "Failure: Run tests",
        "Success: Checkout repository",
        "Success: Install toolchain",
        "Success: Upload artifact",
    ]


def test_summarize_returns_empty_list_without_step_results():
    assert _harness().summarize("[Test/Test] 🏁  Job succeeded\n") == []


@pytest.mark.parametrize(
    ("log_text", "expected"),
    [
        ("[Test/Test] 🏁  Job succeeded\n", True),
        (ACT_LOG, False),
        ("[Test/Test] 🏁  Job failed\n", False),
        ("", False),
    ],
    ids=["succeeded", "steps-only", "failed", "empty"],
)
def test_job_succeeded_requires_the_act_job_marker(log_text: str, expected: bool):
    assert _harness().job_succeeded(log_text) is expected


# --- CLI adapter -------------------------------------------------------------


def test_cli_list_prints_every_profile_from_any_cwd(tmp_path: Path):
    proc = _run_harness("--list", cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    for expected in (*PROFILE_NAMES, ".github/workflows/prek.yml", ".github/workflows/test.yml"):
        assert expected in proc.stdout, f"`--list` output missing {expected!r}"


def test_cli_help_exits_zero_without_docker(tmp_path: Path):
    proc = _run_harness("--help", cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert "usage" in proc.stdout.lower()


def test_cli_unknown_profile_exits_one_and_lists_available_names(tmp_path: Path):
    proc = _run_harness("does-not-exist", cwd=tmp_path)
    output = proc.stdout + proc.stderr
    assert proc.returncode == 1, output
    assert "does-not-exist" in output
    for name in PROFILE_NAMES:
        assert name in output, f"unknown-profile error must list {name!r}"


def test_cli_missing_profile_name_exits_one(tmp_path: Path):
    proc = _run_harness(cwd=tmp_path)
    assert proc.returncode == 1, proc.stderr
    assert "Missing workflow name." in proc.stderr


def test_cli_unknown_flag_keeps_argparse_exit_two(tmp_path: Path):
    proc = _run_harness("--bogus-flag", cwd=tmp_path)
    assert proc.returncode == 2


def test_shim_profile_rejects_empty_job_override_with_clear_error(tmp_path: Path):
    """`--job ""` cannot inject a shim: fail with a `--job` hint, not a raw lookup error."""
    repo = _init_act_repo(tmp_path)
    (repo / ".github" / "workflows" / "prek.yml").write_text(
        "name: Prek\non: workflow_dispatch\njobs:\n  auto-update:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n",
        encoding="utf-8",
    )
    bin_dir = _install_fake_tools(tmp_path)
    env = _fake_act_env(tmp_path, bin_dir, log=ACT_SUCCESS_LOG)

    proc = _run_harness("prek", "--job", "", cwd=repo, env=env)

    assert proc.returncode == 1, proc.stderr
    assert "required" in proc.stderr.lower()
    assert "--job" in proc.stderr
    assert "job '' not found" not in proc.stderr
    assert not (tmp_path / "fake-act-args").exists(), "act must not run without a shim job"


def test_shell_adapter_lists_profiles_from_an_unrelated_cwd(tmp_path: Path):
    proc = subprocess.run(  # noqa: S603
        [str(ADAPTER), "--list"],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert proc.returncode == 0, proc.stderr
    for expected in (*PROFILE_NAMES, ".github/workflows/prek.yml", ".github/workflows/test.yml"):
        assert expected in proc.stdout, f"adapter `--list` output missing {expected!r}"


# --- act invocation: fake `act` records cwd, args, and exit behavior ---------


def test_act_runs_from_repository_root_when_invoked_from_nested_directory(tmp_path: Path):
    repo = _init_act_repo(tmp_path)
    bin_dir = _install_fake_tools(tmp_path)
    nested = repo / "nested" / "deeper"
    nested.mkdir(parents=True)
    env = _fake_act_env(tmp_path, bin_dir, log=ACT_SUCCESS_LOG)

    proc = _run_harness("test", cwd=nested, env=env)

    assert proc.returncode == 0, proc.stderr
    recorded_cwd = (tmp_path / "fake-act-cwd").read_text(encoding="utf-8").strip()
    assert Path(recorded_cwd).resolve() == repo.resolve()


def test_act_arguments_keep_profile_fallbacks_and_append_env_args_after_amd64(tmp_path: Path):
    repo = _init_act_repo(tmp_path)
    bin_dir = _install_fake_tools(tmp_path)
    env = _fake_act_env(tmp_path, bin_dir, log=ACT_SUCCESS_LOG)
    env["ACT_EXTRA_ARGS"] = "--matrix os:ubuntu-latest --verbose"

    proc = _run_harness("test", "--amd64", "--event", "", "--image", "", cwd=repo, env=env)

    assert proc.returncode == 0, proc.stderr
    args = _read_act_args(tmp_path)
    assert args[0] == "-W"
    assert Path(args[1]).name.startswith("act-workflows-")
    assert args[2:9] == [
        "pull_request",
        "-j",
        "test",
        "-P",
        f"ubuntu-latest={CANONICAL_IMAGE}",
        "--container-daemon-socket",
        "-",
    ]
    assert args[9:] == [
        "--container-architecture",
        "linux/amd64",
        "--matrix",
        "os:ubuntu-latest",
        "--verbose",
    ]


def test_run_act_appends_env_args_after_caller_extra_args(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = _harness()
    bin_dir = _install_fake_tools(tmp_path)
    env = _fake_act_env(tmp_path, bin_dir, log=ACT_SUCCESS_LOG)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("ACT_EXTRA_ARGS", "--env-flag value")

    rc = module.run_act(
        tmp_path / "staged",
        "workflow_dispatch",
        "job",
        CANONICAL_IMAGE,
        tmp_path / "act.log",
        extra_args=("--profile-flag", "p"),
        cwd=tmp_path,
    )

    assert rc == 0
    assert _read_act_args(tmp_path)[-4:] == ["--profile-flag", "p", "--env-flag", "value"]


def test_failed_summary_exits_nonzero_when_act_succeeds(tmp_path: Path):
    repo = _init_act_repo(tmp_path)
    bin_dir = _install_fake_tools(tmp_path)
    env = _fake_act_env(tmp_path, bin_dir, log=ACT_LOG)

    proc = _run_harness("test", cwd=repo, env=env)

    assert proc.returncode == 1
    output = proc.stdout + proc.stderr
    assert "JOB FAILED" in output
    assert "Failure: Run tests" in output


def test_act_nonzero_exit_code_is_propagated(tmp_path: Path):
    repo = _init_act_repo(tmp_path)
    bin_dir = _install_fake_tools(tmp_path)
    env = _fake_act_env(tmp_path, bin_dir, log=ACT_SUCCESS_LOG, rc=7)

    proc = _run_harness("test", cwd=repo, env=env)

    assert proc.returncode == 7, proc.stderr


def test_act_stream_survives_undecodable_output(tmp_path: Path):
    repo = _init_act_repo(tmp_path)
    bin_dir = _install_fake_tools(tmp_path)
    env = _fake_act_env(tmp_path, bin_dir, log=ACT_SUCCESS_LOG)
    Path(env["FAKE_ACT_STDOUT"]).write_bytes(b"\xff\xfe\n[Test/Test] \xf0\x9f\x8f\x81  Job succeeded\n")

    proc = _run_harness("test", cwd=repo, env=env)

    assert proc.returncode == 0, proc.stderr
    assert "Job succeeded" in proc.stdout


def test_shell_adapter_is_a_thin_exec_wrapper_without_profile_sourcing():
    assert ADAPTER.is_file(), f"Missing shell adapter: {ADAPTER}"
    assert os.access(ADAPTER, os.X_OK), f"Adapter not executable: {ADAPTER}"
    content = ADAPTER.read_text()
    assert "exec python3" in content
    assert "workflow_test.py" in content

    assert not re.search(r"^\s*(?:source|\.)\s+", content, re.MULTILINE), "Adapter must not source profiles"
    assert "common.sh" not in content
    assert not re.search(r"workflows/\S+\.sh", content), "Adapter must not reference sourced profiles"

    last_line = content.strip().splitlines()[-1]
    for token in ("exec", "python3", "workflow_test.py", '"$@"'):
        assert token in last_line, f"Adapter must end with the exec line; got {last_line!r}"


# --- common.sh: only die/need_cmd + error logging stay -----------------------


@pytest.mark.parametrize("helper", HARNESS_HELPERS)
def test_common_sh_drops_harness_helper(helper: str):
    content = COMMON.read_text()
    assert not re.search(rf"^\s*(?:function\s+)?{helper}\s*\(\s*\)", content, re.MULTILINE), (
        f"lib/common.sh still defines harness-only {helper}()"
    )


@pytest.mark.parametrize("helper", ("log_info", "log_ok", "log_warn"))
def test_common_sh_drops_dead_logging_helpers(helper: str):
    content = COMMON.read_text()
    assert not re.search(rf"^{helper}\(\)", content, re.MULTILINE), (
        f"lib/common.sh still defines unused {helper}(); release CLIs only use die/need_cmd"
    )


def test_common_sh_drops_scripts_dir_global():
    assert COMMON.is_file()
    assert "SCRIPTS_DIR" not in COMMON.read_text()


def test_common_sh_header_does_not_claim_the_workflow_harness_sources_it():
    header = COMMON.read_text(encoding="utf-8").split("set -euo pipefail", 1)[0]
    assert "workflow" not in header.lower()
    assert "release" in header.lower()


@pytest.mark.parametrize("helper", ("die", "need_cmd", "log_error"))
def test_common_sh_keeps_shared_release_helpers(helper: str):
    content = COMMON.read_text()
    assert re.search(rf"^{helper}\(\)", content, re.MULTILINE), f"lib/common.sh must keep {helper}()"
