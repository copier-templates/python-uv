"""Static checks on the top-level `_` settings declared in `copier.yaml`."""

from __future__ import annotations

from _projects import copier_config

# Copier's documented settings; anything else `_`-prefixed is silently ignored.
VALID_COPIER_SETTINGS = {
    "_answers_file",
    "_envops",
    "_exclude",
    "_external_data",
    "_graceful_exit",
    "_jinja_extensions",
    "_message_after_copy",
    "_message_after_update",
    "_message_before_copy",
    "_message_before_update",
    "_migrations",
    "_min_copier_version",
    "_preserve_symlinks",
    "_secret_questions",
    "_skip_if_exists",
    "_skip_tasks",
    "_subdirectory",
    "_tasks",
    "_templates_suffix",
}


def test_copier_yaml_declares_only_real_copier_settings() -> None:
    """Every top-level `_` key must be a real Copier setting (no dead `_preserve`)."""
    unknown = {key for key in copier_config() if key.startswith("_")} - VALID_COPIER_SETTINGS
    assert not unknown, f"copier.yaml declares settings Copier never reads: {sorted(unknown)}"
