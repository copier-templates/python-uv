"""`prek.toml` guards: security pins, hook priority tiers and formatter scope."""

from __future__ import annotations

from _projects import TEMPLATE_ROOT, load_toml

PREK_TOML = TEMPLATE_ROOT / "templates" / "prek.toml"
PREK = load_toml(PREK_TOML)
HOOKS = {hook["id"]: hook for repo in PREK["repos"] for hook in repo["hooks"]}
GITLEAKS_REPO = "https://github.com/gitleaks/gitleaks"
GITLEAKS_REV = "v8.30.1"
BUILTIN_HOOK_IDS = set(
    "check-added-large-files check-executables-have-shebangs check-merge-conflict check-toml check-yaml detect-private-key end-of-file-fixer fix-byte-order-marker mixed-line-ending trailing-whitespace".split()  # noqa: SIM905
)
# Hooks that rewrite files; concurrent writers to one file race, so each needs its own tier.
FILE_FIXER_IDS = set(
    "end-of-file-fixer fix-byte-order-marker mixed-line-ending trailing-whitespace ruff-check ruff-format taplo-format".split()  # noqa: SIM905
)


def test_prek_security_and_supply_chain_guards():
    """gitleaks is declared against the pinned rev, pre-commit-hooks runs as `builtin`, updates cool down."""
    repos = {repo["repo"]: repo for repo in PREK["repos"]}
    gitleaks = repos[GITLEAKS_REPO]
    assert gitleaks["rev"] == GITLEAKS_REV
    assert {"id": "gitleaks", "priority": "checks"} in gitleaks["hooks"]
    assert "https://github.com/pre-commit/pre-commit-hooks" not in repos
    assert {hook["id"] for hook in repos["builtin"]["hooks"]} == BUILTIN_HOOK_IDS

    cooldown_days = PREK["update"]["cooldown_days"]
    assert isinstance(cooldown_days, int) and 1 <= cooldown_days <= 255, "cooldown_days must be 1-255 to be enabled"


def test_prek_priorities_serialize_fixers_before_checks():
    """Each file fixer needs its own tier; read-only checks share a later tier and run once on pre-commit."""
    aliases = PREK["priorities"]
    assert all(hook.get("priority") in aliases for hook in HOOKS.values()), "every hook must name a [priorities] alias"
    fixer_tiers = [aliases[HOOKS[hook_id]["priority"]] for hook_id in FILE_FIXER_IDS]
    check_tiers = [aliases[hook["priority"]] for hook_id, hook in HOOKS.items() if hook_id not in FILE_FIXER_IDS]
    assert len(set(fixer_tiers)) == len(fixer_tiers), "file fixers must not share a priority tier"
    assert min(check_tiers) > max(fixer_tiers), "read-only checks must run after every file fixer"
    assert PREK.get("default_stages") == ["pre-commit"]


def test_taplo_is_pinned_and_hook_only():
    """taplo lives only in the prek hook, so `mise run format`/`format:check` stay Ruff-only."""
    assert "taplo" in load_toml(TEMPLATE_ROOT / "mise.toml")["tools"]
    tasks = load_toml(TEMPLATE_ROOT / "mise.toml")["tasks"]
    assert "taplo" not in str(tasks["format"]["run"]) and "taplo" not in str(tasks["format:check"]["run"])
    assert HOOKS["taplo-format"].get("files") == "\\.toml$"


def test_ty_check_runs_on_precommit_as_readonly_check():
    """ty type-checks on every commit like ruff, as a read-only `checks`-tier local hook."""
    hook = HOOKS["ty-check"]
    assert hook["entry"] == "uv run ty check"
    assert hook["priority"] == "checks"
    assert hook.get("language") == "system"
    assert hook.get("pass_filenames") is False
    assert hook.get("always_run") is True
    assert "ty-check" not in FILE_FIXER_IDS
