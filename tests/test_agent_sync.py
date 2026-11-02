"""Agent roster sync tests.

`AGENTS.md` is the source of truth for repo rules, and the portable agent
definitions under `.agents/` must stay discoverable from it: every
agent file has to be named there, every `@name` mentioned there has to be a
real agent, and every agent must point back to `AGENTS.md`. `.gitignore` must
re-include agent markdown without re-including secrets or bytecode. The
canonical verbatim-payload list in `CODING_STANDARDS.md` (referenced by the
`@reviewer` checklist) must match the template tree. These are
pure text assertions on the repository itself (no Copier render, no fixtures).
"""

from __future__ import annotations

import re
import shutil
import subprocess

from conftest import TEMPLATE_ROOT

AGENTS_DIR = TEMPLATE_ROOT / ".agents"
AGENTS_DOC = TEMPLATE_ROOT / "AGENTS.md"

# Module-level constant: absolute path to the mise-pinned git executable (avoids partial-path lint)
GIT = shutil.which("git") or "git"

# Module-level constant: collect agent definitions once per module load
AGENT_FILES = sorted(AGENTS_DIR.glob("*.md"))

# Module-level constant: `@`-mentions in `AGENTS.md` that are deliberately not agents
NON_AGENT_AT_MENTIONS: set[str] = set()


def _is_ignored(rel_path: str) -> int:
    """Return `git check-ignore`'s exit code for `rel_path`: 0 ignored, 1 not ignored."""
    result = subprocess.run(
        [GIT, "check-ignore", "-q", "--no-index", rel_path],
        cwd=TEMPLATE_ROOT,
        capture_output=True,
        check=False,
    )
    return result.returncode


def test_agent_files_are_declared_in_agents_doc():
    """Regression test: every agent definition must be mentioned in `AGENTS.md`."""
    assert AGENT_FILES, f"Expected at least one agent definition in {AGENTS_DIR}"
    agents_doc = AGENTS_DOC.read_text()
    missing = [p.stem for p in AGENT_FILES if f"@{p.stem}" not in agents_doc]
    assert not missing, f"Agents defined in .agents/ but missing from AGENTS.md: {missing}"


def test_agents_doc_mentions_no_undefined_agents():
    """Regression test: every `@name` mentioned in `AGENTS.md` must have an agent definition."""
    agents_doc = AGENTS_DOC.read_text()
    stems = {p.stem for p in AGENT_FILES}
    mentioned = set(re.findall(r"@([A-Za-z][A-Za-z0-9_-]*)", agents_doc))
    undefined = sorted(mentioned - stems - NON_AGENT_AT_MENTIONS)
    assert not undefined, f"AGENTS.md mentions agents with no definition in .agents/: {undefined}"


def test_agents_gitignore_scoped_to_agent_markdown():
    """Regression test: `.gitignore` re-includes agent markdown only, not secrets or bytecode."""
    # 0 == ignored by git, 1 == not ignored
    expectations = {
        ".agents/coder.md": 1,
        ".agents/new-agent.md": 1,
        ".agents/.env": 0,
        ".agents/x.pyc": 0,
    }
    failures = []
    for rel_path, expected in expectations.items():
        actual = _is_ignored(rel_path)
        if actual != expected:
            wanted = "ignored" if expected == 0 else "not ignored"
            got = "ignored" if actual == 0 else "not ignored"
            failures.append(f"{rel_path}: expected {wanted}, got {got} (git check-ignore exit {actual})")
    assert not failures, "Unexpected .gitignore handling under .agents/:\n" + "\n".join(failures)


def test_agents_doc_has_no_direct_tool_fallback():
    """Regression test: `AGENTS.md` must pin the mise-only rule and never allow direct tool invocation."""
    agents_doc = AGENTS_DOC.read_text()
    assert "falling back to direct tool invocation" not in agents_doc, (
        "AGENTS.md still allows direct tool invocation instead of mise tasks"
    )
    assert "never invoke `pytest`, `ruff`, `shellcheck`, or `uv` directly" in agents_doc, (
        "AGENTS.md no longer pins the mise-only rule (never invoke pytest/ruff/shellcheck/uv directly)"
    )


def test_agent_files_defer_to_agents_doc():
    """Regression test: every agent definition must defer to `AGENTS.md` as the source of truth."""
    assert AGENT_FILES, f"Expected at least one agent definition in {AGENTS_DIR}"
    missing = [p.name for p in AGENT_FILES if "AGENTS.md" not in p.read_text()]
    assert not missing, f"Agent definitions not referencing AGENTS.md: {missing}"


def test_verbatim_payload_list_matches_template_tree():
    """Regression test: the canonical verbatim-payload list must match the non-`.jinja` files under `templates/`."""
    standards_doc = (TEMPLATE_ROOT / "CODING_STANDARDS.md").read_text()
    match = re.search(r"Verbatim payload files[^\n]*:\s*([^\n]+)", standards_doc)
    assert match, "Canonical verbatim payload list missing from CODING_STANDARDS.md"
    listed = {
        p.relative_to(TEMPLATE_ROOT).as_posix()
        for token in re.findall(r"`([^`]+)`", match.group(1))
        for p in TEMPLATE_ROOT.glob(token)
        if p.is_file()
    }
    actual = {
        p.relative_to(TEMPLATE_ROOT).as_posix()
        for p in (TEMPLATE_ROOT / "templates").rglob("*")
        if p.is_file()
        and not p.name.endswith(".jinja")
        and "licenses" not in p.relative_to(TEMPLATE_ROOT / "templates").parts
    }
    missing = sorted(actual - listed)
    stale = sorted(listed - actual)
    assert not missing and not stale, (
        "Canonical verbatim payload list in CODING_STANDARDS.md out of sync with templates/: "
        f"missing={missing} stale={stale}"
    )
