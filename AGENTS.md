# AGENTS.md

Copier template for Python + `uv`, not an app. `templates/` is the payload (`_subdirectory: templates`): `*.jinja` renders, other files copy verbatim. Root tooling never ships; only `templates/` does.

## Gate

Run every command through mise (toolchain pinned in `mise.toml`): other commands can be invoked only if mise task cannot handle them.
Tight loop: `mise run ci` green before delivery.
Work on the orchestrator-assigned isolated branch or worktree; never push — the orchestrator owns cleanup and fast-forward rebase. Branch names follow `feat|hotfix/issue-<n>-short-desc` and always merge to `main` (no develop or release branches). Keep `prek` hooks in sync with mise tasks.
Local releases are human-run (`mise run release`); agents never bump versions, tag, or push, and never apply `release:*` labels. The CI release job in `.github/workflows/release.yml` cuts, validates, pushes, and merges a labeled release PR once gates pass.
Split, dispatch, and delivery sequence: `.agents/orchestrator.md` (single owner; load it before planning).
Workers never spawn sub-agents; `@reviewer` stays read-only. Never pin a model in repo files.

## Roles (lazy-load `.agents/*.md` — load only the file you need)

| Role | File | Use for |
|---|---|---|
| `@orchestrator` | `.agents/orchestrator.md` | Split policy, planning, dispatch, delivery gate (primary; no direct file edits — merges worker commits and cleans up branches/worktrees) |
| `@coder` | `.agents/coder.md` | Strict ATDD: acceptance test RED, then scoped GREEN implementation, granular commits |
| `@reviewer` | `.agents/reviewer.md` | Read-only fresh-context diff review |

These roles are registered in `opencode.json`, so a new build session starts as `@orchestrator` and the workers are launchable subagents. The `.agents/*.md` files stay the single source of truth and are loaded on demand; the config only wires them and enforces the rules above (no orchestrator edits, no worker subagents, no pushing). Keep model choices out of the repo config.

How-to: [Changing `templates`/](CODING_STANDARDS.md#changing-templates), [Template contract](CODING_STANDARDS.md#template-contract), [Shell](CODING_STANDARDS.md#shell), [Refactoring](CODING_STANDARDS.md#refactoring), [Security and `copier.yaml`](CODING_STANDARDS.md#security-and-copieryaml), [Commits and branches](CODING_STANDARDS.md#commits-and-branches), [Mise task map](CODING_STANDARDS.md#mise-task-map).

## Agent skills

### Issue tracker

Issues and specs live in GitHub Issues (`copier-templates/python-uv`) via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` at the root, ADRs in `docs/adr/`. See `docs/agents/domain.md`.
