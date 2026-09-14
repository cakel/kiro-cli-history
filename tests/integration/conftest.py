"""tests/integration/conftest.py — Ensure integration tests use real ~/.kiro data.

The parent conftest.py's fixture_env is NOT autouse, so integration tests
are not affected by the fixture patch.  This conftest explicitly restores
the real paths in case something else patched them.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture(autouse=True)
def use_real_data():
    """Guarantee real session_store paths for every integration test.

    Removes KIRO_DEMO_DIR if set (by a parent fixture or env) and restores
    the module-level paths to their production defaults.
    """
    import session_store

    # Remove any fixture patch from the environment
    old_env = os.environ.pop("KIRO_DEMO_DIR", None)

    # Re-derive production paths
    real_sessions_dir = Path.home() / ".kiro" / "sessions" / "cli"
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        base = Path(local) if local else Path.home() / "AppData" / "Local"
        real_sqlite_db = base / "kiro-cli" / "data.sqlite3"
    elif sys.platform == "darwin":
        real_sqlite_db = Path.home() / "Library" / "Application Support" / "kiro-cli" / "data.sqlite3"
    else:
        xdg = os.environ.get("XDG_DATA_HOME", "")
        base = Path(xdg) if xdg else Path.home() / ".local" / "share"
        real_sqlite_db = base / "kiro-cli" / "data.sqlite3"

    old_sessions_dir = session_store.SESSIONS_DIR
    old_sqlite_db    = session_store.SQLITE_DB
    old_demo_dir     = session_store._DEMO_DIR

    session_store.SESSIONS_DIR = real_sessions_dir
    session_store.SQLITE_DB    = real_sqlite_db
    session_store._DEMO_DIR    = ""

    yield

    # Restore whatever was there before
    session_store.SESSIONS_DIR = old_sessions_dir
    session_store.SQLITE_DB    = old_sqlite_db
    session_store._DEMO_DIR    = old_demo_dir
    if old_env is not None:
        os.environ["KIRO_DEMO_DIR"] = old_env
