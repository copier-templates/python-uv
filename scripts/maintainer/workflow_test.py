#!/usr/bin/env python3
"""Local GitHub Actions harness: lint a workflow, then run its job via `act`.

Profiles are JSON data under ``scripts/maintainer/workflows/`` (one file per
workflow). This module owns everything else: profile loading, scratch staging,
act-local step injection, the Docker/actionlint/act adapters, and the act log
summary. It is stdlib-only and runs on the system ``python3`` (3.9+).
"""

# ruff: noqa: S603, UP045 -- the wrapper runs the system python3 (3.9) without
# `from __future__ import annotations`, so `X | None` unions cannot be evaluated;
# this CLI intentionally executes tools resolved from PATH.
# NOTE: no `from __future__ import annotations`: tests import this module by path
# without registering it in `sys.modules`, and string annotations make
# `@dataclass` look the module up (CPython dataclasses `_is_type`).
import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn, Optional, TextIO, cast

HERE = Path(__file__).resolve().parent
PROFILES_DIR = HERE / "workflows"
DEFAULT_IMAGE = "catthehacker/ubuntu:act-24.04"
BEGIN_MARKER = "# ACT-LOCAL-BEGIN"
END_MARKER = "# ACT-LOCAL-END"

_STEP_RESULT_RE = re.compile(r"(Success|Failure) - (.*) \[[^\]]*\]")
_JOB_SUCCEEDED_RE = re.compile(r"Job succeeded\b")


@dataclass(frozen=True)
class Profile:
    """One local-test profile, pinned as JSON under ``workflows/``."""

    workflow_file: str
    event: str
    job: str
    image: str
    needs_git_shim: bool
    shim_snippet: Optional[str]
    extra_args: tuple[str, ...] = ()


_PROFILE_KEYS = ("workflow_file", "event", "job", "image", "needs_git_shim", "shim_snippet")
_STRING_PROFILE_KEYS = ("workflow_file", "event", "job", "image")


def _profile_data(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"{path}: cannot read profile: {error}") from error
    if not isinstance(data, dict):
        raise ValueError(f"{path}: profile must be a JSON object")
    return data


def _check_profile_keys(data: dict[str, object], path: Path) -> None:
    missing = [key for key in _PROFILE_KEYS if key not in data]
    if missing:
        raise ValueError(f"{path}: missing required key(s): {', '.join(missing)}")
    unknown = sorted(set(data) - set(_PROFILE_KEYS) - {"extra_args"})
    if unknown:
        raise ValueError(f"{path}: unknown key(s): {', '.join(unknown)}")


def _check_profile_types(data: dict[str, object], path: Path) -> None:
    for key in _STRING_PROFILE_KEYS:
        if not isinstance(data[key], str):
            raise ValueError(f'{path}: "{key}" must be a string')
    if not isinstance(data["needs_git_shim"], bool):
        raise ValueError(f'{path}: "needs_git_shim" must be true or false')
    shim_snippet = data["shim_snippet"]
    if shim_snippet is not None and not isinstance(shim_snippet, str):
        raise ValueError(f'{path}: "shim_snippet" must be a string or null')


def load_profile(path: Path) -> Profile:
    """Load and validate one JSON profile, raising a friendly ``ValueError``."""
    path = Path(path)
    data = _profile_data(path)
    _check_profile_keys(data, path)
    _check_profile_types(data, path)
    extra_args = data.get("extra_args", [])
    if extra_args is None:
        extra_args = []
    if not isinstance(extra_args, list) or not all(isinstance(arg, str) for arg in extra_args):
        raise ValueError(f'{path}: "extra_args" must be a list of strings')

    return Profile(
        workflow_file=cast(str, data["workflow_file"]),
        event=cast(str, data["event"]),
        job=cast(str, data["job"]),
        image=cast(str, data["image"]),
        needs_git_shim=cast(bool, data["needs_git_shim"]),
        shim_snippet=cast(Optional[str], data["shim_snippet"]),
        extra_args=tuple(cast(list[str], extra_args)),
    )


def load_profiles(profiles_dir: Path) -> dict[str, Profile]:
    """Load every ``*.json`` profile in ``profiles_dir`` keyed by file stem."""
    return {path.stem: load_profile(path) for path in sorted(Path(profiles_dir).glob("*.json"))}


def _without_eol(line: str) -> str:
    return line.rstrip("\r\n")


