"""Rendered project contents: expected paths, layouts, exclusions, payload, README and answers facts."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from _projects import BASE_DATA, ProjectRegistry, load_toml, run_copy_from

EXPECTED_FILES = ".copier-answers.yml .gitattributes .gitignore prek.toml cliff.toml mise.toml pyproject.toml README.md uv.lock".split()  # noqa: SIM905
EXPECTED_DIRS: list[str] = ["src", "tests"]

# With `_subdirectory: templates`, only files under `templates/` may copy; these once leaked via the root.
# `tests/` is deliberately absent: `templates/tests/` legitimately renders as the generated `tests/` package.
EXCLUDED_PATHS = ".vscode .agents .opencode .chlog .pytest_cache .pyscn docs examples hooks extensions .github/extensions src/copier_python_uv.egg-info templates licenses copier.yaml SECURITY.md AGENTS.md .env summary.md".split()  # noqa: SIM905

# Hidden `when: false` facts (and removed questions): Copier must keep them out of the answers file.
COMPUTED_FACT_KEYS = (
    "is_app is_lib is_package dev_deps dev_dep_names verify_ci with_ruff with_pytest with_pytest_cov".split()  # noqa: SIM905
)


def test_expected_files_and_dirs_exist(projects: ProjectRegistry):
    project = projects.render("basic")
    missing: list[str] = [f for f in EXPECTED_FILES if not (project.path / f).is_file()]
    missing += [d for d in EXPECTED_DIRS if not (project.path / d).is_dir()]
    assert not missing, f"Missing expected paths: {missing}"


@pytest.mark.parametrize("variant", ["basic", "lib"])
def test_generated_unit_test_has_standard_module_spacing(projects: ProjectRegistry, variant: str):
    test_file = projects.render(variant).read("tests/unit/test_init.py")
    assert re.match(r'""".*"""\n\n(from|import) ', test_file)
    assert test_file.endswith("\n") and not test_file.endswith("\n\n")


def test_package_mode_normalizes_module_name(projects: ProjectRegistry):
    """Hyphenated project names derive an underscore module package and a CLI entrypoint."""
    project = projects.render("python313-licensed")
    config = project.pyproject()["project"]
    assert project.project_name == "my-app"
    assert project.module_name == "my_app"
    assert (project.path / "src" / "my_app" / "__init__.py").is_file()
    assert config["name"] == "my-app"
    assert config["scripts"] == {"my-app": "my_app:main"}


def test_app_mode_renders_root_entrypoint_and_coverage(projects: ProjectRegistry):
    project = projects.render("app")
    config = project.pyproject()
    assert (project.path / "main.py").is_file()
    assert not (project.path / "src").exists()
    assert "scripts" not in config["project"]
    assert "build-system" not in config
    assert config["tool"]["coverage"]["run"]["source"] == ["."]
    assert "source_pkgs" not in config["tool"]["coverage"]["run"]
    assert config["tool"]["pytest"]["pythonpath"] == ["."]
    assert config["tool"]["pytest"]["testpaths"] == ["tests"]


def test_library_mode_renders_typed_package(projects: ProjectRegistry):
    project = projects.render("lib")
    config = project.pyproject()
    assert (project.path / "src" / project.module_name / "__init__.py").is_file()
    assert (project.path / "src" / project.module_name / "py.typed").is_file()
    assert "scripts" not in config["project"]
    assert config["build-system"]["build-backend"] == "uv_build"


@pytest.mark.parametrize("relpath", EXCLUDED_PATHS)
def test_excluded_paths_are_absent(projects: ProjectRegistry, relpath: str):
    """Copier may leave an empty directory behind, so an excluded directory must be absent or empty.

    Uses a files-only render: a task variant runs `mise run ci` and legitimately creates `.pytest_cache`.
    """
    path = projects.render("github").path / relpath
    assert not path.exists() or (path.is_dir() and not any(path.iterdir())), f"Excluded path present: {relpath}"


def test_payload_tests_package_is_rendered(projects: ProjectRegistry):
    project = projects.render("basic")
    missing = [
        relpath
        for relpath in ("tests/__init__.py", "tests/unit/test_init.py")
        if not (project.path / relpath).is_file()
    ]
    assert not missing, f"payload files missing from generated project: {missing}"


@pytest.mark.parametrize(("variant", "present"), [("github", True), ("extra-dev-no-github", False)])
def test_github_dir_follows_github_integration(projects: ProjectRegistry, variant: str, present: bool):
    project = projects.render(variant)
    assert (project.path / ".github" / "workflows" / "test.yml").is_file() is present
    assert (project.path / ".github").exists() is present


def test_project_name_with_leading_digit_is_rejected(template_source: Path, tmp_path: Path):
    """`123app` would render `module_name` `123app`, an invalid identifier."""
    with pytest.raises(ValueError, match="(?i)project name.*digit"):
        run_copy_from(template_source, tmp_path / "bad-name", BASE_DATA | {"project_name": "123app"})


@pytest.mark.parametrize(
    "snippet",
    [
        "Running Tests",
        "Code Quality",
        "img.shields.io/badge/mise",
        "mise.jdx.dev",
        "mise run changelog",
        "mise run release",
    ],
)
def test_readme_documents_tooling_and_workflows(projects: ProjectRegistry, snippet: str):
    assert snippet in projects.render("basic").read("README.md")


def test_generated_cliff_toml_is_valid(projects: ProjectRegistry):
    data = load_toml(projects.render("basic").path / "cliff.toml")
    assert "body" in data["changelog"]
    assert data["git"]["conventional_commits"] is True


def test_answers_omit_hidden_computed_facts(projects: ProjectRegistry):
    """A leaked computed fact would be replayed verbatim by `copier update` instead of re-derived."""
    answers = projects.render("basic").read(".copier-answers.yml")
    leaked = [name for name in COMPUTED_FACT_KEYS if re.search(rf"^{name}:", answers, re.MULTILINE)]
    assert not leaked, f"hidden computed facts leaked into answers: {leaked}\n{answers}"
