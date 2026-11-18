"""Root repository hygiene: TOML formatting, agent roster, verbatim payload list and Copier settings."""

from __future__ import annotations

import re
import shutil
import subprocess

from _projects import TEMPLATE_ROOT, copier_config

# Copier's documented settings; anything else `_`-prefixed is silently ignored.
VALID_COPIER_SETTINGS = set(
    "_answers_file _envops _exclude _external_data _graceful_exit _jinja_extensions _message_after_copy _message_after_update _message_before_copy _message_before_update _migrations _min_copier_version _preserve_symlinks _secret_questions _skip_if_exists _skip_tasks _subdirectory _tasks _templates_suffix".split()  # noqa: SIM905
)


def test_all_root_toml_files_are_taplo_clean():
    owned = sorted(p.name for p in TEMPLATE_ROOT.glob("*.toml"))
    assert owned, "expected root *.toml files"
    taplo = shutil.which("taplo")
    assert taplo is not None, "taplo must be on PATH (mise toolchain)"
    proc = subprocess.run(
        [taplo, "format", "--check", *owned],
        check=False,
        capture_output=True,
        text=True,
        cwd=TEMPLATE_ROOT,
    )
    assert proc.returncode == 0, f"taplo wants to reformat:\n{proc.stdout}\n{proc.stderr}"


def test_agent_roster_matches_agents_doc():
    """Every `.agents/*.md` is mentioned in `AGENTS.md`, and every `@name` there has a definition."""
    agent_files = sorted((TEMPLATE_ROOT / ".agents").glob("*.md"))
    assert agent_files, "expected at least one agent definition in .agents/"
    stems = {path.stem for path in agent_files}
    agents_doc = (TEMPLATE_ROOT / "AGENTS.md").read_text()
    missing = sorted(stem for stem in stems if f"@{stem}" not in agents_doc)
    undefined = sorted(set(re.findall(r"@([A-Za-z][A-Za-z0-9_-]*)", agents_doc)) - stems)
    assert not missing and not undefined, f"agent roster drift: missing={missing} undefined={undefined}"


def test_verbatim_payload_list_matches_template_tree():
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
    missing, stale = sorted(actual - listed), sorted(listed - actual)
    assert not missing and not stale, (
        f"Canonical verbatim payload list out of sync with templates/: missing={missing} stale={stale}"
    )


def test_copier_yaml_declares_only_real_copier_settings():
    """Every top-level `_` key must be a real Copier setting (no dead `_preserve`)."""
    unknown = {key for key in copier_config() if key.startswith("_")} - VALID_COPIER_SETTINGS
    assert not unknown, f"copier.yaml declares settings Copier never reads: {sorted(unknown)}"
