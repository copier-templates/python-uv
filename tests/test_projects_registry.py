"""Contract tests for the render fixture registry (`_projects.py`).

The planned refactor collapses every `conftest.py` render fixture into a
single registry module that owns the render pipeline. These tests pin the
registry's public contract with a pure, injected render function: no Copier
renders, no `conftest` import, no filesystem access.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from _projects import ALIASES, BASE_DATA, VARIANTS, ProjectRegistry

EXPECTED_VARIANTS = {
    "basic",
    "ruff",
    "ruff-only",
    "pytest-no-cov",
    "python313",
    "license",
    "license-ruff",
    "github",
    "no-github",
    "hyphenated-package",
    "app",
    "lib",
}

EXPECTED_ALIASES = {
    "generated_basic": "basic",
    "generated_with_ruff": "ruff",
    "generated_python313": "python313",
    "generated_with_license": "license",
    "generated_with_license_ruff": "license-ruff",
    "generated_with_github_integration": "github",
    "generated_without_github_integration": "no-github",
    "generated_hyphenated_package": "hyphenated-package",
    "generated_app": "app",
    "generated_library": "lib",
}

# The BASE_DATA contract the registry must preserve (today owned by
# tests/conftest.py); a registry refactor must not silently change these values.
EXPECTED_BASE_DATA: dict[str, object] = {
    "project_type": "package",
    "project_description": "Example description",
    "author_name": "Test User",
    "author_email": "test@test.com",
    "production_deps": ["httpx[http2]"],
    "dev_deps": ["pytest", "pytest-cov"],
    "github_integration": True,
}


def _recording_render_fn(
    calls: list[tuple[dict[str, object], str]],
) -> Callable[[dict[str, object], str], Path]:
    """Return a render stub that records every `(data, dst_name)` call."""

    def render_fn(data: dict[str, object], dst_name: str) -> Path:
        calls.append((data, dst_name))
        return Path(dst_name)

    return render_fn


def test_variants_table_covers_expected_names() -> None:
    """`VARIANTS` must expose exactly the twelve render variants."""
    assert set(VARIANTS.keys()) == EXPECTED_VARIANTS


def test_aliases_map_all_generated_fixtures() -> None:
    """`ALIASES` must map every generated-fixture name onto its variant."""
    assert ALIASES == EXPECTED_ALIASES


def test_base_data_is_pinned() -> None:
    """`BASE_DATA` must match the pinned contract in `EXPECTED_BASE_DATA`."""
    assert BASE_DATA == EXPECTED_BASE_DATA


def test_render_merges_base_and_variant_and_overrides() -> None:
    """`render` must layer BASE_DATA, then variant overrides, then caller overrides."""
    calls: list[tuple[dict[str, object], str]] = []
    registry = ProjectRegistry(render_fn=_recording_render_fn(calls))

    dst = registry.render("ruff", {"project_name": "custom"})

    assert dst == Path("ruff")
    assert calls == [
        ({**EXPECTED_BASE_DATA, **VARIANTS["ruff"], "project_name": "custom"}, "ruff"),
    ]


def test_render_caches_identical_calls() -> None:
    """Identical (variant, overrides) pairs must hit the render function exactly once."""
    calls: list[tuple[dict[str, object], str]] = []
    registry = ProjectRegistry(render_fn=_recording_render_fn(calls))

    first = registry.render("basic")
    second = registry.render("basic")

    assert first == Path("basic")
    assert second == first
    assert len(calls) == 1


def test_render_does_not_cache_distinct_overrides() -> None:
    """Different overrides on the same variant must each reach the render function."""
    calls: list[tuple[dict[str, object], str]] = []
    registry = ProjectRegistry(render_fn=_recording_render_fn(calls))

    registry.render("basic")
    registry.render("basic", {"include_license": True})

    assert len(calls) == 2


def test_unknown_variant_raises() -> None:
    """Rendering a variant absent from `VARIANTS` must fail loudly before rendering."""
    calls: list[tuple[dict[str, object], str]] = []
    registry = ProjectRegistry(render_fn=_recording_render_fn(calls))

    with pytest.raises((KeyError, ValueError)):
        registry.render("nonexistent")

    assert calls == []


def test_registry_requires_injected_render_fn() -> None:
    """The registry must never fall back to its own Copier render: the fn is required."""
    with pytest.raises(TypeError):
        ProjectRegistry()  # type: ignore[call-arg]
