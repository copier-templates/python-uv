"""Agent roster and verbatim-payload list stay in sync with the repo."""

from __future__ import annotations

import re

from _projects import TEMPLATE_ROOT

AGENTS_DIR = TEMPLATE_ROOT / ".agents"
AGENTS_DOC = TEMPLATE_ROOT / "AGENTS.md"
AGENT_FILES = sorted(AGENTS_DIR.glob("*.md"))


def test_agent_files_are_declared_in_agents_doc():
    """Every agent definition must be mentioned in `AGENTS.md`."""
    assert AGENT_FILES, f"Expected at least one agent definition in {AGENTS_DIR}"
    agents_doc = AGENTS_DOC.read_text()
    missing = [p.stem for p in AGENT_FILES if f"@{p.stem}" not in agents_doc]
    assert not missing, f"Agents defined in .agents/ but missing from AGENTS.md: {missing}"


def test_agents_doc_mentions_no_undefined_agents():
    """Every `@name` mentioned in `AGENTS.md` must have an agent definition."""
    mentioned = set(re.findall(r"@([A-Za-z][A-Za-z0-9_-]*)", AGENTS_DOC.read_text()))
    undefined = sorted(mentioned - {p.stem for p in AGENT_FILES})
    assert not undefined, f"AGENTS.md mentions agents with no definition in .agents/: {undefined}"


def test_verbatim_payload_list_matches_template_tree():
    """The canonical verbatim-payload list must match the non-`.jinja` files under `templates/`."""
    standards_doc = (TEMPLATE_ROOT / "CODING_STANDARDS.md").read_text()
    section = re.search(r"## Template contract(.*?)(?=\n## |\Z)", standards_doc, re.DOTALL)
    assert section, "Canonical verbatim payload list missing from CODING_STANDARDS.md"
    listed = {
        p.relative_to(TEMPLATE_ROOT).as_posix()
        for token in re.findall(r"`([^`]+)`", section.group(1))
        if token.startswith("templates/")
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
