"""Tests for the render variants pinned by the registry.

This module guards the render polarities the computed render-facts refactor
must preserve exactly:

- the ruff-without-pytest combo (pytest sections must not leak into a
  ruff-only render) and its mirror, pytest-without-cov (coverage sections
  must not leak into a coverage-less pytest render);
- the answers-file omission contract: hidden `when: false` computed facts
  must never be recorded in `.copier-answers.yml`.
"""

from __future__ import annotations

from pathlib import Path

import tomllib
from _mise_contract import read_mise_toml, refs, task_names
from _projects import ProjectRegistry

# The six hidden `when: false` questions in copier.yaml that compute render
# facts from the user's answers. Copier omits such questions from the
# generated answers file, so none of these may appear as YAML keys there.
COMPUTED_FACT_KEYS = (
    "is_app",
    "is_lib",
    "is_package",
    "with_ruff",
    "with_pytest",
    "with_pytest_cov",
)


def test_ruff_only_render_omits_pytest_sections(projects: ProjectRegistry) -> None:
    """A ruff-without-pytest render must keep Ruff tooling and drop pytest sections.

    This is the only variant where the Ruff and pytest conditionals diverge;
    the computed render-facts refactor must preserve this render exactly.
    """
    project = projects.render("ruff-only")

    data = read_mise_toml(project / "mise.toml")
    tasks = data["tasks"]
    names = task_names(data)

    assert {"lint:python", "format", "hooks", "doctor"} <= names
    assert names.isdisjoint({"test:unit", "test", "ci"}), (
        f"pytest-gated tasks leaked into a ruff-only render: {sorted(names)}"
    )
    assert "lint:python" in refs(tasks["lint"])

    pyproject = tomllib.loads((project / "pyproject.toml").read_text())
    assert "ruff" in pyproject["tool"]
    assert "pytest" not in pyproject["tool"]

    readme = (project / "README.md").read_text()
    assert "Code Quality" in readme
    assert "Running Tests" not in readme


def test_pytest_without_cov_render_omits_coverage_sections(projects: ProjectRegistry) -> None:
    """A pytest-without-pytest-cov render must keep pytest tooling and drop coverage sections.

    This is the mirror of the ruff-only combo: the only variant where the
    pytest and pytest-cov conditionals diverge, so the computed render-facts
    refactor cannot leak `--cov` addopts or `[tool.coverage.*]` tables into a
    coverage-less pytest render.
    """
    project = projects.render("pytest-no-cov")

    pyproject = tomllib.loads((project / "pyproject.toml").read_text())
    assert "pytest" in pyproject["tool"]
    pytest_ini = pyproject["tool"]["pytest"]
    assert "ini_options" in pytest_ini, "`[tool.pytest.ini_options]` must render when pytest is present"
    assert "coverage" not in pyproject["tool"], "coverage tooling leaked into a pytest-without-cov render"
    addopts = pytest_ini["ini_options"]["addopts"]
    assert not any(opt.startswith("--cov") for opt in addopts), (
        f"coverage addopts leaked into a pytest-without-cov render: {addopts}"
    )

    data = read_mise_toml(project / "mise.toml")
    names = task_names(data)

    assert {"test:unit", "test:integration", "test"} <= names
    assert names.isdisjoint({"lint:python", "format", "ci"}), (
        f"ruff-gated tasks leaked into a pytest-without-cov render: {sorted(names)}"
    )


def test_answers_omit_computed_render_facts(generated_basic: Path) -> None:
    """`.copier-answers.yml` must not record any hidden computed render fact.

    Copier omits `when: false` questions from the generated answers file; the
    render-facts refactor leans on that contract, so a fact leaking into the
    answers would be replayed verbatim by `copier update` instead of being
    re-derived from the user's real answers. Each fact is checked as the
    key-shaped substring `<name>:` rather than the bare name, so a sibling
    key can never trip the check for a shorter name: `"with_pytest:"` is not
    a substring of a leaked `with_pytest_cov: true` line, and that line is
    exactly what the `with_pytest_cov` assertion targets.
    """
    answers_text = (generated_basic / ".copier-answers.yml").read_text()
    for name in COMPUTED_FACT_KEYS:
        assert f"{name}:" not in answers_text, (
            f"computed fact {name!r} leaked into .copier-answers.yml:\n{answers_text}"
        )
