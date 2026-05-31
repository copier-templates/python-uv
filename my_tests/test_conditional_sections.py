"""Tests for conditional README sections and dependency-driven rendering."""

from __future__ import annotations

from pathlib import Path

import tomllib


def test_readme_includes_tests_section_when_pytest(generated_basic: Path):
    readme = (generated_basic / "README.md").read_text()
    assert "Running Tests" in readme


def test_readme_includes_ruff_section_only_when_present(generated_with_ruff: Path):
    readme = (generated_with_ruff / "README.md").read_text()
    assert "Code Quality" in readme


def test_readme_excludes_ruff_section_when_not_selected(generated_basic: Path):
    readme = (generated_basic / "README.md").read_text()
    assert "Code Quality" not in readme


def test_pyproject_includes_license_field_when_selected(generated_with_license: Path):
    """Verify pyproject.toml includes license field when license is selected."""
    pyproject = (generated_with_license / "pyproject.toml").read_text()
    assert 'license = "MIT"' in pyproject, "pyproject.toml should include license field"


def test_pyproject_includes_license_files_when_license_selected(generated_with_license: Path):
    """Verify pyproject.toml includes license-files field when license is selected."""
    pyproject = (generated_with_license / "pyproject.toml").read_text()
    assert 'license-files = ["LICENSE"]' in pyproject, "pyproject.toml should include license-files field"


def test_pyproject_omits_license_field_when_not_selected(generated_basic: Path):
    """Verify pyproject.toml omits license field when license is not selected."""
    pyproject = (generated_basic / "pyproject.toml").read_text()
    assert "license =" not in pyproject, "pyproject.toml should not include license field when no license selected"
    assert "license-files" not in pyproject, "pyproject.toml should not include license-files when no license selected"


def test_mise_toml_is_valid_toml_with_ruff(generated_with_ruff: Path):
    """Generated mise.toml must be valid TOML when ruff is in dev_deps."""
    content = (generated_with_ruff / "mise.toml").read_text()
    data = tomllib.loads(content)
    assert "tasks" in data
    assert "lint" in data["tasks"]
    assert "format" in data["tasks"]
    assert "unit" in data["tasks"]
    assert "test" in data["tasks"]
    assert "ci" in data["tasks"]
    assert data["env"]["_"]["file"] == ".env"
    assert data["tasks"]["format"].get("depends") == ["lint"]
    assert data["tasks"]["unit"].get("depends") == ["clean", "lint"]
    assert data["tasks"]["test"].get("depends") == ["clean", "lint"]
    assert data["tasks"]["ci"].get("depends") == ["lint", "unit", "format"]


def test_mise_toml_is_valid_toml_without_ruff(generated_basic: Path):
    """Generated mise.toml must be valid TOML when ruff is NOT in dev_deps."""
    content = (generated_basic / "mise.toml").read_text()
    data = tomllib.loads(content)
    assert "tasks" in data
    assert "lint" not in data["tasks"]
    assert "format" not in data["tasks"]
    assert "ci" not in data["tasks"]
    assert "unit" in data["tasks"]
    assert "test" in data["tasks"]
    assert data["env"]["_"]["file"] == ".env"
    assert data["tasks"]["unit"].get("depends") == ["clean"]
    assert data["tasks"]["test"].get("depends") == ["clean"]


def test_mise_toml_lint_task_runs_ruff_fix(generated_with_ruff: Path):
    """Lint and format tasks should be split for Ruff projects."""
    content = (generated_with_ruff / "mise.toml").read_text()
    data = tomllib.loads(content)
    lint_run = data["tasks"]["lint"]["run"]
    format_run = data["tasks"]["format"]["run"]
    assert "ruff check --fix" in lint_run
    assert "ruff format" not in lint_run
    assert format_run == "uv run ruff format ."


def test_pyproject_configures_ruff_rules_for_generated_projects(generated_with_ruff: Path):
    """Generated pyproject.toml should include the expanded Ruff config."""
    pyproject = tomllib.loads((generated_with_ruff / "pyproject.toml").read_text())
    lint = pyproject["tool"]["ruff"]["lint"]

    assert {
        "E",
        "W",
        "F",
        "I",
        "Q",
        "B",
        "C4",
        "C90",
        "SIM",
        "DTZ",
        "ARG",
        "PLE",
        "PLW",
        "PLC",
        "UP",
        "S",
    }.issubset(set(lint["select"]))
    assert lint["per-file-ignores"]["tests/unit/**/*.py"] == ["ARG001"]
    assert lint["per-file-ignores"]["tests/**/*.py"] == ["S101", "S105", "S106"]
    assert lint["isort"]["known-first-party"] == ["ruff_proj"]


def test_pyproject_registers_markers_and_package_coverage(generated_with_ruff: Path):
    """Generated packaged projects should register markers and use source_pkgs coverage."""
    pyproject = tomllib.loads((generated_with_ruff / "pyproject.toml").read_text())
    pytest_options = pyproject["tool"]["pytest"]["ini_options"]
    coverage_run = pyproject["tool"]["coverage"]["run"]

    assert pytest_options["markers"] == [
        "unit: marks tests as unit tests",
        "integration: marks tests as integration tests",
    ]
    assert coverage_run["source_pkgs"] == ["ruff_proj"]
    assert "source" not in coverage_run