def inject_step(workflow_text: str, job: str, snippet: str) -> str:
    """Insert ``snippet`` as the first step of ``job``, preserving all else.

    The block is wrapped in ``BEGIN_MARKER``/``END_MARKER`` comments so callers
    can detect (and refuse to keep) act-local shims. Raises ``ValueError`` when
    the job or its ``steps:`` block is missing.
    """
    lines = workflow_text.splitlines(keepends=True)
    job_line = f"  {job}:"
    job_index: Optional[int] = None
    for index, line in enumerate(lines):
        if _without_eol(line) == job_line:
            job_index = index
            break
    if job_index is None:
        raise ValueError(f"job {job!r} not found")

    steps_index: Optional[int] = None
    for index in range(job_index + 1, len(lines)):
        content = _without_eol(lines[index])
        stripped = content.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(content) - len(content.lstrip(" "))
        if indent <= 2:
            break  # dedent to another job (or the next top-level key)
        if content == "    steps:":
            steps_index = index
            break
    if steps_index is None:
        raise ValueError(f"no 'steps:' found for job {job!r}")

    if not snippet.endswith("\n"):
        snippet += "\n"
    block = [
        f"      {BEGIN_MARKER} (temporary, local `act` runs only)\n",
        snippet,
        f"      {END_MARKER}\n",
    ]
    return "".join(lines[: steps_index + 1] + block + lines[steps_index + 1 :])


def stage_workflows(repo_root: Path, dest: Path) -> None:
    """Copy only top-level ``.github/workflows/*.yml`` files into ``dest``."""
    source = Path(repo_root) / ".github" / "workflows"
    target = Path(dest)
    target.mkdir(parents=True, exist_ok=True)
    for path in sorted(source.glob("*.yml")):
        shutil.copy2(path, target / path.name)


def summarize(log_text: str) -> list[str]:
    """Return sorted, unique ``Success: <step>``/``Failure: <step>`` results."""
    results = set()
    for line in log_text.splitlines():
        match = _STEP_RESULT_RE.search(line)
        if match is not None:
            results.add(f"{match.group(1)}: {match.group(2).strip()}")
    return sorted(results)


def job_succeeded(log_text: str) -> bool:
    """True only when the act job marker says the whole job succeeded."""
    return _JOB_SUCCEEDED_RE.search(log_text) is not None


