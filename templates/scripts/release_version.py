"""Version math shared by `release.sh` and `check-version-tag.sh`.

Single source of version knowledge: parsing, bumping, suggestion, drift
classification and tag selection. Stdlib-only so generated projects can run
it with their own interpreter.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from collections.abc import Iterable, Sequence
from pathlib import Path

SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
BUMP_KINDS = ("patch", "minor", "major")


def _format(version: tuple[int, int, int]) -> str:
    """Render a parsed version back to plain `X.Y.Z`."""
    return ".".join(str(part) for part in version)


def parse_version(text: str) -> tuple[int, int, int]:
    """Parse a plain `X.Y.Z` version; reject prefixes, suffixes and extra parts."""
    match = SEMVER.fullmatch(text)
    if match is None:
        raise ValueError(f"invalid version {text!r}: expected plain X.Y.Z")
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


def bump(version: str, kind: str) -> str:
    """Return `version` bumped by `kind` (`patch`, `minor` or `major`)."""
    major, minor, patch = parse_version(version)
    if kind == "patch":
        return _format((major, minor, patch + 1))
    if kind == "minor":
        return _format((major, minor + 1, 0))
    if kind == "major":
        return _format((major + 1, 0, 0))
    raise ValueError(f"invalid bump {kind!r}: expected one of {', '.join(BUMP_KINDS)}")


def suggest(bump_kind: str, current: str, local: str = "", remote: str = "") -> str:
    """Next version: a `bump_kind` bump above the highest known version.

    A repository with no tags yet keeps the current version for its first
    release, regardless of the requested bump.
    """
    if not local and not remote:
        return _format(parse_version(current))
    known = [parse_version(version) for version in (current, local, remote) if version]
    return bump(_format(max(known)), bump_kind)


def is_above_floor(version: str, current: str, local: str = "", remote: str = "") -> bool:
    """Whether `version` may be released given the pyproject and tag floors.

    Tags make the floor strict. A first release (no tags) may equal the
    pyproject version, but never go below it.
    """
    known = [parse_version(known_version) for known_version in (current, local, remote) if known_version]
    if not known:
        return True
    candidate = parse_version(version)
    floor = max(known)
    return candidate > floor if local or remote else candidate >= floor


def latest_tag(lines: Iterable[str]) -> str:
    """Highest plain `X.Y.Z` tag in local tag output; empty when none."""
    best: tuple[int, int, int] | None = None
    for line in lines:
        try:
            candidate = parse_version(line.strip())
        except ValueError:
            continue
        if best is None or candidate > best:
            best = candidate
    return _format(best) if best is not None else ""


def latest_remote_tag(lines: Iterable[str]) -> str:
    """Highest plain `X.Y.Z` tag in `git ls-remote --tags` output; empty when none."""
    best: tuple[int, int, int] | None = None
    for line in lines:
        _, separator, ref = line.strip().partition("refs/tags/")
        if not separator:
            continue
        try:
            candidate = parse_version(ref)
        except ValueError:
            continue
        if best is None or candidate > best:
            best = candidate
    return _format(best) if best is not None else ""


def classify_drift(current: str, latest: str) -> str:
    """Name the relation between the pyproject version and the latest tag."""
    if not latest:
        return "no-tags"
    current_parts = parse_version(current)
    latest_parts = parse_version(latest)
    if current_parts == latest_parts:
        return "ok"
    return "ahead" if current_parts > latest_parts else "behind"


def read_project_version(path: str | Path = "pyproject.toml") -> str:
    """Read and validate `[project] version` from a `pyproject.toml`."""
    with Path(path).open("rb") as handle:
        data = tomllib.load(handle)
    version = data["project"]["version"]
    if not isinstance(version, str):
        raise ValueError(f"invalid [project] version {version!r}: expected plain X.Y.Z")
    parse_version(version)
    return version


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser used by the release scripts."""
    parser = argparse.ArgumentParser(
        prog="release_version.py",
        description="Version math shared by release.sh and check-version-tag.sh.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    project_version = subparsers.add_parser("project-version", help="print [project] version")
    project_version.add_argument("path", nargs="?", default="pyproject.toml", help="pyproject path")

    subparsers.add_parser("latest-tag", help="highest plain X.Y.Z line on stdin")
    subparsers.add_parser("latest-remote-tag", help="highest plain X.Y.Z refs/tags entry on stdin")

    suggest_parser = subparsers.add_parser("suggest", help="suggest the next release version")
    suggest_parser.add_argument("--bump", required=True, choices=BUMP_KINDS)
    suggest_parser.add_argument("--current", required=True)
    suggest_parser.add_argument("--local", default="")
    suggest_parser.add_argument("--remote", default="")

    floor_parser = subparsers.add_parser("check-floor", help="exit 0 when the version is above every floor")
    floor_parser.add_argument("--version", required=True)
    floor_parser.add_argument("--current", required=True)
    floor_parser.add_argument("--local", default="")
    floor_parser.add_argument("--remote", default="")

    classify_parser = subparsers.add_parser("classify", help="print the version drift state")
    classify_parser.add_argument("--current", required=True)
    classify_parser.add_argument("--latest", default="")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return the process exit code."""
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "project-version":
            print(read_project_version(args.path))
        elif args.command == "latest-tag":
            print(latest_tag(sys.stdin.read().splitlines()))
        elif args.command == "latest-remote-tag":
            print(latest_remote_tag(sys.stdin.read().splitlines()))
        elif args.command == "suggest":
            print(suggest(args.bump, args.current, args.local, args.remote))
        elif args.command == "check-floor":
            return 0 if is_above_floor(args.version, args.current, args.local, args.remote) else 1
        else:
            print(classify_drift(args.current, args.latest))
    except (KeyError, ValueError, OSError) as error:
        print(f"release_version: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
