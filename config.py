"""config.py — Configuration management for kiro-cli-history.

Handles reading/writing kiro-cli-history.json with schema versioning.
Config file is optional — app works with defaults if missing.

Public API:
    get_data_dir()     -> Path (creates if needed)
    load_config()      -> dict (settings with defaults applied)
    save_config(settings: dict) -> bool
    get_setting(key: str, default=None) -> Any
"""

import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1
CONFIG_FILENAME = "kiro-cli-history.json"

# Default settings — used when config file is missing or incomplete
DEFAULT_SETTINGS = {
    "trust_all_tools": True,
    "show_single_turn": False,
    "show_untitled": False,
    "theme": "textual-dark",
}


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _get_default_data_dir() -> Path:
    """Get default data directory based on OS."""
    if os.name == "nt":
        return Path(r"C:\ProgramData\kiro-cli-history\data")
    return Path.home() / ".local" / "share" / "kiro-cli-history" / "data"

# Fixed data directory — override with KIRO_HISTORY_DATA_DIR env var if needed
_DATA_DIR = Path(os.environ.get("KIRO_HISTORY_DATA_DIR", "")) or _get_default_data_dir()


def get_install_dir() -> Path:
    """Get the installation directory (where kiro_history.py lives)."""
    # When running from installed location, this file is in install dir
    # When running from source, use the script location
    return Path(__file__).parent.resolve()


def get_data_dir() -> Path:
    """Get the data directory for config and logs. Creates if needed."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    return _DATA_DIR


def _get_config_path() -> Path:
    """Get the full path to the config file."""
    return get_data_dir() / CONFIG_FILENAME


# ---------------------------------------------------------------------------
# Version string (imported from main module or fallback)
# ---------------------------------------------------------------------------

def _get_app_version() -> str:
    """Get the current app version string."""
    try:
        from _version import VERSION
        return VERSION
    except ImportError:
        return "unknown"


# ---------------------------------------------------------------------------
# Load / Save
# ---------------------------------------------------------------------------

def load_config() -> dict:
    """Load config from file, applying defaults for missing keys.
    
    Returns a dict with all settings guaranteed to have values.
    If file doesn't exist or is invalid, returns defaults.
    """
    config_path = _get_config_path()
    settings = DEFAULT_SETTINGS.copy()
    
    if not config_path.exists():
        return settings
    
    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
        
        # Schema migration placeholder
        file_schema = data.get("schema_version", 1)
        if file_schema < SCHEMA_VERSION:
            # Future: migrate from older schema versions
            pass
        
        # Merge saved settings with defaults (defaults fill gaps)
        saved_settings = data.get("settings", {})
        for key in DEFAULT_SETTINGS:
            if key in saved_settings:
                val = saved_settings[key]
                # Type-check: bool settings must be bool (guard against "yes", 1, etc.)
                if isinstance(DEFAULT_SETTINGS[key], bool):
                    settings[key] = bool(val) if isinstance(val, bool) else DEFAULT_SETTINGS[key]
                else:
                    settings[key] = val
                
    except (json.JSONDecodeError, OSError, KeyError, TypeError):
        # Corrupted or unreadable — use defaults
        pass
    
    return settings


def save_config(settings: dict) -> tuple:
    """Save settings to config file.
    
    Args:
        settings: Dict of setting key-value pairs to save.
                  Only keys in DEFAULT_SETTINGS are saved.
    
    Returns:
        (True, "") on success, (False, error_message) on failure.
    """
    config_path = _get_config_path()
    
    # Filter to known settings only
    filtered = {k: v for k, v in settings.items() if k in DEFAULT_SETTINGS}
    
    data = {
        "schema_version": SCHEMA_VERSION,
        "app_version": _get_app_version(),
        "settings": filtered,
    }
    
    tmp_path = None
    try:
        # Atomic write: write to temp, then rename
        import tempfile
        data_dir = get_data_dir()
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            dir=data_dir,
            delete=False,
        ) as tmp:
            json.dump(data, tmp, indent=2, ensure_ascii=False)
            tmp_path = tmp.name
        
        # Replace atomically
        os.replace(tmp_path, config_path)
        return (True, "")
        
    except (OSError, TypeError) as e:
        # Clean up temp file if rename failed
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return (False, str(e))


def get_setting(key: str, default=None):
    """Get a single setting value. Convenience wrapper around load_config."""
    settings = load_config()
    return settings.get(key, default)


# ---------------------------------------------------------------------------
# CLI self-check
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== config.py self-check ===\n")
    
    print(f"Install dir: {get_install_dir()}")
    print(f"Data dir: {get_data_dir()}")
    print(f"Config path: {_get_config_path()}")
    print(f"App version: {_get_app_version()}")
    print()
    
    print("Current settings:")
    settings = load_config()
    for k, v in settings.items():
        print(f"  {k}: {v}")
    print()
    
    # Test save
    print("Testing save...")
    ok, err = save_config(settings)
    if ok:
        print("  Save successful")
        print(f"  File contents: {_get_config_path().read_text()}")
    else:
        print(f"  Save failed: {err}")
    
    print("\n=== OK ===")
