"""uv-init-aligned project type rendering."""

from __future__ import annotations

from _projects import ProjectRegistry, mise_toml, pyproject, refs


def test_package_mode_normalizes_module_name(projects: ProjectRegistry):
    """Hyphenated project names should derive an underscore module package."""
    project = projects.render("hyphenated-package")
    config = pyproject(project)["project"]

    assert (project / "src" / "my_app" / "__init__.py").is_file()
    assert config["name"] == "my-app"
    assert config["scripts"] == {"my-app": "my_app:main"}


def test_app_mode_renders_root_entrypoint_and_coverage(projects: ProjectRegistry):
    """Application mode renders a root main.py, no package tree, and coverage scoped to the root module."""
    project = projects.render("app")
    config = pyproject(project)

    assert (project / "main.py").is_file()
    assert not (project / "src").exists()
    assert "scripts" not in config["project"]
    assert "build-system" not in config
    assert config["tool"]["coverage"]["run"]["source"] == ["."]
    assert "source_pkgs" not in config["tool"]["coverage"]["run"]


def test_library_mode_renders_typed_package(projects: ProjectRegistry):
    """Library mode should render a typed package without a CLI script entrypoint."""
    project = projects.render("lib")
    config = pyproject(project)

    assert (project / "src" / "example_lib" / "__init__.py").is_file()
    assert (project / "src" / "example_lib" / "py.typed").is_file()
    assert "scripts" not in config["project"]
    assert config["build-system"]["build-backend"] == "uv_build"


def test_generated_mise_toml_contains_test_task(projects: ProjectRegistry):
    """The generated mise.toml must split pytest into unit/integration tasks aggregated by `test`."""
    tasks = mise_toml(projects.render("app"))["tasks"]

    assert "uv run pytest tests/unit/" in tasks["test:unit"]["run"]
    assert "uv run pytest tests/integration/" in tasks["test:integration"]["run"]
    assert refs(tasks["test"]) == ["test:unit", "test:integration"]


def test_generated_mise_toml_integration_task_tolerates_missing_directory(projects: ProjectRegistry):
    """`test:integration` must skip gracefully: generated projects ship no tests/integration/ dir."""
    project = projects.render("app")
    mise_text = (project / "mise.toml").read_text()

    assert not (project / "tests" / "integration").exists(), "PRD: no new scaffold directories"
    assert "[[ -d tests/integration ]]" in mise_text, (
        "test:integration must guard on the directory, otherwise pytest exits 4 in a fresh project"
    )
