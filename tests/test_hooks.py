"""Prek hook declaration guards.

`templates/prek.toml` ships into generated projects (root `prek.toml` is a
symlink to it). These tests pin the security hook declaration (gitleaks), the
`repo = "builtin"` conversion of pre-commit-hooks, and the priority tiers that
keep file-mutating fixers serial while read-only checks run concurrently.
"""

from __future__ import annotations

from _projects import TEMPLATE_ROOT, load_toml

PREK_TOML = "templates/prek.toml"

# The pinned gitleaks release this suite requires in both trees.
GITLEAKS_REV = "v8.30.1"

# Fragments of the gitleaks `[[repos]]` block, in declaration order.
GITLEAKS_BLOCK = [
    'repo = "https://github.com/gitleaks/gitleaks"',
    f'rev = "{GITLEAKS_REV}"',
    '{ id = "gitleaks", priority = "checks" }',
]

BUILTIN_HOOK_IDS = {
    "check-added-large-files",
    "check-executables-have-shebangs",
    "check-merge-conflict",
    "check-toml",
    "check-yaml",
    "detect-private-key",
    "end-of-file-fixer",
    "fix-byte-order-marker",
    "mixed-line-ending",
    "trailing-whitespace",
}

# Hooks that rewrite files; concurrent writers to one file race, so each needs its own tier.
FILE_FIXER_IDS = {
    "end-of-file-fixer",
    "fix-byte-order-marker",
    "mixed-line-ending",
    "trailing-whitespace",
    "ruff-check",
    "ruff-format",
}


def test_gitleaks_hook_declared():
    """The shipped prek.toml must declare the gitleaks hook pinned to GITLEAKS_REV."""
    rel_path = PREK_TOML
    text = (TEMPLATE_ROOT / rel_path).read_text()
    for fragment in GITLEAKS_BLOCK:
        assert fragment in text, f"{rel_path}: missing gitleaks hook fragment {fragment!r}"
    positions = [text.find(fragment) for fragment in GITLEAKS_BLOCK]
    assert positions == sorted(positions), f"{rel_path}: gitleaks hook fragments out of order: {GITLEAKS_BLOCK}"


def _prek_config() -> dict:
    return load_toml(TEMPLATE_ROOT / PREK_TOML)


def _hooks_by_id(config: dict) -> dict[str, dict]:
    return {hook["id"]: hook for repo in config["repos"] for hook in repo["hooks"]}


def test_pre_commit_hooks_converted_to_builtin_repo():
    """pre-commit-hooks must run as `repo = "builtin"` with the same hook ids, not a remote clone."""
    repos = {repo["repo"]: repo for repo in _prek_config()["repos"]}
    assert "https://github.com/pre-commit/pre-commit-hooks" not in repos
    assert {hook["id"] for hook in repos["builtin"]["hooks"]} == BUILTIN_HOOK_IDS


def test_every_hook_references_declared_priority_alias():
    """Each hook must pick a `[priorities]` alias; otherwise prek falls back to implicit serial ordering."""
    config = _prek_config()
    aliases = config["priorities"]
    for hook_id, hook in _hooks_by_id(config).items():
        assert hook.get("priority") in aliases, f"{hook_id}: priority must name a [priorities] alias"


def test_file_fixers_get_distinct_serial_tiers_before_checks():
    """Fixers rewrite files so each needs its own tier; read-only checks must run after all of them."""
    config = _prek_config()
    aliases = config["priorities"]
    hooks = _hooks_by_id(config)
    fixer_tiers = [aliases[hooks[hook_id]["priority"]] for hook_id in FILE_FIXER_IDS]
    check_tiers = [aliases[hook["priority"]] for hook_id, hook in hooks.items() if hook_id not in FILE_FIXER_IDS]
    assert len(set(fixer_tiers)) == len(fixer_tiers), "file fixers must not share a priority tier"
    assert min(check_tiers) > max(fixer_tiers), "read-only checks must run after every file fixer"


def test_prek_update_enforces_cooldown_days():
    """`prek update` must hold new hook revs back for a release-age cooldown (supply-chain guard)."""
    cooldown_days = _prek_config()["update"]["cooldown_days"]
    assert isinstance(cooldown_days, int) and 1 <= cooldown_days <= 255, "cooldown_days must be 1-255 to be enabled"
