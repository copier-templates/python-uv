# 0002. Lifecycle script for Copier tasks

Status: Accepted

## Context

The post-copy and post-update Git steps (`git init`, staging, commits and the
`mise run install`/`ci` verification) were inline shell one-liners in `_tasks`
in `copier.yaml`. Quoting and branching were hard to read, and nothing could
test them without rendering a full project.

## Decision

- The steps live in `tasks/lifecycle.py`, a stdlib-only script.
- `copier.yaml` `_tasks` invokes it as one entry: `{{ _copier_python }}` runs it with Copier's own interpreter, and `{{ _copier_conf.src_path }}` resolves it from the template source, not the destination.
- The script never ships, because only `templates/` is copied.

## Consequences

- `tests/test_git_tasks.py` exercises the logic against real Git in temporary directories, with a fake `mise`.
- The script must stay stdlib-only, since it runs under whatever interpreter runs Copier and gets no dependency installation.
- `_tasks` in `copier.yaml` still shows the call order, so the post-copy flow is visible without opening the script.
