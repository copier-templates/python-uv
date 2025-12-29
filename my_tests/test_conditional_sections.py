"""Tests for conditional README sections and dependency-driven rendering."""

from __future__ import annotations

from pathlib import Path


def test_readme_includes_tests_section_when_pytest(generated_basic: Path):
    readme = (generated_basic / "README.md").read_text()
    assert "Running Tests" in readme


def test_readme_includes_ruff_section_only_when_present(generated_with_ruff: Path):
    readme = (generated_with_ruff / "README.md").read_text()
    assert "Code Quality" in readme


def test_readme_excludes_ruff_section_when_not_selected(generated_basic: Path):
    readme = (generated_basic / "README.md").read_text()
    assert "Code Quality" not in readme


def test_readme_includes_pytest_badge_when_pytest_in_dev_deps(generated_basic: Path):
    """Badge for pytest should appear when pytest is in dev_deps."""
    readme = (generated_basic / "README.md").read_text()
    assert "pytest" in readme and "badge" in readme.lower()


def test_readme_includes_ruff_badge_when_ruff_in_dev_deps(generated_with_ruff: Path):
    """Badge for ruff should appear when ruff is in dev_deps."""
    readme = (generated_with_ruff / "README.md").read_text()
    assert "ruff" in readme and "badge" in readme.lower()


def test_readme_excludes_ruff_badge_when_not_in_dev_deps(generated_basic: Path):
    """Badge for ruff should NOT appear when ruff is not in dev_deps."""
    readme = (generated_basic / "README.md").read_text()
    # Check that ruff badge does not exist (but ruff word might appear in text)
    assert "[![ruff" not in readme and "ruff-enabled-black" not in readme


def test_readme_includes_license_badge_when_license_included(generated_with_license: Path):
    """Badge for license should appear when include_license is true."""
    readme = (generated_with_license / "README.md").read_text()
    assert "License" in readme and "badge" in readme.lower()
    assert "LICENSE" in readme or "license" in readme


def test_readme_excludes_license_badge_when_not_included(generated_basic: Path):
    """Badge for license should NOT appear when include_license is false."""
    readme = (generated_basic / "README.md").read_text()
    # Should not have a license badge link
    assert "[![License" not in readme or "github/license" not in readme


def test_readme_badges_appear_on_same_line(generated_with_ruff: Path):
    """All badges should appear on consecutive lines without blank lines between them."""
    readme = (generated_with_ruff / "README.md").read_text()
    lines = readme.split("\n")

    # Extract just the badges section
    start_idx = None
    end_idx = None
    for i, line in enumerate(lines):
        if '<div align="center">' in line:
            start_idx = i
        elif start_idx is not None and line.startswith("#"):
            end_idx = i
            break

    assert start_idx is not None, "Could not find badge section start"
    assert end_idx is not None, "Could not find badge section end"

    # Get the badges section
    badge_section = lines[start_idx:end_idx]

    # Find all badge lines (non-empty lines with [![)
    badge_lines = [line for line in badge_section if "[![" in line]

    # Verify we have multiple badges
    assert len(badge_lines) >= 2, f"Expected at least 2 badges, got {len(badge_lines)}"

    # Now check that badges are not separated by blank lines in the original section
    # Count consecutive badge lines - they should all be together with minimal spacing
    badge_line_indices = []
    for i, line in enumerate(badge_section):
        if "[![" in line:
            badge_line_indices.append(i)

    # Check max gap between consecutive badge lines
    max_gap = 0
    for i in range(len(badge_line_indices) - 1):
        gap = badge_line_indices[i + 1] - badge_line_indices[i]
        max_gap = max(max_gap, gap)

    # Gap should be 1 (consecutive) or at most 2 (with one blank line) - we want 1
    assert max_gap == 1, f"Badges should be on consecutive lines, but gap is {max_gap}"
