"""Git lifecycle and verification steps run by Copier `_tasks` after a copy or update.

Stdlib-only (Copier runs it with its own interpreter) and never shipped.
Usage: lifecycle.py {copy|update} --src <template> --answers <answers-file>
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

INIT_MESSAGE = "Init commit"
SCAFFOLD_MESSAGE = "chore: scaffold from template"
UPDATE_MESSAGE = "chore: update from template"
GENERATED_FILES = ("uv.lock",)


def _git(dst: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    """Run git in `dst`. Probes are captured; `check=True` raises on failure and streams git's output."""
    return subprocess.run(["git", *args], cwd=dst, check=check, capture_output=not check, text=True)  # noqa: S603, S607


def render_paths(src: Path, answers: Path) -> set[str]:
    """Render `src` with `answers` into a temp dir (skipping tasks) and return the relative paths Copier produced."""
    argv = [
        sys.executable,
        "-m",
        "copier",
        "copy",
        "--trust",
        "--defaults",
        "--skip-tasks",
        "--data-file",
        str(answers),
        str(src),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run([*argv, tmp], capture_output=True, text=True, check=False)  # noqa: S603
        if result.returncode:
            sys.stderr.write(result.stderr)
            result.check_returncode()
        return {path.relative_to(tmp).as_posix() for path in Path(tmp).rglob("*") if path.is_file()}


def _commit_rendered(dst: Path, message: str, render: Callable[[], set[str]]) -> None:
    """Commit only this run's paths: rendered files, generated lock files, and tracked files the template dropped.

    Other staged work stays staged; `git commit -- <paths>` commits just the listed paths.
    """
    rendered = render()
    existing = {path for path in rendered | set(GENERATED_FILES) if (dst / path).is_file()}
    dropped = set(_git(dst, "ls-files", "--deleted").stdout.splitlines()) - rendered
    paths = sorted(existing | dropped)
    if not paths:
        return
    _git(dst, "add", "--force", "--", *paths, check=True)
    staged = _git(dst, "diff", "--cached", "--name-status", "--", *paths)
    if not staged.stdout.strip():
        return
    print(staged.stdout, end="")
    _git(dst, "commit", "--no-verify", "-m", message, "--", *paths, check=True)


def run(operation: str, dst: Path, *, mise: Callable[[list[str]], None], render: Callable[[], set[str]]) -> None:
    """Commit the rendered files in `dst`, then install and verify through `mise` when inside a work tree."""
    if _git(dst, "rev-parse", "--is-inside-work-tree").stdout.strip() == "true":
        _commit_rendered(dst, SCAFFOLD_MESSAGE if operation == "copy" else UPDATE_MESSAGE, render)
    elif operation == "copy":
        _git(dst, "init", check=True)
        _commit_rendered(dst, INIT_MESSAGE, render)
    else:
        return

    mise(["run", "install"])
    mise(["run", "ci"])


def _run_mise(args: list[str]) -> None:
    subprocess.run(["mise", *args], check=True)  # noqa: S603, S607


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; operates on the current directory."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("operation", choices=["copy", "update"])
    parser.add_argument("--src", required=True, type=Path)
    parser.add_argument("--answers", required=True, type=Path)
    args = parser.parse_args(argv)
    run(args.operation, Path.cwd(), mise=_run_mise, render=lambda: render_paths(args.src, args.answers))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
