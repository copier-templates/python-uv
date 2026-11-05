"""Render polarities of the computed render facts, and the answers-file omission contract."""

from __future__ import annotations

from _projects import ProjectRegistry, mise_toml, pyproject, refs

# Hidden `when: false` facts in copier.yaml: Copier must keep them out of the answers file.
COMPUTED_FACT_KEYS = (
    "is_app",
    "is_lib",
    "is_package",
    "verify_ci",
    "with_ruff",
    "with_pytest",
    "with_pytest_cov",
)


def test_ruff_only_render_omits_pytest_sections(projects: ProjectRegistry) -> None:
    """A ruff-without-pytest render must keep Ruff tooling and drop pytest sections."""
    project = projects.render("ruff-only")

    tasks = mise_toml(project)["tasks"]
    assert {"lint:python", "format", "hooks", "doctor"} <= set(tasks)
    assert set(tasks).isdisjoint({"test:unit", "test", "ci"}), f"pytest-gated tasks leaked: {sorted(tasks)}"
    assert "lint:python" in refs(tasks["lint"])

    tool = pyproject(project)["tool"]
    assert "ruff" in tool
    assert "pytest" not in tool

    readme = (project / "README.md").read_text()
    assert "Code Quality" in readme
    assert "Running Tests" not in readme


def test_pytest_without_cov_render_omits_coverage_sections(projects: ProjectRegistry) -> None:
    """A pytest-without-pytest-cov render must keep pytest tooling and drop coverage sections."""
    project = projects.render("pytest-no-cov")

    tool = pyproject(project)["tool"]
    assert "ini_options" in tool["pytest"], "`[tool.pytest.ini_options]` must render when pytest is present"
    assert "coverage" not in tool, "coverage tooling leaked into a pytest-without-cov render"
    addopts = tool["pytest"]["ini_options"]["addopts"]
    assert not any(opt.startswith("--cov") for opt in addopts), f"coverage addopts leaked: {addopts}"

    names = set(mise_toml(project)["tasks"])
    assert {"test:unit", "test:integration", "test"} <= names
    assert names.isdisjoint({"lint:python", "format", "ci"}), f"ruff-gated tasks leaked: {sorted(names)}"


def test_answers_omit_computed_render_facts(projects: ProjectRegistry) -> None:
    """`.copier-answers.yml` must not record any hidden computed render fact.

    A leaked fact would be replayed verbatim by `copier update` instead of being re-derived.
    Facts are matched as `<name>:` so `with_pytest:` cannot trip on a leaked `with_pytest_cov:` line.
    """
    answers_text = (projects.render("basic") / ".copier-answers.yml").read_text()
    for name in COMPUTED_FACT_KEYS:
        assert f"{name}:" not in answers_text, f"computed fact {name!r} leaked into answers:\n{answers_text}"


def test_pinned_dev_deps_still_enable_tooling(projects: ProjectRegistry) -> None:
    """Specifiers, extras and non-canonical names (PEP 503) must not disable the tooling facts."""
    project = projects.render("pinned-dev-deps")

    tool = pyproject(project)["tool"]
    assert "ruff" in tool
    addopts = tool["pytest"]["ini_options"]["addopts"]
    assert any(opt.startswith("--cov=") for opt in addopts), f"missing --cov= in addopts: {addopts}"
    assert "run" in tool["coverage"]

    assert "ci" in mise_toml(project)["tasks"]
