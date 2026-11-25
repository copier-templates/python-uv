#!/usr/bin/env python3
"""Keep shared task/hook pins identical across mise includes, prek hooks and test constants.

Every `git::<url>//tasks/<category>?ref=<tag>` include in `mise.toml` is a
managed pin, grouped by source URL: nothing about the upstream (its URL, its
task categories, its tag scheme) is hard-coded, so new categories and new tag
schemes are picked up with no script changes. The matching prek pins are found
by canonical URL (`git::` prefix and `.git` suffix ignored): the `rev` of the
corresponding `[[repos]]` block and the exact pins of its `[update.repos]`
table (glob patterns such as `v*` are left alone). The template tests pin the
same tag in `tests/_projects.py`; moving all of them at once keeps a bump to
one command instead of a manual edit per file.

Template repo (has `templates/`): the source of truth is the root `mise.toml`
includes, or `--to` to move everything including the root file. Rewrites the
root `mise.toml`, `templates/mise.toml.jinja`, `templates/prek.toml` (`rev`
and `include_tags`) and `tests/_projects.py` (`SHARED_REF`).
Rendered project (no `templates/`): syncs the local `prek.toml` shared `rev`
and `include_tags` to the local `mise.toml` includes.
`--check` reports drift without writing (pre-commit guard); mixed `?ref=`
values in `mise.toml` are an error without `--to`, which normalizes them.
No network access: only local files are read and rewritten in place, so
formatting and comments are preserved.

    scripts/sync_shared_refs.py [--to REF] [--check] [--root PATH]
    scripts/sync_shared_refs.py --help

Exits 0 when clean (or after applying), 1 when `--check` finds drift,
2 on usage or layout errors.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

_GIT_INCLUDE_RE = re.compile(r"git::(\S+?)//tasks/([^\"?\s]+)\?ref=([^\"'\s]+)")
_REF_RE = re.compile(r"(\?ref=)[^\"'\s]+")
_UPDATE_REPOS_RE = re.compile(r'^\[update\.repos\."([^"]+)"\]$')
_REPO_RE = re.compile(r'^repo\s*=\s*"([^"]+)"\s*$')
_GLOB_CHARS = frozenset("*?[]!{}")
# Our own test-harness constant (a repo-layout convention, not an upstream pin):
# the value follows `--to`, whatever its scheme.
_PROJECTS_REF_RE = re.compile(r'^(SHARED_REF = ")[^"]*(")$', re.MULTILINE)

USAGE = """Usage:
  scripts/sync_shared_refs.py [--to REF] [--check] [--root PATH]
  scripts/sync_shared_refs.py --help

Move every shared task/hook pin to one tag: the root mise.toml includes,
templates/mise.toml.jinja, templates/prek.toml (rev + include_tags) and
tests/_projects.py (template repo), or the local prek.toml (rendered project).

Options:
  --to REF     move every pin to this ref (default: keep each source at the
               single ref its includes already pin)
  --check      report drift without writing; exits 1 when pins differ
  --root PATH  operate on this project root (default: derived from the
               script location)
  --help       print this help and exit
"""


@dataclass(frozen=True)
class PinFile:
    """One managed file and its rewritten content (`changed` flags drift)."""

    label: str
    path: Path
    updated: str
    changed: bool


def _find_root(start: Path) -> Path:
    """Locate the project root from the script path: template repos keep a payload."""
    scripts = start.resolve().parent
    if ((scripts.parent.parent) / "templates" / "mise.toml.jinja").is_file():
        return scripts.parent.parent
    return scripts.parent


def _canonical_source(url: str) -> str:
    """Normalize a source URL so `git::` includes and prek repos compare equal."""
    return url.removeprefix("git::").removesuffix(".git")


def _discover_groups(text: str) -> dict[str, set[str]]:
    """Map each canonical shared-task source in `mise.toml` to its pinned refs."""
    groups: dict[str, set[str]] = {}
    for line in text.splitlines():
        match = _GIT_INCLUDE_RE.search(line)
        if match:
            groups.setdefault(_canonical_source(match.group(1)), set()).add(match.group(3))
    return groups


def _rewrite_mise_include_line(line: str, targets: dict[str, str]) -> str:
    """Point a shared include line at its source's target, leaving other lines untouched."""
    match = _GIT_INCLUDE_RE.search(line)
    if match is None:
        return line
    target = targets.get(_canonical_source(match.group(1)))
    if target is None:
        return line
    return _REF_RE.sub(rf"\g<1>{target}", line)


def _rewrite_mise_includes(text: str, targets: dict[str, str]) -> str:
    """Point every shared include at its source's target, leaving other lines byte-identical."""
    rewritten = [_rewrite_mise_include_line(line, targets) for line in text.split("\n")]
    return "\n".join(rewritten)


def _rewrite_repo_rev(line: str, target: str) -> str:
    """Point a shared-repo `rev = "..."` line at `target`, whatever it currently pins."""
    return re.sub(r'^(\s*rev\s*=\s*")[^"]*(")', rf"\g<1>{target}\g<2>", line)


def _has_glob(token: str) -> bool:
    return any(char in _GLOB_CHARS for char in token)


def _rewrite_pinned_tokens(line: str, target: str) -> str:
    """Move exact pins on an `[update.repos]` table line to `target`, keeping glob patterns."""

    def _move(match: re.Match[str]) -> str:
        return match.group(0) if _has_glob(match.group(1)) else f'"{target}"'

    return re.sub(r'"([^"]*)"', _move, line)


def _update_repos_key(stripped: str) -> str | None:
    match = _UPDATE_REPOS_RE.match(stripped)
    return match.group(1) if match else None


def _repo_value(stripped: str) -> str | None:
    match = _REPO_RE.match(stripped)
    return match.group(1) if match else None


