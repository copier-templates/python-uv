#!/usr/bin/env python3
"""Keep shared task/hook pins aligned across mise includes, prek hooks and test constants.

Every `git::<url>//tasks/<category>?ref=<tag>` include in `mise.toml` is a
managed pin, tracked by its full task path rather than only its source URL: one
source may be rolled out per category, so `core` can stay on an older tag while
`toml` already uses a newer one. Nothing about the upstream (its URL, its task
categories, its tag scheme) is hard-coded, so new categories, sources and tag
schemes are picked up with no script changes.

The matching prek pins are found by canonical URL (`git::` prefix and `.git`
suffix ignored). A repository's `rev` is the newest ref used by its includes
(numeric-aware comparison); its `[update.repos]` table lists every distinct
managed ref, so `prek update` stays inside the pinned set. Glob patterns such as
`v*` are left alone, and duplicate exact tags collapse to one. The template
tests mirror the per-category refs in `tests/_projects.py` (`SHARED_REFS`, plus
`SHARED_REF` for the shared-hooks pin); moving all of them at once keeps a bump
to one command instead of a manual edit per file.

Template repo (has `templates/`): the source of truth is the root `mise.toml`
includes, or `--to` to move everything including the root file. Rewrites the
root `mise.toml`, `templates/mise.toml.jinja`, `templates/prek.toml` (`rev`
and `include_tags`) and `tests/_projects.py`.
Rendered project (no `templates/`): syncs the local `prek.toml` shared `rev`
and `include_tags` to the local `mise.toml` includes.
`--check` reports drift without writing (pre-commit guard). No network access:
only local files are read and rewritten in place, so formatting and comments
are preserved.

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
_UPDATE_REPOS_RE = re.compile(r'^\[update\.repos\."([^"]+)"\]$')
_REPO_RE = re.compile(r'^repo\s*=\s*"([^"]+)"\s*$')
_STRING_RE = re.compile(r'"([^"]*)"')
_REF_PART_RE = re.compile(r"(\d+)")
_GLOB_CHARS = frozenset("*?[]!{}")
# Our own test-harness constant (a repo-layout convention, not an upstream pin):
# the value follows the newest managed ref, whatever its scheme.
_PROJECTS_REF_RE = re.compile(r'^(SHARED_REF = ")[^"]*(")$', re.MULTILINE)
_PROJECTS_REFS_START = "SHARED_REFS = {"

USAGE = """Usage:
  scripts/sync_shared_refs.py [--to REF] [--check] [--root PATH]
  scripts/sync_shared_refs.py --help

Keep every shared task/hook pin aligned: the root mise.toml includes,
templates/mise.toml.jinja, templates/prek.toml (rev + include_tags) and
tests/_projects.py (template repo), or the local prek.toml (rendered project).

Options:
  --to REF     move every pin to this ref (default: keep each include at the
               ref mise.toml already pins)
  --check      report drift without writing; exits 1 when pins differ
  --root PATH  operate on this project root (default: derived from the
               script location)
  --help       print this help and exit
"""


@dataclass(frozen=True)
class Include:
    """One managed `git::` task include: canonical source, task path and pinned ref."""

    source: str
    category: str
    ref: str


@dataclass(frozen=True)
class PinFile:
    """One managed file and its rewritten content (`changed` flags drift)."""

    label: str
    path: Path
    updated: str
    changed: bool


@dataclass(frozen=True)
class Plan:
    """Resolved per-include targets, per-repo prek pins and the files to rewrite."""

    include_targets: dict[tuple[str, str], str]
    repo_tags: dict[str, tuple[str, ...]]
    repo_revs: dict[str, str]
    files: list[PinFile]


def _find_root(start: Path) -> Path:
    """Locate the project root from the script path: template repos keep a payload."""
    scripts = start.resolve().parent
    if ((scripts.parent.parent) / "templates" / "mise.toml.jinja").is_file():
        return scripts.parent.parent
    return scripts.parent


def _canonical_source(url: str) -> str:
    """Normalize a source URL so `git::` includes and prek repos compare equal."""
    return url.removeprefix("git::").removesuffix(".git")


def _ref_key(ref: str) -> tuple[tuple[int, int | str], ...]:
    """Order refs numerically inside their text parts, so `0.2.10` sorts after `0.2.9`."""
    return tuple((0, int(part)) if part.isdigit() else (1, part) for part in _REF_PART_RE.split(ref))


def _discover_includes(text: str) -> list[Include]:
    """List every managed task include in file order, preserving each include's own ref."""
    includes: list[Include] = []
    for line in text.splitlines():
        for match in _GIT_INCLUDE_RE.finditer(line):
            includes.append(Include(_canonical_source(match.group(1)), match.group(2), match.group(3)))
    return includes


