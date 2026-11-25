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
SCAFFOLD_MESSAGE = "chore: scaffold from copier template"
UPDATE_MESSAGE = "chore: update from copier template"


def _git_probe(dst: Path, *args: str) -> str:
    """Run a read-only git query in `dst` and return its stdout, empty when git rejects the query."""
    # No `check` flag by design: a probe reports through its return value, never an exception.
    return subprocess.run(["git", *args], cwd=dst, capture_output=True, text=True).stdout  # noqa: PLW1510, S603, S607


def _git_run(dst: Path, *args: str) -> None:
    """Run a git command that must succeed: git's output streams through and a failure raises."""
    # No `check` flag by design: git streams its own output, then the non-zero status raises.
    subprocess.run(["git", *args], cwd=dst).check_returncode()  # noqa: PLW1510, S603, S607


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


def generated_files() -> frozenset[str]:
    """Paths the template writes outside Copier's render set, committed alongside it."""
    return frozenset({"uv.lock", ".python-version"})


def _commit_rendered(dst: Path, message: str, render: Callable[[], set[str]]) -> None:
    """Commit only this run's paths: rendered files, generated lock files, and tracked files the template dropped.

    Other staged work stays staged; `git commit -- <paths>` commits just the listed paths.
    """
    rendered = render()
    existing = {path for path in rendered | generated_files() if (dst / path).is_file()}
    dropped = set(filter(None, _git_probe(dst, "ls-files", "-z", "--deleted").split("\0"))) - rendered
    paths = sorted(existing | dropped)
    if not paths:
        return
    _git_run(dst, "add", "--force", "--", *paths)
    staged = _git_probe(dst, "diff", "--cached", "--name-status", "--", *paths)
    if not staged.strip():
        return
    print(staged, end="")
    _git_run(dst, "commit", "--no-verify", "-m", message, "--", *paths)


def run(operation: str, dst: Path, *, verify: Callable[[], None], render: Callable[[], set[str]]) -> None:
    """Commit the rendered files in `dst`, then run `verify` once when inside a work tree.

    A copy outside a work tree initializes git with an empty `INIT_MESSAGE` root and commits the render on top.
    """
    if _git_probe(dst, "rev-parse", "--is-inside-work-tree").strip() == "true":
        _commit_rendered(dst, SCAFFOLD_MESSAGE if operation == "copy" else UPDATE_MESSAGE, render)
    elif operation == "copy":
        _git_run(dst, "init")
        _git_run(dst, "commit", "--no-verify", "--allow-empty", "-m", INIT_MESSAGE)
        _commit_rendered(dst, SCAFFOLD_MESSAGE, render)
    else:
        return

    verify()


def _verify() -> None:
    """Run the rendered project's shared setup gate, then its full CI gate, in that order."""
    for task in ("setup", "ci"):
        # Fixed literals via the project's `mise`: no shell, no user input, so S603 and S607 do not apply.
        subprocess.run(["mise", "run", task], check=True)  # noqa: S603, S607


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; operates on the current directory."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("operation", choices=["copy", "update"])
    parser.add_argument("--src", required=True, type=Path)
    parser.add_argument("--answers", required=True, type=Path)
    args = parser.parse_args(argv)
    run(args.operation, Path.cwd(), verify=_verify, render=lambda: render_paths(args.src, args.answers))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