def _rewrite_prek(text: str, targets: dict[str, str]) -> str:
    """Point each managed repo's `rev` and its `[update.repos]` pins at their source's target.

    Blocks and tables are matched to mise sources by canonical URL, so
    unrelated repos pinned at the same tag are never touched. The table header
    itself is never rewritten, and glob patterns (e.g. `v*`) are preserved.
    """
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    repo_target: str | None = None
    table_target: str | None = None
    for line in lines:
        stripped = line.strip()
        rewritten = line
        if stripped.startswith("[[repos]]"):
            repo_target = None
            table_target = None
        elif (key := _update_repos_key(stripped)) is not None:
            repo_target = None
            table_target = targets.get(_canonical_source(key))
            out.append(rewritten)
            continue
        elif stripped.startswith("["):
            repo_target = None
            table_target = None
        elif (repo := _repo_value(stripped)) is not None:
            table_target = None
            repo_target = targets.get(_canonical_source(repo))
        if repo_target is not None:
            rewritten = _rewrite_repo_rev(rewritten, repo_target)
        elif table_target is not None:
            rewritten = _rewrite_pinned_tokens(rewritten, table_target)
        out.append(rewritten)
    return "".join(out)


def _rewrite_projects_constant(text: str, target: str | None) -> str:
    """Move the `SHARED_REF` constant, leaving every other line byte-identical."""
    if target is None:
        return text
    updated, count = _PROJECTS_REF_RE.subn(rf"\g<1>{target}\g<2>", text)
    if count != 1:
        raise ValueError("expected exactly one SHARED_REF assignment in tests/_projects.py")
    return updated


def _resolve_targets(groups: dict[str, set[str]], target: str | None) -> dict[str, str]:
    """One target ref per source: `--to` wins, otherwise each source keeps its uniform pin."""
    targets = {}
    for source in sorted(groups):
        refs = groups[source]
        if target is not None:
            targets[source] = target
        elif len(refs) > 1:
            raise ValueError(f"{source} pins more than one ref: {sorted(refs)}; pass --to to normalize")
        else:
            targets[source] = next(iter(refs))
    return targets


def _load_mise_toml(path: Path) -> str:
    try:
        return path.read_text()
    except OSError:
        raise ValueError(f"missing {path.name}; run from the project root or pass --root") from None


def _plan(root: Path, target: str | None) -> tuple[dict[str, str], list[PinFile]]:
    """Compute each source's target ref and the rewritten content of every managed file."""
    mise_text = _load_mise_toml(root / "mise.toml")
    groups = _discover_groups(mise_text)
    if not groups:
        raise ValueError("no versioned shared task includes in mise.toml")
    if target is not None and not target.strip():
        raise ValueError("--to needs a non-empty ref")
    targets = _resolve_targets(groups, target)

    template_mode = (root / "templates" / "mise.toml.jinja").is_file()
    prek_path = root / "templates" / "prek.toml" if template_mode else root / "prek.toml"
    # The test constant mirrors the single-source case; a second upstream needs test updates.
    projects_target = next(iter(targets.values())) if len(targets) == 1 else None

    files = [("mise.toml", root / "mise.toml")]
    if template_mode:
        files.append(("templates/mise.toml.jinja", root / "templates" / "mise.toml.jinja"))
    files.append((prek_path.relative_to(root).as_posix(), prek_path))
    if template_mode:
        files.append(("tests/_projects.py", root / "tests" / "_projects.py"))

    planned: list[PinFile] = []
    for label, path in files:
        try:
            original = path.read_text()
        except OSError:
            raise ValueError(f"missing {label}; unexpected layout under {root}") from None
        if path.name == "_projects.py":
            updated = _rewrite_projects_constant(original, projects_target)
        elif path.name == "prek.toml":
            updated = _rewrite_prek(original, targets)
        else:
            updated = _rewrite_mise_includes(original, targets)
        planned.append(PinFile(label, path, updated, updated != original))
    return targets, planned


def _check(planned: list[PinFile], targets: dict[str, str]) -> int:
    print(f"sources: {targets}")
    drifted = [pin.label for pin in planned if pin.changed]
    for pin in planned:
        state = "drifts" if pin.changed else "in sync"
        print(f"{pin.label}: {state}")
    if drifted:
        print(f"shared ref drift in: {', '.join(drifted)}", file=sys.stderr)
        return 1
    return 0


def _apply(planned: list[PinFile], targets: dict[str, str]) -> int:
    print(f"sources: {targets}")
    for pin in planned:
        if pin.changed:
            pin.path.write_text(pin.updated)
            print(f"{pin.label}: updated")
        else:
            print(f"{pin.label}: in sync")
    return 0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="scripts/sync_shared_refs.py", add_help=False)
    parser.add_argument("--to", default=None)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--root", default=None)
    parser.add_argument("--help", action="store_true")
    args = parser.parse_args(argv)
    if args.help:
        print(USAGE, end="")
        raise SystemExit(0)
    return args


def main(argv: list[str]) -> int:
    """Entry point: parse flags, plan the pin moves, check or apply them."""
    args = _parse_args(argv)
    root = Path(args.root) if args.root else _find_root(Path(__file__))
    try:
        # tomllib guards against hand-edited TOML that no longer parses.
        tomllib.loads((root / "mise.toml").read_bytes().decode())
        targets, planned = _plan(root, args.to)
    except ValueError as exc:
        print(f"sync_shared_refs: {exc}", file=sys.stderr)
        return 2
    except (OSError, tomllib.TOMLDecodeError) as exc:
        print(f"sync_shared_refs: cannot read mise.toml under {root}: {exc}", file=sys.stderr)
        return 2
    if args.check:
        return _check(planned, targets)
    return _apply(planned, targets)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
