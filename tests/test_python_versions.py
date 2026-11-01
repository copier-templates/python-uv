"""Regression tests for the `python_version` question and its maintenance script.

These tests pin the whole Python-version contract:

- the Copier question (`type: str`, default `3.11`, released-only choices between
  machine-managed marker comments) and its placement after `project_type`;
- the `uv python install <version>` task that must precede `uv sync`;
- the payload wiring (`mise.toml` tools, `requires-python`, Ruff `target-version`);
- `scripts/update_python_versions.py`, the stdlib-only helper that refreshes the
  question choices from <https://endoflife.date/api/python.json> (unit-tested with
  a stubbed network, never online);
- Copier `update` behaviour for projects generated before the question existed.

Copier renders are expensive (each runs `uv sync`), so they reuse the
session-scoped fixtures from `conftest.py`.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest
import tomllib
import yaml
from conftest import GIT_IDENTITY, TEMPLATE_ROOT, UPDATE_MARKER, _git, _make_data, _run_copy_from
from copier import run_update
from plumbum import local

COPIER_YAML = TEMPLATE_ROOT / "copier.yaml"
ROOT_MISE_TOML = TEMPLATE_ROOT / "mise.toml"
EXAMPLE_CONFIG = TEMPLATE_ROOT / "examples" / "config-basic.yml"
SCRIPT_PATH = TEMPLATE_ROOT / "scripts" / "update_python_versions.py"

# Mirrors of the script constants: the question block must use exactly these markers.
BEGIN_MARKER = "# python-version-choices: begin (managed by scripts/update_python_versions.py, do not edit)"
END_MARKER = "# python-version-choices: end"

# Managed choice lines look like `        "3.14": "3.14"` (8-space indent under `choices:`).
CHOICE_LINE = re.compile(r'^ {8}"(?P<version>\d+\.\d+)": "(?P=version)"$')
VERSION_KEY = re.compile(r"^\d+\.\d+$")
ANSWER_LINE = r"(?m)^python_version:\s*['\"]{version}['\"]\s*$"

SAMPLE_COPIER_YAML = f"""\
project_name:
    type: str

project_type:
    type: str
    choices:
        Application: app
        Packaged application: package
        Library: lib
    default: package

python_version:
    type: str
    choices:
        {BEGIN_MARKER}
        "3.10": "3.10"
        {END_MARKER}
    default: "3.11"

github_integration:
    type: bool
    default: true
