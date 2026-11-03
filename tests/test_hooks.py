"""Security-hook declaration guards.

The gitleaks secret-scanning hook must be declared identically in both
`prek.toml` (root) and `templates/prek.toml` (the payload shipped into
generated projects): a pinned `rev` plus the `gitleaks` hook id, in
declaration order. These are pure text assertions on the repository itself
(no Copier render, no fixtures); they pin the security-hook contract locally
so that dropping, unpinning, or desyncing the declaration fails the suite
immediately.
"""

from __future__ import annotations

import pytest
from conftest import TEMPLATE_ROOT

# Paths (relative to the template root) that must both declare the hook.
PREK_TREES = ["prek.toml", "templates/prek.toml"]

# The pinned gitleaks release this suite requires in both trees.
GITLEAKS_REV = "v8.30.1"

# Fragments of the gitleaks `[[repos]]` block, in declaration order.
GITLEAKS_BLOCK = [
    'repo = "https://github.com/gitleaks/gitleaks"',
    f'rev = "{GITLEAKS_REV}"',
    '{ id = "gitleaks" }',
]


@pytest.mark.parametrize("rel_path", PREK_TREES)
def test_gitleaks_hook_declared_in_both_trees(rel_path: str):
    """The gitleaks hook must be declared, pinned to GITLEAKS_REV, in both prek trees."""
    text = (TEMPLATE_ROOT / rel_path).read_text()
    for fragment in GITLEAKS_BLOCK:
        assert fragment in text, f"{rel_path}: missing gitleaks hook fragment {fragment!r}"
    positions = [text.find(fragment) for fragment in GITLEAKS_BLOCK]
    assert positions == sorted(positions), f"{rel_path}: gitleaks hook fragments out of order: {GITLEAKS_BLOCK}"


def test_security_hooks_are_byte_synced_between_trees():
    """Root and template-payload prek.toml must be byte-identical (security-hook contract)."""
    root_bytes = (TEMPLATE_ROOT / "prek.toml").read_bytes()
    payload_bytes = (TEMPLATE_ROOT / "templates" / "prek.toml").read_bytes()
    assert root_bytes == payload_bytes, (
        "Security-hook declarations drifted: prek.toml is not byte-identical to templates/prek.toml"
    )
