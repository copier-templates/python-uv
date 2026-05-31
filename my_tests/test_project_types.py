"""Tests for uv-init-aligned project type rendering."""

from __future__ import annotations

from pathlib import Path


def test_package_mode_normalizes_module_name(generated_hyphenated_package: Path):
    """Hyphenated project names should derive an underscore module package."""
    pyproject = (generated_hyphenated_package / "pyproject.toml").read_text()

    assert (generated_hyphenated_package / "src" / "my_app" / "__init__.py").is_file()
    assert 'name = "my-app"' in pyproject
    assert '[project.scripts]\nmy-app = "my_app:main"' in pyproject


def test_app_mode_renders_root_entrypoint(generated_app: Path):
    """Application mode should render a root main.py instead of a package tree."""
    pyproject = (generated_app / "pyproject.toml").read_text()

    assert (generated_app / "main.py").is_file()
    assert not (generated_app / "src").exists()
    assert "[project.scripts]" not in pyproject
    assert "[build-system]" not in pyproject


def test_library_mode_renders_typed_package(generated_library: Path):
    """Library mode should render a typed package without a CLI script entrypoint."""
    pyproject = (generated_library / "pyproject.toml").read_text()

    assert (generated_library / "src" / "example_lib" / "__init__.py").is_file()
    assert (generated_library / "src" / "example_lib" / "py.typed").is_file()
    assert "[project.scripts]" not in pyproject
    assert 'build-backend = "uv_build"' in pyproject


def test_generated_mise_toml_contains_test_task(generated_app: Path):
    """The generated mise.toml must define a test task that runs pytest."""
    mise_toml = (generated_app / "mise.toml").read_text()

    assert "uv run pytest tests/unit/" in mise_toml
    assert "[tasks.test]" in mise_toml
    assert "[tasks.unit]" in mise_toml


def test_app_mode_keeps_app_coverage_source(generated_app: Path):
    """Application mode should keep coverage scoped to the root module entrypoint."""
    pyproject = (generated_app / "pyproject.toml").read_text()

    assert 'source = ["."]' in pyproject
    assert "source_pkgs" not in pyproject
