"""Contract tests for the `_mise_contract` test helpers.

The refactor of the mise task-graph assertions centralises the parsing of
`mise.toml` and the rendered `mise.toml.jinja` into a small helper module,
`tests/_mise_contract.py` (underscore-prefixed so pytest never collects it).
These tests pin the helper's public contract so downstream assertion
refactors can rely on it:

- `read_mise_toml(path)` returns the TOML document as a dict;
- `task_names(data)` returns the keys of `data["tasks"]`;
- `refs(task)` returns the subtask names a task depends on, whether they
  come from a `depends` list of strings or from `{task = ...}` steps inside
  a `run` list;
- `run_steps(task)` returns the ordered `task` keys of a `run` list;
- `template_task_names(text)` extracts task header names from the
  `templates/mise.toml.jinja` text (both `[tasks.lint]` and
  `[tasks."lint:python"]` forms).

All tests are pure data: no fixtures, no renders.
"""

from __future__ import annotations

from pathlib import Path

from _mise_contract import read_mise_toml, refs, run_steps, task_names, template_task_names

# Realistic slice of the rendered templates/mise.toml.jinja: bare task
# headers, quoted task headers, and non-task sections that must contribute
# nothing to the extracted task names.
MISE_JINJA_SNIPPET = """\
[tools]
python = "3.12"

[tasks.install]
description = "Install project dependencies"
run = "uv sync --dev"

[tasks."lint:python"]
description = "Lint Python with Ruff"
run = "uv run ruff check ."

[tasks.lint]
description = "Run all linters"
depends = ["lint:python", "lint:shell"]

[tasks."lint:shell"]
description = "Lint shell scripts with ShellCheck"
run = "shellcheck -x script.sh"

[env]
_.python.venv = { path = ".venv", create = true }
"""


def test_refs_from_depends_list():
    """`refs` reads the `depends` strings and ignores every other task key."""
    task = {"description": "run everything", "depends": ["a", "b"], "run": "uv run pytest"}
    assert refs(task) == ["a", "b"]


def test_refs_from_run_steps_skips_plain_strings():
    """`refs` collects `task` keys from dict steps and skips plain string steps."""
    task = {"run": [{"task": "x"}, {"task": "y"}, "plain string step"]}
    assert refs(task) == ["x", "y"]


def test_run_steps_returns_ordered_task_keys():
    """`run_steps` keeps step order and skips non-dict entries."""
    task = {"run": [{"task": "first"}, "raw shell text", {"task": "second"}, 42]}
    assert run_steps(task) == ["first", "second"]


def test_template_task_names_extracts_both_header_forms():
    """`template_task_names` finds bare and quoted task headers, ignoring other sections."""
    names = template_task_names(MISE_JINJA_SNIPPET)
    assert names == {"install", "lint", "lint:python", "lint:shell"}
    assert "tools" not in names, "the [tools] section must not contribute a task name"
    assert "env" not in names, "the [env] section must not contribute a task name"


def test_read_mise_toml_and_task_names(tmp_path: Path):
    """`read_mise_toml` parses a real file and `task_names` returns the task keys."""
    toml_path = tmp_path / "mise.toml"
    toml_path.write_text(
        '[tasks."test:unit"]\nrun = "uv run pytest"\n\n[tasks.lint]\ndepends = ["test:unit"]\n',
        encoding="utf-8",
    )
    data = read_mise_toml(toml_path)
    assert task_names(data) == {"test:unit", "lint"}


def test_refs_without_depends_or_run_is_empty():
    """A task with neither `depends` nor `run` has no subtask refs."""
    assert refs({"description": "standalone task"}) == []