def _resolve_targets(
    includes: list[Include],
    target: str | None,
) -> tuple[dict[tuple[str, str], str], dict[str, tuple[str, ...]], dict[str, str]]:
    """Resolve each include's target plus the refs and hook rev for its source.

    Without `--to`, every include keeps the ref already in mise.toml, so mixed
    per-category refs are valid. The same task path may only appear once with a
    given ref: two different refs would make the source of truth ambiguous.
    Prek gets every distinct ref for the update table and the newest one as the
    repo `rev`.
    """
    include_targets: dict[tuple[str, str], str] = {}
    order: list[str] = []
    for include in includes:
        key = (include.source, include.category)
        current = include_targets.get(key)
        if target is None and current is not None and current != include.ref:
            refs = sorted({current, include.ref}, key=_ref_key)
            path = f"{include.source}//tasks/{include.category}"
            raise ValueError(f"{path} pins more than one ref: {refs}; pass --to to normalize")
        include_targets[key] = target if target is not None else include.ref
        if include.source not in order:
            order.append(include.source)

    refs_by_source: dict[str, list[str]] = {source: [] for source in order}
    for (source, _), ref in include_targets.items():
        if ref not in refs_by_source[source]:
            refs_by_source[source].append(ref)
    repo_tags = {source: tuple(sorted(refs, key=_ref_key)) for source, refs in refs_by_source.items()}
    repo_revs = {source: tags[-1] for source, tags in repo_tags.items()}
    return include_targets, repo_tags, repo_revs


def _rewrite_mise_include_line(line: str, targets: dict[tuple[str, str], str]) -> str:
    """Point each shared include on a line at its task path's target, leaving other lines untouched."""

    def _replace(match: re.Match[str]) -> str:
        key = (_canonical_source(match.group(1)), match.group(2))
        target = targets.get(key)
        if target is None:
            return match.group(0)
        return f"git::{match.group(1)}//tasks/{match.group(2)}?ref={target}"

    return _GIT_INCLUDE_RE.sub(_replace, line)


def _rewrite_mise_includes(text: str, targets: dict[tuple[str, str], str]) -> str:
    """Rewrite every managed include line, leaving all other lines byte-identical."""
    return "\n".join(_rewrite_mise_include_line(line, targets) for line in text.split("\n"))


def _rewrite_repo_rev(line: str, target: str) -> str:
    """Point a shared-repo `rev = "..."` line at `target`, whatever it currently pins."""
    return re.sub(r'^(\s*rev\s*=\s*")[^"]*(")', rf"\g<1>{target}\g<2>", line)


def _has_glob(token: str) -> bool:
    return any(char in _GLOB_CHARS for char in token)


def _split_toml_comment(line: str) -> tuple[str, str]:
    """Split a line into (code, comment) at the first `#` outside double quotes."""
    in_string = False
    for index, char in enumerate(line):
        if char == '"':
            in_string = not in_string
        elif char == "#" and not in_string:
            return line[:index], line[index:]
    return line, ""


def _remove_token(code: str, token: str) -> str:
    """Remove one quoted token and one neighboring comma from an array's code text."""
    without_leading, leading_count = re.subn(rf",\s*{re.escape(token)}", "", code, count=1)
    if leading_count:
        return without_leading
    without_trailing, trailing_count = re.subn(rf"{re.escape(token)}\s*,", "", code, count=1)
    if trailing_count:
        return without_trailing
    return code.replace(token, "", 1)


