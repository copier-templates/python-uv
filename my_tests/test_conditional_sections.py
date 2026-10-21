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


def test_readme_includes_mise_badge(generated_basic: Path):
    readme = (generated_basic / "README.md").read_text()
    assert "img.shields.io/badge/mise" in readme
    assert "mise.jdx.dev" in readme


def test_readme_excludes_ruff_section_when_not_selected(generated_basic: Path):
    readme = (generated_basic / "README.md").read_text()
    assert "Code Quality" not in readme


def test_pyproject_preserves_httpx_http2_production_dependency(generated_basic: Path):
    """Generated pyproject.toml should keep the HTTP/2-enabled httpx dependency example."""
    pyproject = tomllib.loads((generated_basic / "pyproject.toml").read_text())
    assert pyproject["project"]["dependencies"] == ["httpx[http2]"]


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
    assert "lint:python" in data["tasks"]
    assert "lint:shell" in data["tasks"]
    assert "fix:python" in data["tasks"]
    assert "lint:workflows" in data["tasks"]
    assert "format" in data["tasks"]
    assert "format:check" in data["tasks"]
    assert "fix" in data["tasks"]
    assert "hooks" in data["tasks"]
    assert "unit" in data["tasks"]
    assert "test" in data["tasks"]
    assert "ci" in data["tasks"]
    assert "verify" in data["tasks"]
    assert "doctor" in data["tasks"]
    assert "bootstrap" in data["tasks"]
    assert "ci:act" in data["tasks"]
    assert "changelog" in data["tasks"]
    assert "clean" in data["tasks"]
    assert "clean:all" in data["tasks"]
    assert data["env"]["_"]["file"] == ".env"
    assert data["tasks"]["lint"].get("depends") == ["lint:python", "lint:shell", "lint:workflows"]
    assert "depends" not in data["tasks"]["format"]
    assert "depends" not in data["tasks"]["format:check"]
    assert "depends" not in data["tasks"]["unit"]
    assert "depends" not in data["tasks"]["test"]
    assert "depends" not in data["tasks"]["ci"]


def test_mise_toml_ci_runs_ordered_readonly_steps(generated_with_ruff: Path):
    """CI must run lint, format:check, hooks, unit in order via run steps."""
    data = tomllib.loads((generated_with_ruff / "mise.toml").read_text())
    ci_run = data["tasks"]["ci"]["run"]
    assert isinstance(ci_run, list)
    step_tasks = [step["task"] for step in ci_run if isinstance(step, dict) and "task" in step]
    assert step_tasks == ["lint", "format:check", "hooks", "unit"]
    assert data["tasks"]["ci"].get("env", {}).get("CI") == "true"
    verify_run = data["tasks"]["verify"]["run"]
    verify_steps = [step["task"] for step in verify_run if isinstance(step, dict) and "task" in step]
    assert verify_steps == ["lint", "format:check", "hooks", "test"]


def test_mise_toml_is_valid_toml_without_ruff(generated_basic: Path):
    """Generated mise.toml must be valid TOML when ruff is NOT in dev_deps."""
    content = (generated_basic / "mise.toml").read_text()
    data = tomllib.loads(content)
    assert "tasks" in data
    assert "lint" in data["tasks"]
    assert "lint:python" not in data["tasks"]
    assert "lint:shell" in data["tasks"]
    assert "lint:workflows" in data["tasks"]
    assert data["tasks"]["lint"].get("depends") == ["lint:shell", "lint:workflows"]
    assert "fix:python" not in data["tasks"]
    assert "format" not in data["tasks"]
    assert "format:check" not in data["tasks"]
    assert "fix" not in data["tasks"]
    assert "ci" not in data["tasks"]
    assert "verify" not in data["tasks"]
    assert "hooks" in data["tasks"]
    assert "doctor" in data["tasks"]
    assert "bootstrap" in data["tasks"]
    assert "ci:act" in data["tasks"]
    assert "changelog" in data["tasks"]
    assert "clean" in data["tasks"]
    assert "clean:all" in data["tasks"]
    assert "unit" in data["tasks"]
    assert "test" in data["tasks"]
    assert data["env"]["_"]["file"] == ".env"
    assert "depends" not in data["tasks"]["unit"]
    assert "depends" not in data["tasks"]["test"]


def test_mise_toml_lint_is_check_only_and_fix_task_mutates(generated_with_ruff: Path):
    """Lint must be check-only for CI; mutation lives in fix tasks."""
    content = (generated_with_ruff / "mise.toml").read_text()
    data = tomllib.loads(content)
    lint_run = data["tasks"]["lint:python"]["run"]
    fix_run = data["tasks"]["fix:python"]["run"]
    format_run = data["tasks"]["format"]["run"]
    format_check_run = data["tasks"]["format:check"]["run"]
    assert lint_run == "uv run ruff check ."
    assert "--fix" not in lint_run
    assert "ruff format" not in lint_run
    assert "ruff check --fix" in fix_run
    assert format_run == "uv run ruff format ."
    assert format_check_run == "uv run ruff format --check ."


def test_mise_toml_shell_lint_covers_all_scripts(generated_with_ruff: Path):
    """Shell lint task must discover *.sh files and run shellcheck on them."""
    content = (generated_with_ruff / "mise.toml").read_text()
    data = tomllib.loads(content)
    shell_run = data["tasks"]["lint:shell"]["run"]
    assert "shellcheck" in shell_run
    assert "*.sh" in shell_run
    assert "((" in shell_run, "mise shell tasks must use modern (( )) arithmetic tests"


