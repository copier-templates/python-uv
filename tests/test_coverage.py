"""Unit test runs must show a code coverage report (pytest-cov via addopts)."""

from __future__ import annotations

import tomllib
from pathlib import Path

TEMPLATE_ROOT = Path(__file__).resolve().parent.parent


def _root_pyproject() -> dict:
    return tomllib.loads((TEMPLATE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_test_runs_report_coverage():
    """Root pytest addopts must enable coverage over scripts (incl. maintainer), tasks and the release module."""
    addopts = _root_pyproject()["tool"]["pytest"]["ini_options"]["addopts"]
    assert "--cov=scripts" in addopts
    assert "--cov=scripts/maintainer" in addopts
    assert "--cov=tasks" in addopts
    assert "--cov=templates/scripts" in addopts
    assert "--cov-report=term-missing" in addopts


def test_coverage_config_uses_branch():
    """Branch coverage must be enabled for the report."""
    assert _root_pyproject()["tool"]["coverage"]["run"]["branch"] is True
