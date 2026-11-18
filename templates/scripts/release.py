#!/usr/bin/env python3
"""Cut a release: bump [project] version, re-lock, regenerate CHANGELOG.md, amend HEAD, and tag.

Never pushes. Prints the newest local and origin tags before choosing a version.
Interactive via gum on a TTY, flag-driven otherwise (CI-safe).
No reachable tags -> first release keeps the pyproject version (no forced bump).
Offline-safe: origin is best-effort, so a missing remote or remote tag never blocks.

    scripts/release.py [--version X.Y.Z] [--yes]
    scripts/release.py --help

Environment overrides (flags win over env):
    RELEASE_VERSION, RELEASE_YES=1
"""

# Payload scripts run known tools (git/uv/git-cliff/gum) with literal argv and never a shell;
# S603/S607 would only flag those fixed command names, not untrusted input.
# ruff: noqa: S603, S607

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import NoReturn, TextIO

VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
REMOTE_TAG_PATTERN = re.compile(r"refs/tags/([0-9]+\.[0-9]+\.[0-9]+)$")

_TTY = sys.stdout.isatty()
_C_INFO = "\033[1;34m" if _TTY else ""
_C_OK = "\033[1;32m" if _TTY else ""
_C_WARN = "\033[1;33m" if _TTY else ""
_C_ERR = "\033[1;31m" if _TTY else ""
_C_OFF = "\033[0m" if _TTY else ""

USAGE = """Usage:
  scripts/release.py [--version X.Y.Z] [--yes]
  scripts/release.py --help

Cut a release in the current repository:
  1. determines the next version (the explicit --version, or the suggested
     patch bump; conventional commits only shape the changelog)
  2. bumps [project] version in pyproject.toml and re-locks uv.lock
  3. regenerates CHANGELOG.md, amends HEAD, and tags (never pushes)

Options:
  --version X.Y.Z   release this exact version (default: prompt on a TTY,
                    or the suggested patch version with --yes)
  --yes             non-interactive: accept the suggested version, skip
                    confirmations, and allow releasing from a non-main/master
                    branch (required when not on a TTY)
  --help            print this help and exit

Environment:
  RELEASE_VERSION   same as --version
  RELEASE_YES=1     same as --yes

Examples:
  mise run release
  mise run release -- --version 0.4.0 --yes
  RELEASE_YES=1 mise run release
"""


def parse_version(value: str) -> tuple[int, int, int] | None:
    """Parse a plain X.Y.Z version, returning None for anything else (no `v` prefix)."""
    if not VERSION_PATTERN.fullmatch(value):
        return None
    major, minor, patch = value.split(".")
    return int(major), int(minor), int(patch)


def latest_version(tags: Iterable[str]) -> str:
    """Highest plain X.Y.Z value in `tags`, ignoring non-semver tags and peeled entries."""
    best = ""
    best_key: tuple[int, int, int] | None = None
    for tag in tags:
        key = parse_version(tag)
        if key is not None and (best_key is None or key > best_key):
            best, best_key = tag, key
    return best


def suggest_version(current: str, last_tag: str = "", remote_tag: str = "") -> str:
    """Next patch above every known version; a repo with no tags keeps the pyproject version."""
    if not last_tag and not remote_tag:
        return current
    keys = [key for value in (current, last_tag, remote_tag) if (key := parse_version(value)) is not None]
    major, minor, patch = max(keys)
    return f"{major}.{minor}.{patch + 1}"


def version_floor_ok(release: str, current: str, last_tag: str = "", remote_tag: str = "") -> bool:
    """A release must be above the highest known version, except a first release may equal it."""
    key = parse_version(release)
    if key is None:
        return False
    known = [parsed for value in (current, last_tag, remote_tag) if (parsed := parse_version(value)) is not None]
    if not known:
        return False
    floor = max(known)
    return key > floor if (last_tag or remote_tag) else key >= floor


def _log_info(message: str) -> None:
    print(f"{_C_INFO}==> {message}{_C_OFF}")


def _log_ok(message: str) -> None:
    print(f"{_C_OK}✓ {message}{_C_OFF}")


def _log_warn(message: str) -> None:
    print(f"{_C_WARN}! {message}{_C_OFF}", file=sys.stderr)


def _die(message: str) -> NoReturn:
    print(f"{_C_ERR}✗ {message}{_C_OFF}", file=sys.stderr)
    raise SystemExit(1)


def _usage(stream: TextIO = sys.stdout) -> None:
    print(USAGE, file=stream)


def _need_cmd(command: str, hint: str = "") -> None:
    if shutil.which(command) is None:
        _die(f"Required tool '{command}' not found. {hint}".rstrip())


def _is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty() and shutil.which("gum") is not None


