"""Refresh the `python_version` choices in `copier.yaml` from endoflife.date.

Only the block between the begin/end marker comments is rewritten; everything
else in the file is preserved byte-for-byte. Run it via:

    mise run update:python-versions

Stdlib-only, repo-maintenance tooling: it never ships to generated projects.
"""

import json
import re
import ssl
import sys
import urllib.request
from pathlib import Path
from typing import Any

MIN_PYTHON = (3, 12)
API_URL = "https://endoflife.date/api/python.json"
BEGIN_MARKER = "# python-version-choices: begin (managed by scripts/maintainer/update_python_versions.py, do not edit)"
END_MARKER = "# python-version-choices: end"
DEFAULT_TARGET = "copier.yaml"
TIMEOUT_SECONDS = 30
INDENT = " " * 8  # indentation of `choices:` entries and their markers in copier.yaml

CYCLE_PATTERN = re.compile(r"^3\.(\d+)$")
DEFAULT_LINE_PATTERN = re.compile(r"^\s*default:")
DEFAULT_VALUE_PATTERN = re.compile(r"^\s*default:\s*[\"'](?P<version>\d+\.\d+)[\"']\s*$")


def parse_releases(records: list[dict[str, Any]]) -> list[str]:
    """Return released CPython 3.x cycles >= `MIN_PYTHON`, newest first.

    Cycles without a `latest` release (not yet published) are skipped, duplicates
    collapse, and input order does not matter.
    """
    minors: set[int] = set()
    for record in records:
        cycle = record.get("cycle")
        if not isinstance(cycle, str) or not record.get("latest"):
            continue
        match = CYCLE_PATTERN.match(cycle)
        if match is None:
            continue
        minor = int(match.group(1))
        if (3, minor) < MIN_PYTHON:
            continue
        minors.add(minor)
    return [f"3.{minor}" for minor in sorted(minors, reverse=True)]


def _marker_index(lines: list[str], marker: str) -> int:
    """Index of the one line holding `marker`; ValueError when it is missing or duplicated."""
    found = [index for index, line in enumerate(lines) if line.strip() == marker]
    if len(found) != 1:
        raise ValueError(f"expected exactly one {marker!r} marker, found {len(found)}")
    return found[0]


def update_copier_yaml(content: str, versions: list[str]) -> str:
    """Swap the managed choice block in `content` for `versions`.

    Raises ValueError when either marker is missing or duplicated, when the end
    marker precedes the begin marker, or when `versions` is empty (an empty
    `choices:` mapping is not valid for Copier).
    """
    if not versions:
        raise ValueError("refusing to write an empty python_version choice list")

    lines = content.splitlines(keepends=True)
    begin, end = _marker_index(lines, BEGIN_MARKER), _marker_index(lines, END_MARKER)
    if begin > end:
        raise ValueError("the begin marker must precede the end marker")

    block = [
        f"{INDENT}{BEGIN_MARKER}\n",
        *(f'{INDENT}"{version}": "{version}"\n' for version in versions),
        f"{INDENT}{END_MARKER}\n",
    ]
    return "".join([*lines[:begin], *block, *lines[end + 1 :]])


def current_default_version(content: str) -> str:
    """Return the `python_version` default: the first `default:` line after the end marker.

    Raises ValueError when the end marker is missing or duplicated, when no `default:`
    line follows it, or when that line is not a quoted `X.Y` version.
    """
    lines = content.splitlines()
    for line in lines[_marker_index(lines, END_MARKER) + 1 :]:
        if DEFAULT_LINE_PATTERN.match(line):
            match = DEFAULT_VALUE_PATTERN.match(line)
            if match is None:
                raise ValueError(f"python_version default must be a quoted X.Y version, got {line.strip()!r}")
            return match.group("version")
    raise ValueError("no `default:` line follows the python-version-choices end marker")


def _ssl_context() -> ssl.SSLContext:
    """Default TLS context minus OpenSSL strict X.509 checks.

    Python 3.13+ enables VERIFY_X509_STRICT by default, which rejects the corporate
    Zscaler root (non-critical Basic Constraints, no Key Usage). Clearing it only
    affects this script's requests.
    """
    context = ssl.create_default_context()
    context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return context


def _fetch_releases() -> list[dict[str, Any]]:
    with urllib.request.urlopen(API_URL, timeout=TIMEOUT_SECONDS, context=_ssl_context()) as response:
        records = json.loads(response.read().decode("utf-8"))
    if not isinstance(records, list):
        raise ValueError(f"expected a JSON list from {API_URL}, got {type(records).__name__}")
    return records


def main() -> int:
    """Rewrite the managed choice block of the target file (default `copier.yaml`)."""
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(DEFAULT_TARGET)

    try:
        versions = parse_releases(_fetch_releases())
    except (OSError, ValueError) as exc:
        print(f"error: could not fetch Python release data from {API_URL}: {exc}", file=sys.stderr)
        return 1
    if not versions:
        print(
            f"error: no released Python >= 3.{MIN_PYTHON[1]} cycles found; leaving {target} untouched", file=sys.stderr
        )
        return 1

    try:
        content = target.read_text(encoding="utf-8")
        default = current_default_version(content)
        updated = update_copier_yaml(content, versions)
    except (OSError, ValueError) as exc:
        print(f"error: cannot update {target}: {exc}", file=sys.stderr)
        return 1
    if default not in versions:
        print(
            f"error: refusing to update {target}: python_version default {default} is not among the fetched "
            f"choices ({', '.join(versions)}); leaving the file untouched",
            file=sys.stderr,
        )
        return 1

    if updated == content:
        print(f"{target}: python_version choices already up to date ({', '.join(versions)})")
        return 0

    target.write_text(updated, encoding="utf-8")
    print(f"{target}: python_version choices set to {', '.join(versions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