def _rewrite_tag_tokens(line: str, refs: tuple[str, ...], emitted: bool) -> tuple[str | None, bool]:
    """Rewrite a managed `include_tags` line to one pin per distinct ref.

    The first exact pin expands to every managed ref; later exact pins are
    duplicates and disappear together with one neighboring comma. Glob patterns
    are never touched. A bare pin on its own line expands into one line per ref
    so taplo-style arrays stay readable. Comments outside strings are preserved.
    """
    code, suffix = _split_toml_comment(line)
    exact = [match for match in _STRING_RE.finditer(code) if not _has_glob(match.group(1))]
    if not exact:
        return line, emitted

    newline = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
    if not emitted:
        first = exact[0]
        stripped = code.strip()
        bare = stripped in (f'"{first.group(1)}"', f'"{first.group(1)}",')
        if bare:
            indent = code[: len(code) - len(code.lstrip())]
            comma = "," if stripped.endswith(",") else ""
            expanded = newline.join(f'{indent}"{ref}"{comma}' for ref in refs)
            return expanded + suffix + newline, True
        replacement = ", ".join(f'"{ref}"' for ref in refs)
        code = code[: first.start()] + replacement + code[first.end() :]
        for match in reversed(exact[1:]):
            code = _remove_token(code, match.group(0))
        return code + suffix, True

    if len(exact) == 1 and code.strip() in (f'"{exact[0].group(1)}"', f'"{exact[0].group(1)}",'):
        if suffix.strip():
            indent = code[: len(code) - len(code.lstrip())]
            return indent + suffix.lstrip() + newline, True
        return None, True
    for match in reversed(exact):
        code = _remove_token(code, match.group(0))
    if not code.strip() and not suffix.strip():
        return None, True
    return code + suffix, True


def _update_repos_key(stripped: str) -> str | None:
    match = _UPDATE_REPOS_RE.match(stripped)
    return match.group(1) if match else None


def _repo_value(stripped: str) -> str | None:
    match = _REPO_RE.match(stripped)
    return match.group(1) if match else None


def _rewrite_prek(text: str, repo_revs: dict[str, str], repo_tags: dict[str, tuple[str, ...]]) -> str:
    """Point each managed repo's `rev` and `[update.repos]` pins at its source's refs.

    Blocks and tables are matched to mise sources by canonical URL, so unrelated
    repos pinned at the same tag are never touched. The table header itself is
    never rewritten, glob patterns are preserved, and exact pins are
    deduplicated to one per managed ref.
    """
    out: list[str] = []
    repo_rev: str | None = None
    table_tags: tuple[str, ...] | None = None
    table_emitted = False
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        rewritten: str | None = line
        if stripped.startswith("[[repos]]"):
            repo_rev = None
            table_tags = None
            table_emitted = False
        elif (key := _update_repos_key(stripped)) is not None:
            repo_rev = None
            table_tags = repo_tags.get(_canonical_source(key))
            table_emitted = False
            out.append(line)
            continue
        elif stripped.startswith("["):
            repo_rev = None
            table_tags = None
            table_emitted = False
        elif (repo := _repo_value(stripped)) is not None:
            table_tags = None
            table_emitted = False
            repo_rev = repo_revs.get(_canonical_source(repo))
        if repo_rev is not None:
            rewritten = _rewrite_repo_rev(line, repo_rev)
        elif table_tags is not None:
            rewritten, table_emitted = _rewrite_tag_tokens(line, table_tags, table_emitted)
        if rewritten is not None:
            out.append(rewritten)
    return "".join(out)