def test_mise_toml_uses_modern_bash(generated_with_ruff: Path):
    """Rendered mise tasks must use modern bash, not legacy POSIX tests."""
    content = (generated_with_ruff / "mise.toml").read_text()
    assert "#!/usr/bin/env bash" in content
    assert "if [ " not in content
    assert "while [ " not in content


def test_mise_toml_pins_prek_tool(generated_basic: Path):
    """Generated mise.toml must pin prek so hooks run from mise."""
    data = tomllib.loads((generated_basic / "mise.toml").read_text())
    assert data["tools"]["prek"] == "0.5.6"


def test_mise_toml_pins_local_cicd_tools(generated_with_ruff: Path):
    """Generated mise.toml must pin act/actionlint/git-cliff for local CI/CD."""
    data = tomllib.loads((generated_with_ruff / "mise.toml").read_text())
    assert data["tools"]["act"] == "0.2"
    assert data["tools"]["actionlint"] == "1.7"
    assert data["tools"]["git-cliff"] == "2.13"


def test_mise_toml_agent_entrypoints(generated_with_ruff: Path):
    """Generated projects must expose doctor/bootstrap/hooks/verify/clean:all."""
    data = tomllib.loads((generated_with_ruff / "mise.toml").read_text())
    bootstrap_run = data["tasks"]["bootstrap"]["run"]
    bootstrap_steps = [step["task"] for step in bootstrap_run if isinstance(step, dict) and "task" in step]
    assert bootstrap_steps == ["install", "doctor"]
    assert bootstrap_run[0] == "mise trust"
    assert "mise doctor" in data["tasks"]["doctor"]["run"]
    assert "prek run --all-files" in data["tasks"]["hooks"]["run"]
    assert "act push -j test" in data["tasks"]["ci:act"]["run"]
    assert "git-cliff" in data["tasks"]["changelog"]["run"]
    assert ".venv/" in data["tasks"]["clean:all"]["run"]
    assert ".venv/" not in data["tasks"]["clean"]["run"]


def test_mise_toml_workflows_lint_skips_without_github(generated_without_github_integration: Path):
    """Workflow lint must skip gracefully when github_integration is disabled."""
    content = (generated_without_github_integration / "mise.toml").read_text()
    data = tomllib.loads(content)
    assert "lint:workflows" in data["tasks"]
    run = data["tasks"]["lint:workflows"]["run"]
    assert "[[ -d .github/workflows ]]" in run
    assert "No workflows found, skipping." in run
    assert not (generated_without_github_integration / ".github").exists()


def test_mise_toml_workflows_lint_uses_modern_bash(generated_with_ruff: Path):
    """Workflow lint guard must use modern bash, not legacy POSIX tests."""
    content = (generated_with_ruff / "mise.toml").read_text()
    assert "if [ " not in content
    assert "[[ -d .github/workflows ]]" in content


def test_mise_toml_install_runs_mise_prek(generated_basic: Path):
    """Install task must assume the mise-provided prek (no command -v guard)."""
    data = tomllib.loads((generated_basic / "mise.toml").read_text())
    install_run = data["tasks"]["install"]["run"]
    assert "uv sync" in install_run
    assert "prek install --force" in install_run
    assert "command -v" not in install_run


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


def test_template_examples_prefer_httpx_http2():
    """Template examples should steer users toward the HTTP/2-enabled httpx package."""
    template_root = Path(__file__).resolve().parents[1]
    copier_config = (template_root / "copier.yaml").read_text()
    example_config = (template_root / "examples" / "config-basic.yml").read_text()

    assert "httpx[http2]" in copier_config
    assert "requests" not in copier_config
    assert 'production_deps: ["httpx[http2]"]' in example_config


def _assert_blank_line_between_sections(pyproject_path: Path):
    """Every TOML section header must be preceded by at least one empty line."""
    lines = pyproject_path.read_text().splitlines()
    assert lines, "pyproject.toml should not be empty"
    assert lines[0].startswith("["), "pyproject.toml should start with a section header"
    for idx, line in enumerate(lines):
        if line.startswith("[") and idx > 0:
            assert lines[idx - 1] == "", (
                f"missing empty line before section {line!r} (line {idx + 1}): previous line was {lines[idx - 1]!r}"
            )


def test_pyproject_has_blank_line_between_sections(generated_basic: Path):
    """Regression test: generated pyproject.toml must separate sections with empty lines."""
    _assert_blank_line_between_sections(generated_basic / "pyproject.toml")


def test_pyproject_with_ruff_has_blank_line_between_sections(generated_with_ruff: Path):
    """Regression test: Ruff sections must also be separated by empty lines."""
    _assert_blank_line_between_sections(generated_with_ruff / "pyproject.toml")


def test_pyproject_app_has_blank_line_between_sections(generated_app: Path):
    """Regression test: app projects (skipped sections) must keep empty lines."""
    _assert_blank_line_between_sections(generated_app / "pyproject.toml")


def test_pyproject_library_has_blank_line_between_sections(generated_library: Path):
    """Regression test: library projects (skipped scripts) must keep empty lines."""
    _assert_blank_line_between_sections(generated_library / "pyproject.toml")
