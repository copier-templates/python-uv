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
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(  # noqa: S603
            [
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
                tmp,
            ],  # noqa: S607
            check=True,
            capture_output=True,
        )
        return {path.relative_to(tmp).as_posix() for path in Path(tmp).rglob("*") if path.is_file()}


def _commit_rendered(dst: Path, message: str, render: Callable[[], set[str]]) -> None:
    """Stage only the rendered paths (plus generated lock files), print what is staged, and commit when non-empty."""
    paths = {path for path in render() | set(GENERATED_FILES) if (dst / path).is_file()}
    if paths:
        _git(dst, "add", "--force", "--", *sorted(paths), check=True)
    staged = _git(dst, "diff", "--cached", "--name-status")
    if not staged.stdout.strip():
        return
    print(staged.stdout, end="")
    _git(dst, "commit", "--no-verify", "-m", message, check=True)


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
