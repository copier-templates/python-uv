"""Git lifecycle and verification steps run by Copier `_tasks` after a copy or update.

Stdlib-only (Copier runs it with its own interpreter) and never shipped.
Usage: lifecycle.py {copy|update}
"""

from __future__ import annotations

import argparse
import subprocess
from collections.abc import Callable
from pathlib import Path

INIT_MESSAGE = "Init commit"
SCAFFOLD_MESSAGE = "chore: scaffold from template"
UPDATE_MESSAGE = "chore: update from template"


def _git(dst: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    """Run git in `dst`. Probes are captured; `check=True` raises on failure and streams git's output."""
    return subprocess.run(["git", *args], cwd=dst, check=check, capture_output=not check, text=True)  # noqa: S603, S607


def _commit_all(dst: Path, message: str) -> None:
    """Stage everything and commit when something is staged; hooks are installed later, so bypass them."""
    _git(dst, "add", "-A", check=True)
    if _git(dst, "diff", "--cached", "--quiet").returncode == 0:
        return
    _git(dst, "commit", "--no-verify", "-m", message, check=True)


def run(operation: str, dst: Path, *, mise: Callable[[list[str]], None]) -> None:
    """Commit the rendered files in `dst`, then install and verify through `mise` when inside a work tree."""
    if _git(dst, "rev-parse", "--is-inside-work-tree").stdout.strip() == "true":
        _commit_all(dst, SCAFFOLD_MESSAGE if operation == "copy" else UPDATE_MESSAGE)
    elif operation == "copy":
        _git(dst, "init", check=True)
        _commit_all(dst, INIT_MESSAGE)
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
    args = parser.parse_args(argv)
    run(args.operation, Path.cwd(), mise=_run_mise)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
