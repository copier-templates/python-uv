"""Shared X.Y.Z version helpers for the release and version-tag payload scripts.

Pure stdlib-only helpers with no side effects: parsing, numeric max, patch
suggestion, and release-floor validation. Both `release.py` and
`check_version_tag.py` import from here so the rules stay in one place.
Edge cases: non-semver tags (`v`-prefix, `latest`, peeled `^{}`) are ignored;
a repo with no tags keeps the pyproject version; an unparseable version never
passes the floor.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


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
