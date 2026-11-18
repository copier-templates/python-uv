"""Rendered pyproject contracts: always-on tooling, pytest, coverage, ty, ruff and section spacing."""

from __future__ import annotations

import re
from typing import cast

import pytest
from _projects import ProjectRegistry

# A new top-level section starts a TOML table header or a bare key following conditional content in [project].
_SECTION_START_RE = re.compile(r"^(?:\[|classifiers = \[|dependencies = \[|license = )")

ALWAYS_ON_DEV = ["pytest>=9,<10", "pytest-cov", "ruff", "ty>=0.0.34"]


@pytest.mark.parametrize("variant", ["basic", "extra-dev-no-github"])
def test_always_on_python_tooling_is_rendered(projects: ProjectRegistry, variant: str):
    """pytest, coverage, ruff and ty always ship in order; extra dev deps append without replacing them."""
    project = projects.render(variant)
    config = project.pyproject()
    production_deps = list(cast("list[str]", project.answer("production_deps")))
    extra_dev = list(cast("list[str]", project.answer("extra_dev_deps")))
    assert config["dependency-groups"]["dev"] == [*ALWAYS_ON_DEV, *extra_dev]
    assert {"pytest", "coverage", "ruff", "ty"} <= set(config["tool"])
    assert any(opt.startswith("--cov=") for opt in config["tool"]["pytest"]["addopts"])
    assert config["tool"]["coverage"]["report"]["fail_under"] == 98
    assert config["project"]["dependencies"] == production_deps


def test_pytest_uses_native_strict_table_for_package_layout(projects: ProjectRegistry):
    """pytest 9 rejects a pyproject that declares both `[tool.pytest]` and `[tool.pytest.ini_options]`."""
    table = projects.render("basic").pyproject()["tool"]["pytest"]
    assert "ini_options" not in table
    assert table["strict"] is True
    assert "--import-mode=importlib" in table["addopts"]
    assert table["testpaths"] == ["tests"]
    assert table["pythonpath"] == ["src"]
    assert table["markers"] == ["unit: marks tests as unit tests", "integration: marks tests as integration tests"]


def test_package_coverage_scopes_to_module(projects: ProjectRegistry):
    project = projects.render("basic")
    coverage = project.pyproject()["tool"]["coverage"]["run"]
    assert coverage["source_pkgs"] == [project.module_name]
    assert "source" not in coverage


@pytest.mark.parametrize(("variant", "include"), [("basic", ["src", "tests"]), ("app", ["main.py", "tests"])])
def test_ty_config_is_strict_and_follows_layout(projects: ProjectRegistry, variant: str, include: list[str]):
    """ty rejects legacy rule names as `renamed-rule` warnings, which `error-on-warning` turns into a failure."""
    ty = projects.render(variant).pyproject()["tool"]["ty"]
    assert ty["src"]["include"] == include
    assert ty["terminal"]["error-on-warning"] is True
    assert ty["rules"]["unsound-return"] == "error"
    assert "unsound-return-statement" not in ty["rules"]
    assert set(ty["rules"].values()) == {"error"}


def test_ruff_rule_set_and_layout(projects: ProjectRegistry):
    project = projects.render("basic")
    ruff = project.pyproject()["tool"]["ruff"]
    lint = ruff["lint"]
    assert ruff["line-length"] == 160
    assert set(lint["select"]) >= set(
        "E W F I Q B C4 C90 SIM DTZ ARG PLE PLW PLC UP S RUF PTH BLE G PGH003 ANN201 ANN202 ANN204".split()  # noqa: SIM905
    )
    assert {"RUF001", "RUF002", "RUF003", "G004"} <= set(lint["ignore"])
    assert lint["per-file-ignores"]["tests/unit/**/*.py"] == ["ARG001"]
    assert lint["per-file-ignores"]["tests/**/*.py"] == ["S101", "S105", "S106", "ANN"]
    assert lint["isort"]["known-first-party"] == [project.module_name]


@pytest.mark.parametrize("variant", ["basic", "app", "lib", "python313-licensed"])
def test_pyproject_sections_are_blank_line_separated(projects: ProjectRegistry, variant: str):
    """Every conditional block keeps a blank line before the next top-level section."""
    lines = projects.render(variant).read("pyproject.toml").splitlines()
    offenders = [i + 1 for i, line in enumerate(lines) if i and _SECTION_START_RE.match(line) and lines[i - 1].strip()]
    assert not offenders, f"{variant}: pyproject sections missing a preceding blank line at lines {offenders}"