"""

# endoflife.date-shaped records: old cycles, current cycles, an unreleased cycle
# (`latest` empty / missing) and a duplicated cycle must all be handled.
RELEASE_RECORDS = [
    {"cycle": "2.7", "latest": "2.7.18", "eol": "2020-01-01"},
    {"cycle": "3.8", "latest": "3.8.20", "eol": "2024-10-07"},
    {"cycle": "3.11", "latest": "3.11.9", "eol": "2027-10-24"},
    {"cycle": "3.12", "latest": "3.12.7", "eol": "2028-10-24"},
    {"cycle": "3.13", "latest": "3.13.0", "eol": "2029-10-24"},
    {"cycle": "3.14", "latest": "3.14.0", "eol": "2030-10-24"},
    {"cycle": "3.15", "latest": "", "eol": "2031-10-24"},
    {"cycle": "3.12", "latest": "3.12.7", "eol": "2028-10-24"},
]
EXPECTED_SCRIPT_VERSIONS = ["3.14", "3.13", "3.12", "3.11"]


# --------------------------------------------------------------------------- #
# copier.yaml: question, choices, marker block, task graph
# --------------------------------------------------------------------------- #


def _copier_config() -> dict[str, Any]:
    """Parse `copier.yaml` (Jinja lives inside quoted scalars, so it loads as YAML)."""
    loaded = yaml.safe_load(COPIER_YAML.read_text())
    assert isinstance(loaded, dict), "copier.yaml must parse to a mapping"
    return loaded


def _question(name: str) -> dict[str, Any]:
    config = _copier_config()
    assert name in config, f"copier.yaml is missing the {name!r} question"
    question = config[name]
    assert isinstance(question, dict), f"copier.yaml question {name!r} must be a mapping, got {question!r}"
    return question


def _marker_block_lines() -> list[str]:
    """Return the lines strictly between the begin and end marker comments."""
    lines = COPIER_YAML.read_text().splitlines()
    begins = [i for i, line in enumerate(lines) if line.strip() == BEGIN_MARKER]
    ends = [i for i, line in enumerate(lines) if line.strip() == END_MARKER]
    assert len(begins) == 1, f"expected exactly one begin marker, found {len(begins)}"
    assert len(ends) == 1, f"expected exactly one end marker, found {len(ends)}"
    assert begins[0] < ends[0], f"begin marker (line {begins[0] + 1}) must precede end marker (line {ends[0] + 1})"
    return lines[begins[0] + 1 : ends[0]]


def test_python_version_question_is_a_string_with_default_311():
    """Regression test: `python_version` must be a string question defaulting to 3.11."""
    question = _question("python_version")
    assert question.get("type") == "str", f"python_version.type must be str, got {question.get('type')!r}"
    assert question.get("default") == "3.11", f"python_version.default must be '3.11', got {question.get('default')!r}"


def test_python_version_question_follows_project_type():
    """Regression test: the version question belongs directly after `project_type`."""
    keys = list(_copier_config())
    assert "project_type" in keys, "copier.yaml is missing the project_type question"
    assert "python_version" in keys, "copier.yaml is missing the python_version question"
    assert keys.index("project_type") + 1 == keys.index("python_version"), (
        f"python_version must be declared directly after project_type, got order: {[k for k in keys if not k.startswith('_')]}"
    )


def test_python_version_choices_are_released_quoted_versions():
    """Choices must be uniquely keyed, quoted `"3.x": "3.x"` pairs at or above 3.11."""
    choices = _question("python_version").get("choices")
    assert isinstance(choices, dict) and choices, f"python_version.choices must be a non-empty mapping, got {choices!r}"

    values = list(choices.values())
    assert "3.11" in values, f"python_version choices must include '3.11', got {values!r}"
    assert "3.12" in values, f"python_version choices must include '3.12', got {values!r}"
    assert all(isinstance(value, str) for value in values), (
        f"choice values must be quoted strings (else YAML parses floats): {values!r}"
    )
    assert all(VERSION_KEY.match(value) for value in values), f"choice values must look like '3.14': {values!r}"
    assert all(tuple(int(part) for part in value.split(".")) >= (3, 11) for value in values), (
        f"choice values must be released stable versions >= 3.11: {values!r}"
    )
    assert len(values) == len(set(values)), f"duplicate python_version choice values: {values!r}"
    assert all(key == value for key, value in choices.items()), (
        f'choice keys must equal their values (quoted form \'"3.14": "3.14"\'): {choices!r}'
    )
    assert _question("python_version").get("default") in values, "python_version.default must be one of the choices"


def test_python_version_choices_marker_block_is_well_formed():
    """The managed block must hold only 8-space quoted choice lines, newest first."""
    block = [line for line in _marker_block_lines() if line.strip()]
    assert block, "expected at least one choice line inside the managed marker block"
    invalid = [line for line in block if not CHOICE_LINE.match(line)]
    assert not invalid, (
        "the managed marker block must contain only 8-space-indented quoted choice lines "
        f'(e.g. \'        "3.14": "3.14"\'), got: {invalid!r}'
    )


def test_python_version_choices_marker_block_matches_question_choices():
    """The block is the single source of the choices mapping (newest first)."""
    choices = _question("python_version").get("choices")
    assert isinstance(choices, dict)
    block_versions = [CHOICE_LINE.match(line).group("version") for line in _marker_block_lines() if line.strip()]
    assert block_versions == list(choices), (
        f"marker block versions {block_versions!r} must match the parsed choices {list(choices)!r}"
    )


def test_copier_tasks_install_selected_python_before_sync():
    """Regression test: `uv python install <version>` must run before `uv sync`."""
    tasks = _copier_config().get("_tasks")
    assert isinstance(tasks, list), "copier.yaml must declare a _tasks list"

    installs = [
        index for index, task in enumerate(tasks) if isinstance(task, list) and task[:3] == ["uv", "python", "install"]
    ]
    assert len(installs) == 1, f"expected exactly one ['uv', 'python', 'install', ...] task, found {installs!r}"

    install_task = tasks[installs[0]]
    assert len(install_task) == 4, f"uv python install task must carry the version, got {install_task!r}"
    assert "python_version" in install_task[3], (
        f"uv python install must be templated from python_version, got {install_task[3]!r}"
    )

    syncs = [index for index, task in enumerate(tasks) if isinstance(task, list) and task == ["uv", "sync"]]
    assert len(syncs) == 1, f"expected exactly one ['uv', 'sync'] task, found {syncs!r}"
    assert installs[0] < syncs[0], "`uv python install` must be listed before `uv sync`"


def test_root_mise_toml_declares_update_python_versions_task():
    """Regression test: the repo-only task that refreshes the choices must exist."""
    mise = tomllib.loads(ROOT_MISE_TOML.read_text())
    task = mise.get("tasks", {}).get("update:python-versions")
    assert task is not None, "root mise.toml is missing the `update:python-versions` task"
    run = task.get("run", "")
    run_text = "\n".join(run) if isinstance(run, list) else str(run)
    assert "scripts/update_python_versions.py" in run_text, (
        f"`update:python-versions` must run scripts/update_python_versions.py, got {run_text!r}"
    )
    assert "python-versions:update" not in mise.get("tasks", {}), (
        "the retired noun-first `python-versions:update` task must not remain declared"
    )


def test_example_config_pins_python_version():
    """Regression test: the shipped non-interactive example must answer the question."""
    example = EXAMPLE_CONFIG.read_text()
    assert re.search(ANSWER_LINE.format(version=r"3\.11"), example), (
        'examples/config-basic.yml must contain `python_version: "3.11"`'
    )


# --------------------------------------------------------------------------- #
# scripts/update_python_versions.py (stdlib-only, network stubbed)
# --------------------------------------------------------------------------- #


def _load_script_module() -> Any:
    """Import the maintenance script from its path so tests never need packaging."""
    assert SCRIPT_PATH.is_file(), (
        f"missing maintenance script {SCRIPT_PATH.relative_to(TEMPLATE_ROOT)}; "
        "the python_version choices are rewritten by it"
    )
    spec = importlib.util.spec_from_file_location("update_python_versions", SCRIPT_PATH)
    assert spec is not None, f"could not build an import spec for {SCRIPT_PATH}"
    assert spec.loader is not None, f"import spec for {SCRIPT_PATH} has no loader"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script() -> Any:
    """The loaded `update_python_versions` module (fails clearly while it is missing)."""
    return _load_script_module()


def _stub_network(monkeypatch: pytest.MonkeyPatch, module: Any, records: list[dict[str, Any]] | None = None) -> None:
    """Serve a canned endoflife.date payload so `main()` never touches the network."""
    payload = json.dumps(RELEASE_RECORDS if records is None else records).encode("utf-8")

    class _Response:
        """Minimal stand-in for `http.client.HTTPResponse`."""

        status = 200

        def read(self, *_args: Any, **_kwargs: Any) -> bytes:
            return payload

        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *_exc: object) -> bool:
            return False

    def fake_urlopen(*_args: Any, **_kwargs: Any) -> _Response:
        return _Response()

    # Cover both `urllib.request.urlopen(...)` and `from urllib.request import urlopen`.
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    if hasattr(module, "urlopen"):
        monkeypatch.setattr(module, "urlopen", fake_urlopen)


def _stub_network_failure(monkeypatch: pytest.MonkeyPatch, module: Any) -> None:
    """Make every stubbed fetch raise, so `main()` must report the failure itself."""

    def failing_urlopen(*_args: Any, **_kwargs: Any) -> Any:
        raise urllib.error.URLError("boom")

    monkeypatch.setattr(urllib.request, "urlopen", failing_urlopen)
    if hasattr(module, "urlopen"):
        monkeypatch.setattr(module, "urlopen", failing_urlopen)


def test_update_script_exposes_the_documented_contract(script: Any):
    """Regression test: constants the template contract depends on must not drift."""
    assert script.MIN_PYTHON == (3, 11), f"MIN_PYTHON must be (3, 11), got {script.MIN_PYTHON!r}"
    assert script.API_URL == "https://endoflife.date/api/python.json", f"unexpected API_URL: {script.API_URL!r}"
    assert script.BEGIN_MARKER == BEGIN_MARKER, f"unexpected BEGIN_MARKER: {script.BEGIN_MARKER!r}"
    assert script.END_MARKER == END_MARKER, f"unexpected END_MARKER: {script.END_MARKER!r}"


def test_parse_releases_drops_old_and_unreleased_cycles(script: Any):
    """Only released cycles >= 3.11 survive, deduplicated and newest first."""
    assert script.parse_releases(RELEASE_RECORDS) == EXPECTED_SCRIPT_VERSIONS


def test_parse_releases_sorts_newest_first(script: Any):
    """Input order from the API is not trusted; output must still be newest first."""
    assert script.parse_releases(list(reversed(RELEASE_RECORDS))) == EXPECTED_SCRIPT_VERSIONS


def test_parse_releases_handles_empty_input(script: Any):
    """An empty API payload yields no versions instead of crashing."""
    assert script.parse_releases([]) == []


def test_format_choice_lines_quotes_versions_with_eight_space_indent(script: Any):
    """Choices must render as YAML-safe, quoted 8-space-indented mapping entries."""
    assert script.format_choice_lines(["3.14", "3.12"]) == ['        "3.14": "3.14"', '        "3.12": "3.12"']


def test_format_choice_lines_handles_empty_list(script: Any):
    """No versions means no lines (the marker block is then empty)."""
    assert script.format_choice_lines([]) == []


def test_update_copier_yaml_replaces_the_managed_block(script: Any):
    """The stale block is swapped for the new choices, leaving the rest of the YAML intact."""
    updated = script.update_copier_yaml(SAMPLE_COPIER_YAML, EXPECTED_SCRIPT_VERSIONS)

    assert updated.count(BEGIN_MARKER) == 1, f"expected one begin marker after update:\n{updated}"
    assert updated.count(END_MARKER) == 1, f"expected one end marker after update:\n{updated}"
    assert '"3.10": "3.10"' not in updated, "the stale 3.10 choice must be removed"

    parsed = yaml.safe_load(updated)
    assert list(parsed["python_version"]["choices"]) == EXPECTED_SCRIPT_VERSIONS
    assert parsed["python_version"]["choices"] == {"3.14": "3.14", "3.13": "3.13", "3.12": "3.12", "3.11": "3.11"}
    assert parsed["python_version"]["default"] == "3.11", "sibling keys must survive the rewrite"
    assert parsed["project_type"]["default"] == "package", "surrounding questions must survive the rewrite"


def test_update_copier_yaml_is_idempotent(script: Any):
    """Applying the same versions twice must produce byte-identical output."""
    once = script.update_copier_yaml(SAMPLE_COPIER_YAML, EXPECTED_SCRIPT_VERSIONS)
    twice = script.update_copier_yaml(once, EXPECTED_SCRIPT_VERSIONS)
    assert twice == once, "update_copier_yaml must be idempotent"


@pytest.mark.parametrize("marker", [BEGIN_MARKER, END_MARKER], ids=["missing-begin", "missing-end"])
def test_update_copier_yaml_rejects_missing_markers(script: Any, marker: str):
    """A missing marker means the file was hand-edited: refuse instead of guessing."""
    content = "".join(line for line in SAMPLE_COPIER_YAML.splitlines(keepends=True) if line.strip() != marker)
    assert marker not in content, "test setup failed to remove the marker"
    with pytest.raises(ValueError):
        script.update_copier_yaml(content, EXPECTED_SCRIPT_VERSIONS)


def test_main_returns_non_zero_when_markers_are_missing(script: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """`main()` reports failure and leaves unmanaged files untouched."""
    target = tmp_path / "copier.yaml"
    original = "project_name:\n    type: str\n"
    target.write_text(original)
    _stub_network(monkeypatch, script)
    monkeypatch.setattr(sys, "argv", ["update_python_versions.py", str(target)])

    assert script.main() != 0, "main() must return non-zero when the target has no marker block"
    assert target.read_text() == original, "main() must not rewrite a file it cannot manage"


def test_main_rewrites_the_target_file(script: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """`main()` fetches, filters and rewrites the path given in `sys.argv[1]`."""
    target = tmp_path / "copier.yaml"
    target.write_text(SAMPLE_COPIER_YAML)
    _stub_network(monkeypatch, script)
    monkeypatch.setattr(sys, "argv", ["update_python_versions.py", str(target)])

    assert script.main() == 0
    choices = yaml.safe_load(target.read_text())["python_version"]["choices"]
    assert list(choices) == EXPECTED_SCRIPT_VERSIONS


def test_main_rejects_missing_required_choice(script: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """A rewrite that orphans `default` must be refused, leaving the file untouched.

    Upstream dropping the `3.11` cycle would otherwise rewrite `choices` to
    `3.14`/`3.13`/`3.12` while `default` stays `3.11` — an invalid Copier question.
    """
    target = tmp_path / "copier.yaml"
    target.write_text(SAMPLE_COPIER_YAML)
    without_311 = [record for record in RELEASE_RECORDS if record["cycle"] != "3.11"]
    assert "3.11" not in [record["cycle"] for record in without_311], "test setup failed to drop the 3.11 cycle"
    _stub_network(monkeypatch, script, without_311)
    monkeypatch.setattr(sys, "argv", ["update_python_versions.py", str(target)])

    assert script.main() != 0, "main() must fail when the fetched cycles no longer include the default '3.11' choice"
    assert target.read_text() == SAMPLE_COPIER_YAML, (
        "main() must not write choices that would orphan the python_version default"
    )


def test_main_keeps_the_default_choice_in_the_written_block(
    script: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """The green twin of the guard: a payload containing 3.11 keeps it as a choice."""
    target = tmp_path / "copier.yaml"
    target.write_text(SAMPLE_COPIER_YAML)
    _stub_network(monkeypatch, script)
    monkeypatch.setattr(sys, "argv", ["update_python_versions.py", str(target)])

    assert script.main() == 0
    question = yaml.safe_load(target.read_text())["python_version"]
    assert "3.11" in question["choices"], f"the written choices must still include '3.11', got {question['choices']!r}"
    assert question["default"] in question["choices"], (
        f"python_version.default {question['default']!r} must remain one of the written choices"
    )


def test_main_reports_fetch_failure_without_touching_target(
    script: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """A network error must return non-zero and leave a marker-bearing file untouched."""
    target = tmp_path / "copier.yaml"
    target.write_text(SAMPLE_COPIER_YAML)
    _stub_network_failure(monkeypatch, script)
    monkeypatch.setattr(sys, "argv", ["update_python_versions.py", str(target)])

    assert script.main() != 0, "main() must return non-zero when the release data cannot be fetched"
    assert target.read_text() == SAMPLE_COPIER_YAML, "a failed fetch must not modify the target file"


# --------------------------------------------------------------------------- #
# Rendered projects: payload plumbing for the selected version
# --------------------------------------------------------------------------- #


def _tools(project: Path) -> dict[str, str]:
    return tomllib.loads((project / "mise.toml").read_text())["tools"]


def _pyproject(project: Path) -> dict[str, Any]:
    return tomllib.loads((project / "pyproject.toml").read_text())


def test_default_render_pins_mise_python_311(generated_basic: Path):
    """The question default must drive the generated `mise.toml` Python pin."""
    assert _tools(generated_basic)["python"] == "3.11"


def test_default_render_sets_requires_python_311(generated_basic: Path):
    """The question default must drive `requires-python`."""
    assert _pyproject(generated_basic)["project"]["requires-python"] == ">=3.11"


def test_default_render_sets_ruff_target_version_311(generated_with_ruff: Path):
    """Ruff `target-version` must track the selected Python version."""
    assert _pyproject(generated_with_ruff)["tool"]["ruff"]["target-version"] == "py311"


def test_default_render_records_python_version_answer(generated_basic: Path):
    """The answers file must capture the version so `copier update` can replay it."""
    answers = (generated_basic / ".copier-answers.yml").read_text()
    assert re.search(ANSWER_LINE.format(version=r"3\.11"), answers), (
        f"answers file lacks python_version 3.11:\n{answers}"
    )


def test_python313_render_pins_mise_python(generated_python313: Path):
    """An explicit `python_version` answer must reach the generated `mise.toml`."""
    assert _tools(generated_python313)["python"] == "3.13"


def test_python313_render_sets_requires_python(generated_python313: Path):
    """An explicit `python_version` answer must reach `requires-python`."""
    assert _pyproject(generated_python313)["project"]["requires-python"] == ">=3.13"


def test_python313_render_sets_ruff_target_version(generated_python313: Path):
    """An explicit `python_version` answer must reach Ruff `target-version`."""
    assert _pyproject(generated_python313)["tool"]["ruff"]["target-version"] == "py313"


def test_python313_render_records_python_version_answer(generated_python313: Path):
    """The answers file must record the non-default selection."""
    answers = (generated_python313 / ".copier-answers.yml").read_text()
    assert re.search(ANSWER_LINE.format(version=r"3\.13"), answers), (
        f"answers file lacks python_version 3.13:\n{answers}"
    )


# --------------------------------------------------------------------------- #
# copier update: projects generated before the question existed
# --------------------------------------------------------------------------- #


def test_update_restores_python_version_for_legacy_project(_git_template_repo: Path):
    """`copier update` must re-ask the new question and template it from the default.

    Simulates a project generated from `v1.0.0` whose answers file predates the
    `python_version` question: the answer is dropped, then the project is updated
    to `v1.0.1`, which must restore the answer and the rendered pins.
    """
    data = _make_data({"project_name": "update_proj"})
    project = _run_copy_from(_git_template_repo, data, dst_name="update", vcs_ref="v1.0.0")

    answers_path = project / ".copier-answers.yml"
    answers, dropped = re.subn(r"(?m)^python_version:.*\n", "", answers_path.read_text())
    assert dropped == 1, "the v1.0.0 render should record exactly one python_version answer to drop"
    answers_path.write_text(answers)

    with local.env(**GIT_IDENTITY):
        _git(project, "add", "-A")
        _git(project, "commit", "-m", "drop python_version answer")
        run_update(str(project), defaults=True, overwrite=True, unsafe=True)

    restored = answers_path.read_text()
    assert re.search(ANSWER_LINE.format(version=r"3\.11"), restored), (
        f"copier update must restore the python_version answer:\n{restored}"
    )
    assert _tools(project)["python"] == "3.11", "updated project must pin the default Python in mise.toml"
    assert UPDATE_MARKER in (project / "README.md").read_text(), (
        "copier update must apply the v1.0.1 template change to README.md"
    )