def repository_root() -> Path:
    """Return the current git repository root, or exit with a clear error."""
    git = shutil.which("git")
    if git is None:
        _die("Not inside a git repository.")
    try:
        proc = subprocess.run(
            [git, "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        _die("Not inside a git repository.")
    if proc.returncode != 0 or not proc.stdout.strip():
        _die("Not inside a git repository.")
    return Path(proc.stdout.strip())


def _command_works(args: Sequence[str]) -> bool:
    try:
        proc = subprocess.run(args, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return False
    return proc.returncode == 0


def ensure_docker() -> None:
    """Exit unless a working Docker CLI and daemon are available."""
    docker = shutil.which("docker")
    if docker is None or not _command_works([docker, "--version"]):
        homebrew = Path("/opt/homebrew/bin/docker")
        if homebrew.is_file():
            os.environ["PATH"] = "/opt/homebrew/bin" + os.pathsep + os.environ.get("PATH", "")
            docker = shutil.which("docker")
    if docker is None or not _command_works([docker, "--version"]):
        _die("No working 'docker' CLI. Install one: brew install docker")
    if not _command_works([docker, "info"]):
        colima = shutil.which("colima")
        if colima is None:
            _die("Docker daemon unreachable. Start it (e.g. 'colima start') and retry.")
        _log_info("Docker daemon unreachable, starting colima...")
        if subprocess.run([colima, "start"], check=False).returncode != 0:
            _die("'colima start' failed.")
        if not _command_works([docker, "info"]):
            _die("Docker daemon still unreachable after 'colima start'.")
    version = subprocess.run([docker, "--version"], check=False, capture_output=True, text=True)
    _log_ok(f"docker: {version.stdout.strip()}")


def run_actionlint(path: Path) -> None:
    """Lint one workflow file with actionlint (fast fail before containers)."""
    actionlint = shutil.which("actionlint")
    if actionlint is None:
        _die("Required tool 'actionlint' not found. Install it: mise install")
    if subprocess.run([actionlint, str(path)], check=False).returncode != 0:
        raise SystemExit(1)
    _log_ok(f"actionlint: {path} clean")


def run_act(
    workflows_dir: Path,
    event: str,
    job: str,
    image: str,
    log_file: Path,
    extra_args: Sequence[str] = (),
    cwd: Optional[Path] = None,
) -> int:
    """Run `act` against a staged workflows dir, streaming and teeing output.

    ``cwd`` keeps act at the repository root like the old shell harness.
    ``ACT_EXTRA_ARGS`` is appended last, word-split for simple flags only.
    """
    act = shutil.which("act")
    if act is None:
        _die("Required tool 'act' not found. Install it: mise install")
    args = [act, "-W", str(workflows_dir), event]
    if job:
        args.extend(["-j", job])
    args.extend(["-P", f"ubuntu-latest={image}", "--container-daemon-socket", "-"])
    args.extend(extra_args)
    args.extend(shlex.split(os.environ.get("ACT_EXTRA_ARGS", "")))
    _log_info(f"act {' '.join(args[1:])}")
    with open(log_file, "w", encoding="utf-8") as handle:
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(cwd) if cwd is not None else None,
        )
        if process.stdout is not None:
            for line in process.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
                handle.write(line)
        return process.wait()


def _log_info(message: str) -> None:
    print(f"==> {message}")


def _log_ok(message: str) -> None:
    print(f"✓ {message}")


def _log_error(message: str) -> None:
    print(f"✗ {message}", file=sys.stderr)


def _die(message: str) -> NoReturn:
    _log_error(message)
    raise SystemExit(1)


def _print_profiles(profiles: dict[str, Profile], stream: Optional[TextIO] = None) -> None:
    target = stream or sys.stdout
    for name in sorted(profiles):
        profile = profiles[name]
        print(
            f"{name:<16} file={profile.workflow_file} event={profile.event} job={profile.job or '(all)'}",
            file=target,
        )


def _print_summary(log_path: Path, log_text: str) -> bool:
    print("--- step results ---")
    for result in summarize(log_text):
        print(result)
    if job_succeeded(log_text):
        _log_ok("local run: JOB SUCCEEDED")
        return True
    _log_error(f"local run: JOB FAILED (see {log_path})")
    return False


def _run_profile(name: str, profile: Profile, event: str, job: str, image: str, amd64: bool) -> int:
    root = repository_root()
    workflow_path = root / profile.workflow_file
    if not workflow_path.is_file():
        _log_error(f"Workflow file not found: {workflow_path}")
        return 1

    _log_info(f"testing {profile.workflow_file} (event={event} job={job or '(all)'})")
    run_actionlint(workflow_path)
    ensure_docker()

    stage_dir = Path(tempfile.mkdtemp(prefix="act-workflows-"))
    # NOTE: macOS mktemp requires the X's to be trailing (no suffix).
    log_fd, log_name = tempfile.mkstemp(prefix="act-run-")
    os.close(log_fd)
    log_path = Path(log_name)
    try:
        stage_workflows(root, stage_dir)
        staged_file = stage_dir / workflow_path.name
        if profile.needs_git_shim:
            if not profile.shim_snippet:
                _log_error(f"{name} needs a git shim but sets no shim_snippet")
                return 1
            snippet_path = PROFILES_DIR / profile.shim_snippet
            if not snippet_path.is_file():
                _log_error(f"Shim snippet not found: {snippet_path}")
                return 1
            try:
                patched = inject_step(
                    staged_file.read_text(encoding="utf-8"),
                    job,
                    snippet_path.read_text(encoding="utf-8"),
                )
            except ValueError as error:
                _log_error(str(error))
                return 1
            staged_file.write_text(patched, encoding="utf-8")
            _log_info("injected act-local git shim into staged copy (repo untouched)")

        extra_args = list(profile.extra_args)
        if amd64:
            extra_args.extend(["--container-architecture", "linux/amd64"])
        _log_info(f"full log: {log_path}")
        act_rc = run_act(stage_dir, event, job, image, log_path, extra_args, cwd=root)

        # The staged copy is disposable; the real workflow file was never modified.
        if profile.needs_git_shim and "ACT-LOCAL" in workflow_path.read_text(encoding="utf-8"):
            _die(f"Safety check failed: {profile.workflow_file} contains ACT-LOCAL markers!")
        _log_ok("repo workflow file untouched by local shims")
        summary_ok = _print_summary(log_path, log_path.read_text(encoding="utf-8"))
        if act_rc != 0:
            return act_rc
        return 0 if summary_ok else 1
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="test-workflow.sh",
        description="Lint a GitHub Actions workflow, then run its job locally with act.",
        epilog=(
            "Examples:\n"
            "  test-workflow.sh prek\n"
            "  test-workflow.sh prek --event schedule\n"
            "  test-workflow.sh test --job test --event pull_request\n\n"
            "Full docs: scripts/README.md"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("name", nargs="?", help="profile name under scripts/maintainer/workflows/")
    parser.add_argument("--event", help="override the profile trigger event")
    parser.add_argument("--job", help="override the profile job (empty runs the whole event)")
    parser.add_argument("--image", help="override the ubuntu-latest container image")
    parser.add_argument("--amd64", action="store_true", help="force linux/amd64 emulation")
    parser.add_argument("--list", action="store_true", dest="list_profiles", help="list profiles and exit")
    return parser


def main(argv: Sequence[str]) -> int:
    """CLI entry point: parse flags, load profiles, and run one profile."""
    parser = _build_parser()
    options = parser.parse_args(list(argv))
    try:
        profiles = load_profiles(PROFILES_DIR)
    except ValueError as error:
        _die(str(error))

    if options.list_profiles:
        _print_profiles(profiles)
        return 0
    if not options.name:
        parser.print_usage(sys.stderr)
        _log_error("Missing workflow name.")
        return 1
    if options.name not in profiles:
        _log_error(f"Unknown workflow '{options.name}'. Available:")
        _print_profiles(profiles, stream=sys.stderr)
        return 1

    profile = profiles[options.name]
    # Empty overrides fall back to the profile, matching the old ${VAR:-profile}.
    event = options.event or profile.event
    job = profile.job if options.job is None else options.job
    image = options.image or profile.image or DEFAULT_IMAGE
    return _run_profile(options.name, profile, event, job, image, options.amd64)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
