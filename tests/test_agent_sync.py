"""Agent roster and verbatim-payload list stay in sync with the repo."""

from __future__ import annotations

import re
import subprocess

import pytest
from _projects import GIT, TEMPLATE_ROOT

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


def _git_check_ignore(rel_path: str) -> int:
    """Exit code of `git check-ignore`: 0 ignored, 1 not ignored."""
    return subprocess.run(  # noqa: S603
        [GIT, "check-ignore", "--no-index", "-q", "--", rel_path],
        cwd=TEMPLATE_ROOT,
        check=False,
    ).returncode


def test_payload_bytecode_is_git_ignored():
    """Payload bytecode must stay ignored while source Payload files stay tracked."""
    bytecode = "templates/scripts/__pycache__/release_version.cpython-312.pyc"
    assert _git_check_ignore(bytecode) == 0, f"{bytecode} would be committed despite the bytecode ignore rules"
    assert _git_check_ignore("templates/scripts/release_version.py") == 1, "source Payload files must stay tracked"


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
        and "__pycache__" not in p.parts
        and p.suffix != ".pyc"
        and "licenses" not in p.relative_to(TEMPLATE_ROOT / "templates").parts
    }
    missing = sorted(actual - listed)
    stale = sorted(listed - actual)
    assert not missing and not stale, (
        "Canonical verbatim payload list in CODING_STANDARDS.md out of sync with templates/: "
        f"missing={missing} stale={stale}"
    )


@pytest.mark.parametrize(
    "rel_path",
    ["templates/scripts/release_version.py", "templates/scripts/lib/release-common.sh"],
)
def test_verbatim_payload_list_names_release_payload_files(rel_path: str):
    """The release module and logging helper must be listed as verbatim payload."""
    standards_doc = (TEMPLATE_ROOT / "CODING_STANDARDS.md").read_text()
    section = re.search(r"## Template contract(.*?)(?=\n## |\Z)", standards_doc, re.DOTALL)
    assert section, "Canonical verbatim payload list missing from CODING_STANDARDS.md"
    assert f"`{rel_path}`" in section.group(1), f"Missing {rel_path} from the verbatim payload table"
