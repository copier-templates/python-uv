#!/usr/bin/env python3
"""Check that pyproject.toml [project] version equals the max-semver plain X.Y.Z tag reachable from HEAD.

Blocks both drift directions:
    version > tag  -> bumped without tagging (run release / tag / push --follow-tags)
    tag > version  -> tag moved ahead (never delete the tag; bump pyproject)
No tags reachable -> pass (fresh repo). Offline-safe: remote checks warn only.

    scripts/check_version_tag.py [--help]
"""

# Payload scripts run known tools (git) with literal argv and never a shell; S603/S607 would
# only flag those fixed command names, not untrusted input.
# ruff: noqa: S603, S607

from __future__ import annotations

import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import NoReturn, TextIO

VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")

USAGE = """Usage:
  scripts/check_version_tag.py [--help]

Check pyproject.toml [project] version against git tags.

Exits 0 when the version equals the max-semver X.Y.Z tag reachable from HEAD
(or when no X.Y.Z tags exist yet). Exits 1 on mismatch with a recovery hint,
or when the version is unparseable.
"""


def parse_version(value: str) -> tuple[int, int, int] | None:
    """Parse a plain X.Y.Z version, returning None for anything else (no `v` prefix)."""
    if not VERSION_PATTERN.fullmatch(value):
        return None
    major, minor, patch = value.split(".")
    return int(major), int(minor), int(patch)


def latest_version(tags: list[str]) -> str:
    """Highest plain X.Y.Z value in `tags`, ignoring non-semver tags."""
    best = ""
    best_key: tuple[int, int, int] | None = None
    for tag in tags:
        key = parse_version(tag)
        if key is not None and (best_key is None or key > best_key):
            best, best_key = tag, key
    return best


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], check=False, text=True, capture_output=True)


def _usage(stream: TextIO = sys.stdout) -> None:
    print(USAGE, file=stream)


def _fail(message: str) -> NoReturn:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def _read_pyproject_version() -> str:
    try:
        with Path("pyproject.toml").open("rb") as handle:
            data = tomllib.load(handle)
        return str(data["project"]["version"])
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError):
        _fail("Could not read [project] version from pyproject.toml.")


def _parse_args(argv: list[str]) -> None:
    if argv and argv[0] in ("--help", "-h"):
        _usage()
        raise SystemExit(0)
    if argv:
        print(f"Unexpected argument: {argv[0]}", file=sys.stderr)
        _usage(sys.stderr)
        raise SystemExit(2)


def main(argv: list[str] | None = None) -> int:
    """Compare the pyproject version with the newest reachable X.Y.Z tag."""
    _parse_args(list(sys.argv[1:] if argv is None else argv))

    top_level = _git("rev-parse", "--show-toplevel")
    if top_level.returncode:
        _fail("Not inside a git repository.")
    os.chdir(top_level.stdout.strip())

    current_version = _read_pyproject_version()
    if parse_version(current_version) is None:
        _fail(f"Invalid pyproject version {current_version}: expected X.Y.Z.")

    merged = _git("-c", "color.ui=false", "tag", "--merged", "HEAD")
    tags = [line for line in merged.stdout.splitlines() if VERSION_PATTERN.fullmatch(line)]
    latest = latest_version(tags)

    if not latest:
        print(f"No X.Y.Z tags reachable from HEAD; pyproject is {current_version}. OK.")
        return 0
    if current_version == latest:
        print(f"pyproject version {current_version} matches latest tag {latest}. OK.")
        remote = _git("ls-remote", "--tags", "origin")
        tag_ref = "refs/tags/" + re.escape(latest) + r"$"
        if remote.returncode == 0 and not re.search(tag_ref, remote.stdout, re.MULTILINE):
            print(f"Note: tag {latest} is not on origin yet; push with: git push --follow-tags")
        return 0

    higher = max((current_version, latest), key=lambda value: parse_version(value) or (0, 0, 0))
    if higher == current_version:
        print(f"Blocked: pyproject version {current_version} is ahead of latest tag {latest}.", file=sys.stderr)
        print("You bumped without tagging.", end=" ", file=sys.stderr)
        print(
            f"Fix with: mise run release --version {current_version} --yes, then: git push --follow-tags",
            file=sys.stderr,
        )
    else:
        print(f"Blocked: latest tag {latest} is ahead of pyproject version {current_version}.", file=sys.stderr)
        print("Never delete the tag.", end=" ", file=sys.stderr)
        print(f"Fix with: mise run release (--version above {latest}), then: git push --follow-tags", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
