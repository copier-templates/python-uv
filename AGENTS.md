# AGENTS.md

Copier template for Python + `uv`, not an app. `templates/` is the payload (`_subdirectory: templates`): `*.jinja` renders, other files copy verbatim. Root tooling never ships; only `templates/` does.

## Gate

Run every command through mise (toolchain pinned in `mise.toml`): other commands can be invoked only if mise task cannot handle them.
Discover tasks via `mise tasks ls` (`mise tasks info <task>` for details). Stable cross-project contract is `TASK_CONTRACT` in `tests/test_sync.py`.
Tight loop: `mise run ci` green before delivery.
Work on the orchestrator-assigned isolated worktree; never push — the orchestrator owns cleanup and fast-forward rebase. Branch names follow `feat/issue-<n>-short-desc` and always be merged via rebase to `main`. Keep `prek` hooks in sync with mise tasks.
Local releases are human-run (`mise run release`); agents never bump versions, tag, or push.
Split, dispatch, and delivery sequence: `.agents/orchestrator.md` (single owner; load it before planning).
Workers never spawn sub-agents; `@reviewer` stays read-only. Never pin a model in repo files.

## Roles (lazy-load `.agents/*.md` — load only the file you need)

You start as `@orchestrator`. Dispatch `@coder` / `@docs-writer` / `@reviewer` as subagents; never invert.

| Role | Invoked by | File | Use for |
|---|---|---|---|
| `@orchestrator` | session default | `.agents/orchestrator.md` | Split policy, planning, dispatch, delivery gate (integration-only: merge/rebase/squash/cleanup, no content edits) |
| `@coder` | orchestrator only | `.agents/coder.md` | Owns all content edits via strict ATDD: RED test first, then scoped GREEN, granular commits |
| `@docs-writer` | orchestrator only | `.agents/docs-writer.md` | Owns standalone prose docs (root `*.md`, `docs/`, `GLOSSARY.md`, ADRs); no code, config, or `templates/` |
| `@reviewer` | orchestrator only | `.agents/reviewer.md` | Read-only fresh-context diff review; suggests fixups as text, `@coder` applies |

The `.agents/*.md` files stay the single source of truth and are loaded on demand.

How-to:
- [Changing `templates`/](CODING_STANDARDS.md#changing-templates)
- [Template contract](CODING_STANDARDS.md#template-contract)
- [Shell](CODING_STANDARDS.md#shell)
- [Refactoring](CODING_STANDARDS.md#refactoring)
- [Security and `copier.yaml`](CODING_STANDARDS.md#security-and-copieryaml)
- [Commits and branches](CODING_STANDARDS.md#commits-and-branches)

## Agent skills

### Issue tracker

Issues and specs live in GitHub Issues (`copier-templates/python-uv`) via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` at the root, ADRs in `docs/adr/`. See `docs/agents/domain.md`.
