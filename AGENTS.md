# AGENTS.md

Copier template for Python + `uv`, not an app. `templates/` is the payload (`_subdirectory: templates`): `*.jinja` renders, other files copy verbatim. Root tooling never ships; only `templates/` does.

## Gate

Run every command through mise (toolchain pinned in `mise.toml`): other commands can be invoked only if mise task cannot handle them.
Discover tasks via `mise tasks ls` (`mise tasks info <task>` for details). The contract is thin local wrappers (`bootstrap`, `release`) over pinned shared includes, checked by the wiring tests in `tests/test_sync.py` and `tests/test_rendered_mise.py`.
Tight loop: `mise run ci` green before delivery.
Work on an isolated worktree or branch; never push — clean up temporary worktrees/branches after merging. Branch names follow `feat/issue-<n>-short-desc` and always be merged via rebase to `main`. Keep `prek` hooks in sync with mise tasks.
Local releases are human-run (`mise run release`); agents never bump versions, tag, or push.
Main agent is the orchestrator: it applies the software engineering best practices in `CODING_STANDARDS.md` and does the work itself by default. Subagents are opt-in and the orchestrator decides when to use them — spawn one only for independent parallel workstreams or a fresh-context review of a risky diff. Subagents never spawn their own; a review subagent stays read-only. State scope explicitly, keep reviewers read-only, and run the delivery gate (`mise run ci`) yourself before integrating. Never pin a model in repo files.

## How-to
- [Changing `templates`/](CODING_STANDARDS.md#changing-templates)
- [Template contract](CODING_STANDARDS.md#template-contract)
- [Working method](CODING_STANDARDS.md#working-method)
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