def _rewrite_projects_constants(text: str, refs: list[tuple[str, str]] | None, hook_ref: str | None) -> str:
    """Mirror per-category refs in `SHARED_REFS` and the hooks pin in `SHARED_REF`.

    Multiple upstream sources are left alone: `_projects.py` models this
    template's single shared source, so extra sources need their own test wiring.
    """
    if refs is None:
        return text
    lines = text.splitlines(keepends=True)
    starts = [index for index, line in enumerate(lines) if line.startswith(_PROJECTS_REFS_START)]
    if len(starts) != 1:
        raise ValueError("expected exactly one SHARED_REFS assignment in tests/_projects.py")
    start = starts[0]
    end = next((index for index in range(start + 1, len(lines)) if lines[index].strip() == "}"), None)
    if end is None:
        raise ValueError("unterminated SHARED_REFS mapping in tests/_projects.py")
    newline = "\r\n" if lines[start].endswith("\r\n") else "\n"
    block = [f"SHARED_REFS = {{{newline}"]
    block.extend(f'    "{category}": "{ref}",{newline}' for category, ref in refs)
    block.append(f"}}{newline}")
    text = "".join(lines[:start] + block + lines[end + 1 :])
    if hook_ref is not None:
        updated, count = _PROJECTS_REF_RE.subn(rf"\g<1>{hook_ref}\g<2>", text)
        if count != 1:
            raise ValueError("expected exactly one SHARED_REF assignment in tests/_projects.py")
        text = updated
    return text


def _load_mise_toml(path: Path) -> str:
    try:
        return path.read_text()
    except OSError:
        raise ValueError(f"missing {path.name}; run from the project root or pass --root") from None


def _project_refs(
    includes: list[Include],
    include_targets: dict[tuple[str, str], str],
    sources: list[str],
) -> list[tuple[str, str]] | None:
    """Category-to-ref entries for `tests/_projects.py`, limited to one shared source."""
    if len(sources) != 1:
        return None
    seen: set[str] = set()
    refs: list[tuple[str, str]] = []
    for include in includes:
        if include.category in seen:
            continue
        seen.add(include.category)
        refs.append((include.category, include_targets[(include.source, include.category)]))
    return refs


def _plan(root: Path, target: str | None) -> Plan:
    """Compute every include target and the rewritten content of each managed file."""
    mise_text = _load_mise_toml(root / "mise.toml")
    includes = _discover_includes(mise_text)
    if not includes:
        raise ValueError("no versioned shared task includes in mise.toml")
    if target is not None and not target.strip():
        raise ValueError("--to needs a non-empty ref")
    include_targets, repo_tags, repo_revs = _resolve_targets(includes, target)
    sources = list(repo_tags)

    template_mode = (root / "templates" / "mise.toml.jinja").is_file()
    prek_path = root / "templates" / "prek.toml" if template_mode else root / "prek.toml"
    projects_refs = _project_refs(includes, include_targets, sources)
    projects_hook_ref = repo_revs[sources[0]] if projects_refs is not None else None

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
            updated = _rewrite_projects_constants(original, projects_refs, projects_hook_ref)
        elif path.name == "prek.toml":
            updated = _rewrite_prek(original, repo_revs, repo_tags)
        else:
            updated = _rewrite_mise_includes(original, include_targets)
        planned.append(PinFile(label, path, updated, updated != original))
    return Plan(include_targets, repo_tags, repo_revs, planned)


def _print_sources(plan: Plan) -> None:
    print(f"sources: { {source: list(tags) for source, tags in plan.repo_tags.items()} }")


def _check(plan: Plan) -> int:
    _print_sources(plan)
    drifted = [pin.label for pin in plan.files if pin.changed]
    for pin in plan.files:
        state = "drifts" if pin.changed else "in sync"
        print(f"{pin.label}: {state}")
    if drifted:
        print(f"shared ref drift in: {', '.join(drifted)}", file=sys.stderr)
        return 1
    return 0


def _apply(plan: Plan) -> int:
    _print_sources(plan)
    for pin in plan.files:
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
        plan = _plan(root, args.to)
    except ValueError as exc:
        print(f"sync_shared_refs: {exc}", file=sys.stderr)
        return 2
    except (OSError, tomllib.TOMLDecodeError) as exc:
        print(f"sync_shared_refs: cannot read mise.toml under {root}: {exc}", file=sys.stderr)
        return 2
    if args.check:
        return _check(plan)
    return _apply(plan)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
