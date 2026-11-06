"""Vulture allowlist: false positives that look unused but are used dynamically.

Intent: vulture is static — it cannot see usage via strings, plugins,
`pytest` fixtures, CLI entrypoints, or public API consumed outside this repo.
When `mise run lint:deadcode` flags something intentionally kept, allowlist
it here instead of weakening the whole gate (`min_confidence`,
`ignore_names` in `pyproject.toml` are for broad categories, this file is
for specific names).

This file must stay listed in `[tool.vulture] paths` in `pyproject.toml`:
vulture scans it, so each entry below counts as a "use".

Workflow:
    1. `mise run lint:deadcode` (or `uv run vulture --make-whitelist`)
    2. Confirm a finding is intentional (public API, dynamic use).
    3. Paste its `--make-whitelist` line below. The trailing comment is
       just a note — the bare `name` / `_.name` expression is what marks
       it as used.

Format (paste as-is from `--make-whitelist` output):
    my_func  # unused function (src/mod.py:12)
    MyClass  # unused class (src/mod.py:20)
    _.method  # unused method (src/mod.py:25)
    _.attr  # unused attribute (src/mod.py:30)

See https://vulture.readthedocs.io/en/latest/whitelists.html
"""

# Nothing allowlisted by default.
__all__: list[str] = []