def _git(*args: str, capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], check=False, text=True, capture_output=capture)


def _parse_args(argv: Sequence[str]) -> tuple[str, bool]:
    version = ""
    assume_yes = False
    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument == "--version":
            if index + 1 >= len(argv):
                _usage(sys.stderr)
                raise SystemExit(2)
            version = argv[index + 1]
            index += 2
        elif argument.startswith("--version="):
            version = argument.split("=", 1)[1]
            index += 1
        elif argument == "--yes":
            assume_yes = True
            index += 1
        elif argument in ("--help", "-h"):
            _usage()
            raise SystemExit(0)
        elif argument == "--":
            break
        elif argument.startswith("-"):
            print(f"Unknown option: {argument}", file=sys.stderr)
            _usage(sys.stderr)
            raise SystemExit(2)
        else:
            print(f"Unexpected argument: {argument}", file=sys.stderr)
            _usage(sys.stderr)
            raise SystemExit(2)
    return version, assume_yes


def _read_pyproject_version() -> str:
    try:
        with Path("pyproject.toml").open("rb") as handle:
            data = tomllib.load(handle)
        return str(data["project"]["version"])
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as error:
        _die(f"Could not read [project] version from pyproject.toml ({error}).")


def _bump_pyproject(version: str) -> None:
    pyproject = Path("pyproject.toml")
    text = pyproject.read_text(encoding="utf-8")
    new_text, count = re.subn(r'^version\s*=\s*"[^"]*"', f'version = "{version}"', text, count=1, flags=re.M)
    if count != 1:
        raise SystemExit("expected exactly one top-level version key in pyproject.toml")
    pyproject.write_text(new_text, encoding="utf-8")


def _latest_remote_tag(output: str) -> str:
    tags = [match.group(1) for line in output.splitlines() if (match := REMOTE_TAG_PATTERN.search(line))]
    return latest_version(tags)


def _remote_has_tag(version: str, output: str) -> bool:
    pattern = re.compile(r"refs/tags/" + re.escape(version) + r"(\^\{\})?$", re.MULTILINE)
    return pattern.search(output) is not None


