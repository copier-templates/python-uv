"""Regression tests for the `_tasks` git lifecycle in `copier.yaml`.

The git tasks must be safe to run against any destination:

- a fresh copy initialises a repo and records the historical `Init commit`;
- a copy into an already-initialised work tree must reuse it (no second
  `git init`) and commit the scaffold as `chore: scaffold from template`;
- an update commits only the template diff as `chore: update from template`;
- no task may create an empty commit (`--allow-empty` is gone) — every commit is
  guarded so it only runs when something is staged;
- `mise trust` runs before any commit so hook shims see a trusted config;
- commits bypass hooks (`--no-verify`) since `prek install` runs later;
- after committing, `mise run install` + `mise run ci` verify the scaffold
  (the latter only when `ci` exists, i.e. pytest+ruff are installed).

These are structural checks on the parsed YAML: rendering the template costs a
full `uv sync`, and the command contract is fully visible without it.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
import yaml
from conftest import TEMPLATE_ROOT

COPIER_YAML = TEMPLATE_ROOT / "copier.yaml"

# Fixed commit messages (deliberately not configurable questions).
FRESH_COPY_MESSAGE = "Init commit"
EXISTING_COPY_MESSAGE = "chore: scaffold from template"
UPDATE_MESSAGE = "chore: update from template"

# Any of these proves the commit is conditional on staged changes.
DIFF_GUARDS = ("git diff --cached --quiet", "git diff --quiet", "git status --porcelain")

# The work-tree probe that distinguishes a fresh directory from an existing repo.
WORK_TREE_PROBE = "git rev-parse --is-inside-work-tree"


def _copier_config() -> dict[str, Any]:
    """Parse `copier.yaml` (Jinja lives inside quoted scalars, so it loads as YAML)."""
    loaded = yaml.safe_load(COPIER_YAML.read_text())
    assert isinstance(loaded, dict), "copier.yaml must parse to a mapping"
    return loaded


def _tasks() -> list[Any]:
    """Return the declared `_tasks` entries."""
    tasks = _copier_config().get("_tasks")
    assert isinstance(tasks, list), "copier.yaml must declare a _tasks list"
    assert tasks, "copier.yaml _tasks must not be empty"
    return tasks


def _task_command_text(task: Any) -> str:
    """Flatten a `_tasks` entry (list form or `command:` mapping) into one string."""
    if isinstance(task, list):
        assert task, "a list-form _tasks entry must not be empty"
        return " ".join(str(part) for part in task)
    assert isinstance(task, dict), f"_tasks entry must be a list or a mapping, got {task!r}"
    assert "command" in task, f"_tasks mapping without a command: {task!r}"
    command = task["command"]
    if isinstance(command, list):
        return " ".join(str(part) for part in command)
    return str(command)


def _task_when(task: Any) -> str:
    """Return the `when:` expression of a `_tasks` mapping (empty when unconditional)."""
    if isinstance(task, dict) and isinstance(task.get("when"), str):
        return task["when"]
    return ""


def _tasks_for_operation(operation: str) -> list[str]:
    """Command texts of every task gated on `_copier_operation == '<operation>'`."""
    pattern = re.compile(rf"_copier_operation\s*==\s*['\"]{operation}['\"]")
    texts = [_task_command_text(task) for task in _tasks() if pattern.search(_task_when(task))]
    assert texts, f"copier.yaml has no _tasks entry gated on _copier_operation == {operation!r}"
    return texts


def _joined(texts: list[str]) -> str:
    """Join task command texts so index-based ordering checks work across entries."""
    return "\n".join(texts)


def _task_indexes(texts: list[str], *needles: str) -> list[int]:
    """Indexes of task texts containing every needle."""
    return [i for i, text in enumerate(texts) if all(needle in text for needle in needles)]


@pytest.fixture(scope="module")
def copier_tasks() -> list[Any]:
    """Parsed `_tasks` entries from `copier.yaml` (parsed once per module)."""
    return _tasks()


@pytest.fixture(scope="module")
def copier_task_texts(copier_tasks: list[Any]) -> list[str]:
    """Flattened command text of every `_tasks` entry."""
    return [_task_command_text(task) for task in copier_tasks]


def test_copy_task_branches_on_existing_repo():
    """Copy must detect an existing work tree and pick the matching commit message."""
    copy_text = _joined(_tasks_for_operation("copy"))

    assert WORK_TREE_PROBE in copy_text, (
        f"the copy task must probe for an existing work tree with `{WORK_TREE_PROBE}` before touching git state"
    )
    assert FRESH_COPY_MESSAGE in copy_text, f"a fresh copy must still commit as {FRESH_COPY_MESSAGE!r}"
    assert EXISTING_COPY_MESSAGE in copy_text, f"a copy into an existing repo must commit as {EXISTING_COPY_MESSAGE!r}"


def test_copy_task_skips_reinit_when_existing():
    """`git init` must be conditional: an existing repo must not be re-initialised."""
    copy_text = _joined(_tasks_for_operation("copy"))

    assert "git init" in copy_text, "a fresh copy still needs `git init` to create the repository"
    assert "git init . && git add" not in copy_text, (
        "`git init` must not be chained unconditionally in front of `git add -A`; "
        "an existing work tree has to be reused instead of re-initialised"
    )
    assert not copy_text.lstrip().startswith("git init"), (
        "the copy task must probe the work tree before running `git init`"
    )

    probe = copy_text.find(WORK_TREE_PROBE)
    init = copy_text.find("git init")
    assert probe != -1 and init != -1, "expected both the work-tree probe and `git init` in the copy task"
    assert probe < init, (
        f"`{WORK_TREE_PROBE}` (offset {probe}) must come before `git init` (offset {init}) "
        "so the initialisation can be skipped inside an existing repo"
    )


def test_no_allow_empty_commits():
    """No task may force an empty commit: `--allow-empty` must be gone from the payload."""
    offenders = [text for text in (_task_command_text(task) for task in _tasks()) if "--allow-empty" in text]
    assert not offenders, f"_tasks must not create empty commits, found `--allow-empty` in: {offenders!r}"


def test_commits_only_when_changes():
    """Every committing task (copy and update) must be guarded on staged changes."""
    for operation in ("copy", "update"):
        commits = [text for text in _tasks_for_operation(operation) if "git commit" in text]
        assert commits, f"copier.yaml has no committing task for the {operation!r} operation"
        for text in commits:
            assert any(guard in text for guard in DIFF_GUARDS), (
                f"the {operation!r} commit must be guarded by one of {DIFF_GUARDS!r} "
                f"so it only runs when something is staged, got: {text!r}"
            )


def test_update_task_commits_with_update_message():
    """`copier update` must commit its template diff with the fixed update message."""
    matching = [text for text in _tasks_for_operation("update") if UPDATE_MESSAGE in text]
    assert matching, (
        f"copier.yaml must declare an update task committing with {UPDATE_MESSAGE!r}, "
        f"got: {_tasks_for_operation('update')!r}"
    )
    for text in matching:
        assert "git commit" in text, f"the task carrying {UPDATE_MESSAGE!r} must commit, got: {text!r}"
        assert any(guard in text for guard in DIFF_GUARDS), (
            f"the update commit must be guarded by one of {DIFF_GUARDS!r} so a no-op update "
            f"creates no commit, got: {text!r}"
        )


def test_mise_trust_runs_before_git_commits(copier_task_texts: list[str]):
    """`mise trust` must precede any committing task.

    Regression: the scaffold commit runs prek hooks resolved through mise
    shims. With `mise trust` ordered after the commit, an untrusted
    `mise.toml` makes the shellcheck hook fail and aborts the whole copy
    (`mise ERROR ... are not trusted` inside the hook output).
    """
    trust_indexes = _task_indexes(copier_task_texts, "mise trust")
    commit_indexes = _task_indexes(copier_task_texts, "git commit")
    assert trust_indexes, "copier.yaml must declare a `mise trust` task"
    assert commit_indexes, "copier.yaml must declare committing tasks"
    assert min(trust_indexes) < min(commit_indexes), (
        f"`mise trust` (indexes {trust_indexes}) must run before any "
        f"`git commit` (indexes {commit_indexes}) so hooks see a trusted config"
    )


@pytest.mark.parametrize("operation", ["copy", "update"])
def test_commits_bypass_hooks(operation: str):
    """Scaffold/update commits must not depend on hook success (`--no-verify`).

    `prek install` only runs later via `mise run install`, so the scaffold
    commit must succeed whether hooks are installed, untrusted, or offline.
    """
    commits = [text for text in _tasks_for_operation(operation) if "git commit" in text]
    assert commits, f"copier.yaml has no committing task for the {operation!r} operation"
    for text in commits:
        assert "--no-verify" in text, (
            f"the {operation!r} commit must pass `--no-verify` so scaffold "
            f"never fails on hook/mise-trust state, got: {text!r}"
        )


def test_verify_tasks_run_after_commits(copier_task_texts: list[str]):
    """`mise run install` + `mise run ci` must verify the scaffold after committing.

    Both run for copy and update so a fresh project (and every template
    update) is proven installed and green before copier reports success.
    """
    installs = _task_indexes(copier_task_texts, "mise", "run", "install")
    verifications = _task_indexes(copier_task_texts, "mise", "run", " ci")
    commits = _task_indexes(copier_task_texts, "git commit")
    assert installs, "copier.yaml must declare a `mise run install` verify task"
    assert verifications, "copier.yaml must declare a `mise run ci` verify task"
    assert min(installs) > max(commits), (
        f"`mise run install` (indexes {installs}) must run after the scaffold commits (indexes {commits})"
    )
    assert min(verifications) > max(installs), (
        f"`mise run ci` (indexes {verifications}) must run after `mise run install` (indexes {installs})"
    )


@pytest.mark.parametrize(("task_name", "needle"), [("install", "install"), ("ci", " ci")])
def test_verify_tasks_cover_copy_and_update(
    copier_tasks: list[Any], copier_task_texts: list[str], task_name: str, needle: str
):
    """Every verify task must run for both copy and update (not just one)."""
    indexes = _task_indexes(copier_task_texts, "mise", "run", needle)
    assert indexes, f"copier.yaml must declare a `mise run {task_name}` verify task"
    for i in indexes:
        when = _task_when(copier_tasks[i])
        assert "'copy'" in when and "'update'" in when, (
            f"the `{task_name}` verify task must cover both copy and update, got when: {when!r}"
        )


@pytest.mark.parametrize("dep", ["pytest", "ruff"])
def test_verify_ci_only_when_defined(copier_tasks: list[Any], copier_task_texts: list[str], dep: str):
    """`mise run ci` exists only with pytest+ruff, so the guard must pin the computed-facts derivation (with_pytest/with_ruff)."""
    verifications = _task_indexes(copier_task_texts, "mise", "run", " ci")
    assert verifications, "copier.yaml must declare a `mise run ci` verify task"
    for i in verifications:
        when = _task_when(copier_tasks[i])
        assert "with_pytest and with_ruff" in when, (
            "the `mise run ci` task must be gated on the with_pytest and with_ruff computed facts "
            f"(ci is only rendered when pytest AND ruff are present), got when: {when!r}"
        )
        assert f"with_{dep}" in when, (
            f"the `mise run ci` task must reference the with_{dep} computed fact, got when: {when!r}"
        )
