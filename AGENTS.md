# AGENTS.md

Copier template for Python + `uv`, not an app. `templates/` is the payload (`_subdirectory: templates`): `*.jinja` renders, other files copy verbatim. Root tooling never ships; only `templates/` does.

## Gate

Run every command through mise (toolchain pinned in `mise.toml`): never invoke `pytest`, `ruff`, `shellcheck`, or `uv` directly.
Tight loop: `mise run ci` green before delivery.
Work on the orchestrator-assigned isolated branch or worktree; never push — the orchestrator owns cleanup and fast-forward rebase. Keep `prek` hooks in sync with mise tasks.
Releases are human-run (`mise run release`); agents never bump versions, tag, or push.
Split: docs-only/small changes run single-shot; any `templates/` change runs `@tester` → `@coder` → `@reviewer` with a matching `tests/` regression test.
Workers never spawn sub-agents; `@reviewer` stays read-only. For orchestrator prefer `muse-spark-1.3` at `xhigh`, else `claude-opus-5.5` (or latest `opus`), else the tool default. Never pin a model in repo files.

## Roles (lazy-load `.agents/*.md` — load only the file you need)

| Role | File | Use for |
|---|---|---|
| `@orchestrator` | `.agents/orchestrator.md` | Planning, dispatch, delivery gate (primary; no direct file edits — merges worker commits and cleans up branches/worktrees) |
| `@tester` | `.agents/tester.md` | RED regression tests, verification runs |
| `@coder` | `.agents/coder.md` | Scoped GREEN implementation and granular commits |
| `@reviewer` | `.agents/reviewer.md` | Read-only fresh-context diff review |

How-to: [Changing `templates`/](CODING_STANDARDS.md#changing-templates), [Template contract](CODING_STANDARDS.md#template-contract), [Shell](CODING_STANDARDS.md#shell), [Refactoring](CODING_STANDARDS.md#refactoring), [Security and `copier.yaml`](CODING_STANDARDS.md#security-and-copieryaml), [Commits and branches](CODING_STANDARDS.md#commits-and-branches), [Mise task map](CODING_STANDARDS.md#mise-task-map).

## Agent skills

### Issue tracker

Issues and specs live in GitHub Issues (`copier-templates/python-uv`) via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` at the root, ADRs in `docs/adr/`. See `docs/agents/domain.md`.
