"""Security-hook declaration guards.

The gitleaks secret-scanning hook must be declared in `templates/prek.toml`
(shipped into generated projects; root `prek.toml` is a symlink to it): a
pinned `rev` plus the `gitleaks` hook id, in declaration order.
"""

from __future__ import annotations

from _projects import TEMPLATE_ROOT

PREK_TOML = "templates/prek.toml"

# The pinned gitleaks release this suite requires in both trees.
GITLEAKS_REV = "v8.30.1"

# Fragments of the gitleaks `[[repos]]` block, in declaration order.
GITLEAKS_BLOCK = [
    'repo = "https://github.com/gitleaks/gitleaks"',
    f'rev = "{GITLEAKS_REV}"',
    '{ id = "gitleaks" }',
]


def test_gitleaks_hook_declared():
    """The shipped prek.toml must declare the gitleaks hook pinned to GITLEAKS_REV."""
    rel_path = PREK_TOML
    text = (TEMPLATE_ROOT / rel_path).read_text()
    for fragment in GITLEAKS_BLOCK:
        assert fragment in text, f"{rel_path}: missing gitleaks hook fragment {fragment!r}"
    positions = [text.find(fragment) for fragment in GITLEAKS_BLOCK]
    assert positions == sorted(positions), f"{rel_path}: gitleaks hook fragments out of order: {GITLEAKS_BLOCK}"
