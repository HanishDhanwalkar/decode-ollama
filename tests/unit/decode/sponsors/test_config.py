"""Unit tests for decode.sponsors.config."""

import json
from pathlib import Path

from pydantic import SecretStr

from decode.config.settings import Settings
from decode.sponsors.config import (
    get_anonymized_metadata,
    is_sponsors_enabled,
    read_config_file_opt_out,
)
from decode.sponsors.types import FORBIDDEN_METADATA_KEYS


def test_get_anonymized_metadata_has_zero_code_leakage():
    """Anonymized metadata contains only OS/Python/Client version; never user data."""
    meta = get_anonymized_metadata()
    data = meta.to_dict()

    assert "client_version" in data
    assert "os_type" in data
    assert "python_version" in data

    # Check that no forbidden keys or substrings exist
    for key in data:
        assert key not in FORBIDDEN_METADATA_KEYS
        for forbidden in ("prompt", "code", "file", "token", "diff", "path"):
            assert forbidden not in key.lower()


def test_read_config_file_opt_out(tmp_path: Path):
    """Parses ads: false or sponsors: false from JSON config files."""
    config_file = tmp_path / "settings.json"

    # Missing file -> None
    assert read_config_file_opt_out(config_file) is None

    # ads: false
    config_file.write_text(json.dumps({"ads": False}))
    assert read_config_file_opt_out(config_file) is False

    # sponsors: false
    config_file.write_text(json.dumps({"sponsors": False}))
    assert read_config_file_opt_out(config_file) is False

    # ads: true
    config_file.write_text(json.dumps({"ads": True}))
    assert read_config_file_opt_out(config_file) is True

    # Malformed JSON -> None
    config_file.write_text("INVALID JSON")
    assert read_config_file_opt_out(config_file) is None


def test_is_sponsors_enabled_cli_flag_opt_out():
    """--no-ads CLI flag unconditionally disables sponsors."""
    settings = Settings(sponsors_enabled=True, llm_provider="gemini")
    assert not is_sponsors_enabled(settings, no_ads_flag=True)


def test_is_sponsors_enabled_settings_json_opt_out(tmp_path: Path):
    """Local settings.json with ads: false disables sponsors."""
    config_file = tmp_path / "settings.json"
    config_file.write_text(json.dumps({"ads": False}))

    settings = Settings(sponsors_enabled=True, llm_provider="gemini")
    assert not is_sponsors_enabled(settings, config_path=config_file)


def test_is_sponsors_enabled_global_settings_opt_out():
    """Setting sponsors_enabled=False disables sponsors."""
    settings = Settings(sponsors_enabled=False, llm_provider="gemini")
    assert not is_sponsors_enabled(settings)


def test_is_sponsors_enabled_default_active():
    """Sponsors are active when configured and not opted out."""
    settings = Settings(
        sponsors_enabled=True,
        llm_provider="gemini",
    )
    assert is_sponsors_enabled(settings)
