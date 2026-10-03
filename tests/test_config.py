"""Tests for config.py — configuration management.

Strategy
--------
config._DATA_DIR is resolved once at module import time, so we cannot
change it by patching an env var at test time without reloading the module.

The most stable approach is to monkeypatch `config._get_config_path` so it
returns a path inside pytest's tmp_path.  This keeps every test hermetic
without touching ProgramData / ~/.local/share.

For get_data_dir() tests that must exercise the env-var code path we use
importlib.reload() under a controlled environment.
"""

import importlib
import json
import os
import sys
from pathlib import Path

import pytest

# Ensure project root is importable (matches conftest.py pattern)
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from config import (
    CONFIG_FILENAME,
    DEFAULT_SETTINGS,
    get_data_dir,
    get_setting,
    load_config,
    save_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_config_path(monkeypatch, tmp_path: Path) -> Path:
    """Redirect all config I/O to a temporary file in tmp_path."""
    cfg_file = tmp_path / CONFIG_FILENAME
    monkeypatch.setattr(config, "_get_config_path", lambda: cfg_file)
    # Also make get_data_dir() return tmp_path so save_config's tempfile
    # creation lands in the same directory.
    monkeypatch.setattr(config, "get_data_dir", lambda: tmp_path)
    return cfg_file


# ---------------------------------------------------------------------------
# get_data_dir() tests
# ---------------------------------------------------------------------------

class TestGetDataDir:
    """Tests that get_data_dir() returns the correct path based on env vars.

    These tests reload the config module under controlled env conditions
    because _DATA_DIR is computed at import time.
    """

    def _reload_with_env(self, monkeypatch, env_value=None):
        """Reload config module with KIRO_HISTORY_DATA_DIR set or unset."""
        if env_value is None:
            monkeypatch.delenv("KIRO_HISTORY_DATA_DIR", raising=False)
        else:
            monkeypatch.setenv("KIRO_HISTORY_DATA_DIR", env_value)
        reloaded = importlib.reload(config)
        return reloaded

    def test_no_env_var_returns_default_path(self, monkeypatch, tmp_path):
        """When no env var is set, get_data_dir() returns the OS default path."""
        cfg = self._reload_with_env(monkeypatch, env_value=None)
        # Patch mkdir so we don't actually create ProgramData dirs
        monkeypatch.setattr(Path, "mkdir", lambda self, **kw: None)
        result = cfg.get_data_dir()
        expected = cfg._get_default_data_dir()
        assert result == expected

    def test_empty_env_var_returns_default_path(self, monkeypatch):
        """Regression: empty KIRO_HISTORY_DATA_DIR must not resolve to CWD.

        Before the fix, Path('') evaluated to Path('.') which pointed to the
        current working directory.  After the fix the code strips and checks
        for an empty string before calling Path().
        """
        cfg = self._reload_with_env(monkeypatch, env_value="")
        # Patch mkdir so we don't create real dirs
        monkeypatch.setattr(Path, "mkdir", lambda self, **kw: None)
        result = cfg.get_data_dir()
        expected = cfg._get_default_data_dir()
        assert result == expected, (
            f"Empty env var must not resolve to CWD; got {result!r}, expected {expected!r}"
        )
        # Also verify the result is not the current directory
        assert result != Path(".").resolve()
        assert result != Path("").resolve()

    def test_env_var_set_returns_custom_path(self, monkeypatch, tmp_path):
        """When KIRO_HISTORY_DATA_DIR is set to a valid path, that path is used."""
        cfg = self._reload_with_env(monkeypatch, env_value=str(tmp_path))
        result = cfg.get_data_dir()
        assert result == tmp_path


# ---------------------------------------------------------------------------
# load_config() tests
# ---------------------------------------------------------------------------

class TestLoadConfig:
    """Tests for load_config() reading behaviour."""

    def test_missing_file_returns_all_defaults(self, monkeypatch, tmp_path):
        """When no config file exists, all DEFAULT_SETTINGS keys are present."""
        cfg_file = _patch_config_path(monkeypatch, tmp_path)
        assert not cfg_file.exists()

        result = load_config()

        for key in DEFAULT_SETTINGS:
            assert key in result, f"Key {key!r} missing from result"
        assert result == DEFAULT_SETTINGS

    def test_corrupt_json_returns_defaults(self, monkeypatch, tmp_path):
        """A corrupt/invalid JSON file falls back to DEFAULT_SETTINGS."""
        cfg_file = _patch_config_path(monkeypatch, tmp_path)
        cfg_file.write_text("{not valid json{{", encoding="utf-8")

        result = load_config()

        assert result == DEFAULT_SETTINGS

    def test_unknown_keys_excluded_from_result(self, monkeypatch, tmp_path):
        """Keys not in DEFAULT_SETTINGS must not appear in the loaded config."""
        cfg_file = _patch_config_path(monkeypatch, tmp_path)
        data = {
            "schema_version": 1,
            "settings": {
                "trust_all_tools": True,
                "unknown_future_key": "something",
                "another_unknown": 42,
            },
        }
        cfg_file.write_text(json.dumps(data), encoding="utf-8")

        result = load_config()

        assert "unknown_future_key" not in result
        assert "another_unknown" not in result
        # Known key is still present
        assert "trust_all_tools" in result

    def test_bool_type_enforcement_integer_falls_back_to_default(self, monkeypatch, tmp_path):
        """Bool settings stored as integer (1) must be replaced with the default.

        The config spec requires bool settings to be actual Python booleans;
        truthy non-bool values (1, 'yes', etc.) are silently replaced with
        the default.
        """
        cfg_file = _patch_config_path(monkeypatch, tmp_path)
        # 'trust_all_tools' and 'debug' are bool settings
        data = {
            "schema_version": 1,
            "settings": {
                "trust_all_tools": 1,      # int, not bool
                "show_single_turn": "yes", # str, not bool
                "debug": False,            # valid bool
            },
        }
        cfg_file.write_text(json.dumps(data), encoding="utf-8")

        result = load_config()

        # Non-bool values are replaced by the default
        assert result["trust_all_tools"] == DEFAULT_SETTINGS["trust_all_tools"]
        assert result["show_single_turn"] == DEFAULT_SETTINGS["show_single_turn"]
        # Valid bool is preserved as-is
        assert result["debug"] is False

    def test_bool_type_enforcement_string_yes_falls_back_to_default(self, monkeypatch, tmp_path):
        """Bool settings stored as string 'yes' must be replaced with the default."""
        cfg_file = _patch_config_path(monkeypatch, tmp_path)
        data = {
            "schema_version": 1,
            "settings": {"show_untitled": "yes"},
        }
        cfg_file.write_text(json.dumps(data), encoding="utf-8")

        result = load_config()

        assert result["show_untitled"] == DEFAULT_SETTINGS["show_untitled"]
        assert isinstance(result["show_untitled"], bool)

    def test_valid_file_loaded_correctly(self, monkeypatch, tmp_path):
        """A well-formed config file is read and returned correctly."""
        cfg_file = _patch_config_path(monkeypatch, tmp_path)
        custom_settings = {
            "trust_all_tools": False,
            "show_single_turn": True,
            "show_untitled": True,
            "theme": "textual-light",
            "debug": True,
            "retention_days": 30,
        }
        data = {
            "schema_version": 1,
            "settings": custom_settings,
        }
        cfg_file.write_text(json.dumps(data), encoding="utf-8")

        result = load_config()

        for key, expected_value in custom_settings.items():
            assert result[key] == expected_value, (
                f"Key {key!r}: expected {expected_value!r}, got {result[key]!r}"
            )


# ---------------------------------------------------------------------------
# save_config() tests
# ---------------------------------------------------------------------------

class TestSaveConfig:
    """Tests for save_config() writing behaviour."""

    def test_save_returns_true_empty_string_on_success(self, monkeypatch, tmp_path):
        """Successful save must return (True, '')."""
        _patch_config_path(monkeypatch, tmp_path)

        ok, err = save_config(DEFAULT_SETTINGS.copy())

        assert ok is True
        assert err == ""

    def test_save_filters_unknown_keys(self, monkeypatch, tmp_path):
        """Unknown keys passed to save_config must not appear in the saved file."""
        cfg_file = _patch_config_path(monkeypatch, tmp_path)
        dirty_settings = dict(DEFAULT_SETTINGS)
        dirty_settings["totally_unknown_key"] = "should_be_dropped"
        dirty_settings["another_bad_key"] = 999

        save_config(dirty_settings)

        saved = json.loads(cfg_file.read_text(encoding="utf-8"))
        saved_keys = set(saved.get("settings", {}).keys())
        assert "totally_unknown_key" not in saved_keys
        assert "another_bad_key" not in saved_keys

    def test_saved_file_is_valid_json(self, monkeypatch, tmp_path):
        """The file written by save_config must be parseable as JSON."""
        cfg_file = _patch_config_path(monkeypatch, tmp_path)

        save_config(DEFAULT_SETTINGS.copy())

        content = cfg_file.read_text(encoding="utf-8")
        # Must not raise
        parsed = json.loads(content)
        assert isinstance(parsed, dict)
        assert "settings" in parsed
        assert "schema_version" in parsed

    def test_save_then_load_round_trip(self, monkeypatch, tmp_path):
        """Settings saved with save_config must be identical when loaded back."""
        _patch_config_path(monkeypatch, tmp_path)
        original = {
            "trust_all_tools": False,
            "show_single_turn": True,
            "show_untitled": False,
            "theme": "nord",
            "debug": True,
            "retention_days": 180,
        }

        ok, _ = save_config(original)
        assert ok is True

        loaded = load_config()
        for key, expected_value in original.items():
            assert loaded[key] == expected_value, (
                f"Round-trip mismatch on {key!r}: "
                f"saved {expected_value!r}, loaded {loaded[key]!r}"
            )


# ---------------------------------------------------------------------------
# get_setting() tests
# ---------------------------------------------------------------------------

class TestGetSetting:
    """Tests for get_setting() convenience wrapper."""

    def test_existing_key_returns_value(self, monkeypatch, tmp_path):
        """get_setting() returns the correct value for an existing key."""
        cfg_file = _patch_config_path(monkeypatch, tmp_path)
        data = {
            "schema_version": 1,
            "settings": {"theme": "solarized-dark", "retention_days": 60},
        }
        cfg_file.write_text(json.dumps(data), encoding="utf-8")

        assert get_setting("theme") == "solarized-dark"
        assert get_setting("retention_days") == 60

    def test_missing_key_returns_provided_default(self, monkeypatch, tmp_path):
        """get_setting() returns the caller-supplied default for unknown keys."""
        _patch_config_path(monkeypatch, tmp_path)
        # No config file — only defaults exist

        result = get_setting("nonexistent_key", default="fallback")
        assert result == "fallback"

    def test_missing_key_returns_none_when_no_default_given(self, monkeypatch, tmp_path):
        """get_setting() returns None for unknown keys when default is omitted."""
        _patch_config_path(monkeypatch, tmp_path)

        result = get_setting("another_nonexistent_key")
        assert result is None

    def test_existing_bool_key_returns_bool(self, monkeypatch, tmp_path):
        """get_setting() returns the correct bool type for bool settings."""
        cfg_file = _patch_config_path(monkeypatch, tmp_path)
        data = {
            "schema_version": 1,
            "settings": {"debug": True},
        }
        cfg_file.write_text(json.dumps(data), encoding="utf-8")

        result = get_setting("debug")
        assert result is True
        assert isinstance(result, bool)