def _gum_input(suggested: str) -> str | None:
    result = subprocess.run(
        ["gum", "input", "--header", "Release version", "--prompt", "Version: ", "--value", suggested],
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _gum_confirm(message: str, *, default: bool) -> bool:
    flag = "--default" if default else "--default=false"
    return subprocess.run(["gum", "confirm", message, flag], check=False).returncode == 0


def _check_branch(assume_yes: bool) -> bool:
    branch = _git("branch", "--show-current").stdout.strip()
    if not branch or branch in ("main", "master"):
        return True
    if assume_yes:
        _log_warn(f"On branch '{branch}' (expected main/master); continuing because --yes was given.")
        return True
    if not _is_interactive():
        _die(f"On branch '{branch}' (expected main/master). Switch branches, or re-run with --yes.")
    _log_warn(f"On branch '{branch}' (expected main/master).")
    if _gum_confirm(f"Release from '{branch}' instead of main/master?", default=False):
        return True
    print("Aborted, nothing changed.")
    return False


def _preflight(assume_yes: bool) -> bool:
    top_level = _git("rev-parse", "--show-toplevel")
    if top_level.returncode:
        _die("Not inside a git repository.")
    os.chdir(top_level.stdout.strip())
    if _git("diff", "--quiet").returncode or _git("diff", "--cached", "--quiet").returncode:
        _die("Working tree is dirty. Commit or stash first, then re-run.")
    last_subject = _git("log", "-1", "--format=%s").stdout
    if last_subject.startswith("chore(release)"):
        _die(f"Last commit is already a release commit ('{last_subject}'). Aborting.")
    return _check_branch(assume_yes)


def _resolve_tags() -> tuple[str, str, str]:
    current_version = _read_pyproject_version()

    last_tag = ""
    described = _git("describe", "--tags", "--abbrev=0")
    if described.returncode == 0:
        last_tag = described.stdout.strip()
        if parse_version(last_tag) is None:
            _log_warn(f"Latest tag '{last_tag}' is not X.Y.Z; comparing against pyproject version only.")
            last_tag = ""
    if last_tag and _git("diff", "--quiet", f"{last_tag}..HEAD", "--").returncode == 0:
        _die(f"Nothing to release: no commits since tag {last_tag}.")

    remote_tag = ""
    remote_refs = _git("ls-remote", "--tags", "origin")
    if remote_refs.returncode == 0:
        remote_tag = _latest_remote_tag(remote_refs.stdout)

    if remote_tag and last_tag:
        _log_info(f"Latest tags: local {last_tag}, remote {remote_tag}.")
    elif remote_tag:
        _log_info(f"Latest tags: local none, remote {remote_tag}.")
    elif last_tag:
        _log_info(f"Latest local tag: {last_tag} (origin unreachable or no remote tags).")
    return current_version, last_tag, remote_tag


def _choose_version(version: str, assume_yes: bool, current: str, last: str, remote: str) -> str | None:
    explicit = bool(version)
    if _is_interactive() and not explicit:
        entered = _gum_input(suggest_version(current, last, remote))
        if entered is None:
            return None
        if not entered:
            _die("No version entered, aborting.")
        return entered
    if version:
        return version
    if assume_yes:
        return suggest_version(current, last, remote)
    _usage(sys.stderr)
    _die("Not interactive (no TTY or gum missing): pass --version X.Y.Z with --yes.")


def _validate_version(version: str, current: str, last: str, remote: str) -> None:
    if parse_version(version) is None:
        _die(f"Invalid version '{version}': expected X.Y.Z (plain tags, no 'v' prefix).")
    if parse_version(current) is None:
        _die(f"Invalid pyproject.toml [project] version '{current}': fix it to X.Y.Z before releasing.")
    if _git("rev-parse", "--verify", "--quiet", f"refs/tags/{version}").returncode == 0:
        _die(f"Tag '{version}' already exists.")
    origin_tags = _git("ls-remote", "--tags", "origin")
    if origin_tags.returncode == 0 and _remote_has_tag(version, origin_tags.stdout):
        _die(f"Tag '{version}' already exists on origin. Never move a published tag; pick a new version.")
    if version_floor_ok(version, current, last, remote):
        return
    hint = f"pyproject ({current})"
    if last:
        hint += f" and tag {last}"
    if remote:
        hint += f" and remote tag {remote}"
    _die(f"Version {version} must be above {hint}.")


def _lock_and_changelog(version: str) -> None:
    spin = ["gum", "spin", "--title", "Updating uv.lock...", "--", "uv", "lock"]
    if _is_interactive():
        if subprocess.run(spin, check=False).returncode:
            _die("'uv lock' failed. Restore with: git checkout -- pyproject.toml")
    elif subprocess.run(["uv", "lock"], check=False).returncode:
        _die("'uv lock' failed. Restore with: git checkout -- pyproject.toml")
    if subprocess.run(["git-cliff", "--tag", version, "-o", "CHANGELOG.md"], check=False).returncode:
        _die("'git-cliff' failed. Restore with: git checkout -- pyproject.toml uv.lock")


def _review_or_abort(version: str, assume_yes: bool) -> bool:
    if _git("add", "--", "pyproject.toml", "uv.lock", "CHANGELOG.md").returncode:
        _die("'git add' failed. Restore with: git checkout -- pyproject.toml uv.lock CHANGELOG.md")
    _git("diff", "--cached", "--stat", capture=False)
    _log_info("CHANGELOG.md preview:")
    for line in Path("CHANGELOG.md").read_text(encoding="utf-8").splitlines()[:15]:
        print(line)
    if _is_interactive() and not assume_yes and not _gum_confirm(f"Amend HEAD and tag {version}?", default=True):
        print("Aborted, HEAD untouched.")
        return False
    return True


def _amend_and_tag(version: str) -> None:
    if _git("commit", "--amend", "--no-edit", capture=False).returncode:
        print("Amend failed (hooks may have modified files).", file=sys.stderr)
        print("Inspect with 'git status', stage fixes, then finish manually:", file=sys.stderr)
        print(f"  git commit --amend --no-edit && git tag {version}", file=sys.stderr)
        raise SystemExit(1)
    if _git("tag", version).returncode:
        _die(f"Tagging '{version}' failed.")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the release flow, returning 0 on success; aborts raise `SystemExit`."""
    version, assume_yes = _parse_args(list(sys.argv[1:] if argv is None else argv))
    version = version or os.environ.get("RELEASE_VERSION", "")
    if os.environ.get("RELEASE_YES") == "1":
        assume_yes = True

    if not _preflight(assume_yes):
        return 0
    _need_cmd("git-cliff", "Install it: mise install")
    _need_cmd("uv", "Install it: mise install")

    current_version, last_tag, remote_tag = _resolve_tags()
    chosen = _choose_version(version, assume_yes, current_version, last_tag, remote_tag)
    if chosen is None:
        return 0
    _validate_version(chosen, current_version, last_tag, remote_tag)

    _log_info(f"Releasing {chosen} (pyproject was {current_version}).")
    _bump_pyproject(chosen)
    _lock_and_changelog(chosen)
    if not _review_or_abort(chosen, assume_yes):
        return 0

    _amend_and_tag(chosen)
    _log_ok(f"Released {chosen}.")
    print("Review, then push: git push --follow-tags")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
