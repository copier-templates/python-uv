"""Render pipeline and project registry behind the `conftest.py` fixtures.

This module owns everything that renders the template working tree for the
test suite: the snapshot copy, the Copier render helpers, the per-variant
answer tables, and a session-scoped registry that renders each
`(variant, overrides)` pair exactly once and caches the result.

`conftest.py` imports from here and re-exports what test modules import, so
this module must never import `conftest` back. The leading underscore keeps
pytest from collecting it as a test module.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from copier import run_copy
from plumbum import local

# Module-level constant: computed once at import time, not repeatedly during tests
TEMPLATE_ROOT = Path(__file__).resolve().parents[1]

# Module-level constant: git identity used for every fixture commit (no global config needed)
GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "Copier Tests",
    "GIT_AUTHOR_EMAIL": "copier-tests@example.com",
    "GIT_COMMITTER_NAME": "Copier Tests",
    "GIT_COMMITTER_EMAIL": "copier-tests@example.com",
}


def _snapshot_template_root() -> Path:
    """Copy the current working tree to a temporary non-git directory for Copier tests."""
    snapshot_root = Path(tempfile.mkdtemp(prefix="copier-template-src-")) / "template"
    shutil.copytree(
        TEMPLATE_ROOT,
        snapshot_root,
        ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"),
    )
    return snapshot_root


TEMPLATE_SOURCE = _snapshot_template_root()

# Base data and small helper to produce test data with overrides
BASE_DATA: dict[str, object] = {
    "project_type": "package",
    "project_description": "Example description",
    "author_name": "Test User",
    "author_email": "test@test.com",
    "production_deps": ["httpx[http2]"],
    "dev_deps": ["pytest", "pytest-cov"],
    "github_integration": True,
}


def _make_data(overrides: dict[str, object]) -> dict[str, object]:
    """Return a copy of BASE_DATA merged with overrides."""
    return BASE_DATA | overrides


def _run_copy_from(
    source: Path,
    data: dict[str, object],
    dst_name: str = "_generated",
    vcs_ref: str | None = None,
) -> Path:
    """Render `source` with Copier into a fresh temp dir, optionally pinned to `vcs_ref`."""
    # Resolve the destination: on macOS `mkdtemp` returns `/var/...` while git
    # reports `/private/var/...`, which breaks Copier's `update` path math.
    dst_dir = Path(tempfile.mkdtemp(prefix=f"copier-template-test-{dst_name}-")).resolve()
    extra: dict[str, object] = {"vcs_ref": vcs_ref} if vcs_ref is not None else {}
    with local.env(**GIT_IDENTITY):
        run_copy(
            str(source),
            str(dst_dir),
            data=data,
            defaults=True,
            overwrite=True,
            unsafe=True,
            **extra,
        )
    return dst_dir


def _run_copy(data: dict[str, object], dst_name: str = "_generated") -> Path:
    """Render the working-tree snapshot of this template (`TEMPLATE_SOURCE`)."""
    return _run_copy_from(TEMPLATE_SOURCE, data, dst_name=dst_name)


# Per-variant answers layered over BASE_DATA. One entry per generated-fixture
# family in conftest.py; each comment explains why the variant exists.
VARIANTS: dict[str, dict[str, object]] = {
    # The default package render: exercises the full default answer set.
    "basic": {"project_name": "example_proj"},
    # Ruff added to dev_deps so the Ruff sections of pyproject.toml and the
    # Ruff-driven mise tasks render.
    "ruff": {
        "project_name": "ruff_proj",
        "production_deps": [],
        "dev_deps": ["pytest", "pytest-cov", "ruff"],
    },
    # Ruff without pytest: the only variant where the Ruff-gated sections
    # render while every pytest-gated section is skipped, so the computed
    # render-facts refactor cannot leak pytest tasks into a ruff-only render.
    "ruff-only": {
        "project_name": "ruff_only_proj",
        "production_deps": [],
        "dev_deps": ["ruff"],
    },
    # Pytest without pytest-cov: the mirror of "ruff-only" — the only variant
    # where the pytest-gated sections render while every coverage-gated
    # section is skipped, so the computed render-facts refactor cannot leak
    # --cov addopts or [tool.coverage] into a coverage-less pytest render.
    "pytest-no-cov": {
        "project_name": "pytest_nocov_proj",
        "production_deps": [],
        "dev_deps": ["pytest"],
    },
    # Python pinned to 3.13. Ruff is included in `dev_deps` so the rendered
    # `[tool.ruff] target-version` reflects the selected Python version
    # instead of being absent.
    "python313": {
        "project_name": "py313_proj",
        "python_version": "3.13",
        "production_deps": [],
        "dev_deps": ["pytest", "pytest-cov", "ruff"],
    },
    # License selected: renders the LICENSE file and the license fields.
    "license": {
        "project_name": "license_proj",
        "include_license": True,
        "license_type": "mit",
    },
    # Licensed project with Ruff, so copy tasks run hooks on a rendered
    # LICENSE. No other variant combines `include_license` with `ruff`:
    # without this, `mise run ci` (and its `end-of-file-fixer` hook) never
    # executes against a rendered LICENSE, which is how the
    # trailing-blank-line regression escaped.
    "license-ruff": {
        "project_name": "license_ruff_proj",
        "include_license": True,
        "license_type": "mit",
        "production_deps": [],
        "dev_deps": ["pytest", "pytest-cov", "ruff"],
    },
    # GitHub integration enabled explicitly: renders the .github/ workflows.
    "github": {
        "project_name": "github_proj",
        "github_integration": True,
    },
    # GitHub integration disabled explicitly: .github/ must not render.
    "no-github": {
        "project_name": "no_github_proj",
        "github_integration": False,
    },
    # Hyphenated distribution name: the package name must normalize to my_app.
    "hyphenated-package": {
        "project_name": "my-app",
        "project_type": "package",
    },
    # Application project type: renders a root entrypoint instead of src/.
    "app": {
        "project_name": "console_app",
        "project_type": "app",
    },
    # Library project type: renders a typed src layout.
    "lib": {
        "project_name": "example_lib",
        "project_type": "lib",
    },
}

# generated-fixture name -> variant name. Conftest's ten module fixtures
# resolve through this table so the fixture list cannot drift from VARIANTS.
ALIASES: dict[str, str] = {
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


class ProjectRegistry:
    """Session-scoped cache of rendered projects keyed by (variant, overrides).

    The render function is injected: conftest passes the real Copier renderer
    and the contract tests pass a recording stub, so the registry itself never
    renders. Each unique (variant, overrides) pair is rendered exactly once.
    """

    def __init__(self, render_fn: Callable[[dict[str, object], str], Path]) -> None:
        self._render_fn = render_fn
        self._cache: dict[tuple[str, tuple[tuple[str, object], ...] | None], Path] = {}

    def render(self, variant: str, overrides: dict[str, object] | None = None) -> Path:
        """Return the cached render of `variant`, layering overrides over the variant data.

        Raises KeyError for unknown variants before the render function runs.
        """
        data = BASE_DATA | VARIANTS[variant] | (overrides or {})
        key = (variant, None if overrides is None else tuple(sorted(overrides.items())))
        if key not in self._cache:
            self._cache[key] = self._render_fn(data, variant)
        return self._cache[key]
