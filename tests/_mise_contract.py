"""Task-graph contract reader shared by the mise assertion test modules.

The `tests/` suite asserts the rendered `mise.toml` and the
`templates/mise.toml.jinja` source against the task-name and dependency
contract documented in `CODING_STANDARDS.md`. Each test module used to
parse and re-walk those documents on its own; this module centralises the
parsing so every assertion shares one definition of a mise task graph:

- `read_mise_toml(path)` returns the TOML document as a dict;
- `task_names(data)` returns the keys of `data["tasks"]`;
- `refs(task)` returns the subtask names a task depends on, whether they
  come from a `depends` list of strings or from `{task = ...}` steps inside
  a `run` list;
- `run_steps(task)` returns the ordered `task` keys of a `run` list;
- `template_task_names(text)` extracts task header names from the
  `templates/mise.toml.jinja` text (both `[tasks.lint]` and
  `[tasks."lint:python"]` forms).

The module is underscore-prefixed so pytest never collects it; its public
contract is pinned by `test_mise_contract.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

import tomllib

_TASK_HEADER = re.compile(r'^\[tasks\.(?:"([^"]+)"|([^\]]+))\]')


def read_mise_toml(path: Path) -> dict:
    """Parse `path` as TOML and return the document as a dict."""
    return tomllib.loads(path.read_text())


def task_names(data: dict) -> set[str]:
    """Return the keys of `data["tasks"]` as a set."""
    return set(data["tasks"])


def refs(task: dict) -> list[str]:
    """Return the subtask names `task` aggregates via `depends` or ordered run steps."""
    depends = task.get("depends")
    if isinstance(depends, list):
        return [ref for ref in depends if isinstance(ref, str)]
    run = task.get("run")
    if isinstance(run, list):
        return [step["task"] for step in run if isinstance(step, dict) and "task" in step]
    return []


def run_steps(task: dict) -> list[str]:
    """Return the ordered `task` keys of a `run` list, skipping non-dict entries."""
    run = task.get("run")
    if isinstance(run, list):
        return [step["task"] for step in run if isinstance(step, dict) and "task" in step]
    return []


def template_task_names(text: str) -> set[str]:
    """Extract task header names from `mise.toml.jinja` text.

    Matches both bare (`[tasks.lint]`) and quoted (`[tasks."lint:python"]`)
    task headers; every other section contributes nothing.
    """
    names: set[str] = set()
    for line in text.splitlines():
        header = _TASK_HEADER.match(line)
        if header:
            names.add(header.group(1) or header.group(2))
    return names
