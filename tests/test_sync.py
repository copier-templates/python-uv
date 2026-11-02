"""Root-to-template sync guards.

`prek.toml`, the `.github/workflows/*.yml` files, and the mise task-name
contract documented in `CODING_STANDARDS.md` all ship (verbatim or mirrored)
into generated projects via `templates/`. These are pure text assertions on
the repository itself (no Copier render, no fixtures) that fail the suite the
moment a root file drifts from its template payload or a task name leaves the
documented contract.
"""

from __future__ import annotations

import difflib
import re

import tomllib
from conftest import TEMPLATE_ROOT


def _assert_bytes_equal(root_rel: str, template_rel: str) -> None:
    """Assert the root file and its template payload are byte-identical."""
    root = TEMPLATE_ROOT / root_rel
    payload = TEMPLATE_ROOT / template_rel
    root_bytes = root.read_bytes()
    payload_bytes = payload.read_bytes()
    if root_bytes != payload_bytes:
        diff = "\n".join(
            difflib.unified_diff(
                root.read_text().splitlines(),
                payload.read_text().splitlines(),
                fromfile=root_rel,
                tofile=template_rel,
                lineterm="",
            )
        )
        raise AssertionError(f"{root_rel} drifted from {template_rel}:\n{diff}")


def test_prek_toml_stays_in_sync():
    """Root and template-payload prek.toml must be byte-identical (verbatim copy)."""
    _assert_bytes_equal("prek.toml", "templates/prek.toml")


def test_workflow_files_stay_in_sync():
    """Workflow YAML filename sets must match, and each pair must be byte-identical."""
    root_dir = TEMPLATE_ROOT / ".github" / "workflows"
    payload_dir = TEMPLATE_ROOT / "templates" / ".github" / "workflows"
    root_names = {p.name for p in root_dir.glob("*.yml")}
    payload_names = {p.name for p in payload_dir.glob("*.yml")}
    assert root_names, f"Expected at least one workflow file in {root_dir}"
    assert root_names == payload_names, (
        "Workflow filename sets drifted: "
        f"root-only={sorted(root_names - payload_names)}, "
        f"payload-only={sorted(payload_names - root_names)}"
    )
    for name in sorted(root_names):
        _assert_bytes_equal(f".github/workflows/{name}", f"templates/.github/workflows/{name}")


TASK_HEADER = re.compile(r'^\[tasks\.(?:"([^"]+)"|([^\]]+))\]')


def test_mise_task_contract_parity():
    """Every task name in the documented contract must exist in root and template mise.toml."""
    standards_doc = (TEMPLATE_ROOT / "CODING_STANDARDS.md").read_text()
    match = re.search(r"expose the same task names:\s*([^\n]*?)\.", standards_doc)
    assert match, "Task contract line missing from CODING_STANDARDS.md"
    contract = set(re.findall(r"`([^`]+)`", match.group(1)))
    assert contract, "No task names parsed from the CODING_STANDARDS.md contract line"

    root_tasks = set(tomllib.loads((TEMPLATE_ROOT / "mise.toml").read_text())["tasks"])

    template_text = (TEMPLATE_ROOT / "templates" / "mise.toml.jinja").read_text()
    template_tasks = set()
    for line in template_text.splitlines():
        header = TASK_HEADER.match(line)
        if header:
            template_tasks.add(header.group(1) or header.group(2))

    missing_root = sorted(contract - root_tasks)
    missing_template = sorted(contract - template_tasks)
    assert not missing_root and not missing_template, (
        "mise task contract drift: "
        f"missing from root mise.toml={missing_root}, "
        f"missing from templates/mise.toml.jinja={missing_template}"
    )
