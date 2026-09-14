"""tests/integration/conftest.py — Use portable synthetic fixtures for integration tests.

These fixtures are stateless and work on any machine.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture(autouse=True)
def use_integration_fixtures():
    """Point session_store to portable integration test fixtures.
    
    These synthetic fixtures have known message counts and search patterns,
    making tests deterministic across any machine.
    """
    import session_store
    from tests.fixtures.integration_sessions import build_integration_fixtures, INTEGRATION_SESSIONS
    
    # Build fixtures if not present
    fixture_dir = Path(__file__).parent.parent / "fixtures" / "integration_sessions"
    jsonl_files = list(fixture_dir.glob("*.jsonl"))
    if len(jsonl_files) < len(INTEGRATION_SESSIONS):
        build_integration_fixtures(fixture_dir)
    
    # Store original values
    old_sessions_dir = session_store.SESSIONS_DIR
    old_sqlite_db = session_store.SQLITE_DB
    old_demo_dir = session_store._DEMO_DIR
    old_env = os.environ.get("KIRO_DEMO_DIR")
    
    # Point to fixture directory directly
    session_store.SESSIONS_DIR = fixture_dir
    session_store.SQLITE_DB = fixture_dir / "nonexistent.sqlite3"  # No SQLite in fixtures
    session_store._DEMO_DIR = ""  # Clear to prevent other path logic
    os.environ.pop("KIRO_DEMO_DIR", None)  # Remove env var
    
    yield
    
    # Restore
    session_store.SESSIONS_DIR = old_sessions_dir
    session_store.SQLITE_DB = old_sqlite_db
    session_store._DEMO_DIR = old_demo_dir
    if old_env is None:
        os.environ.pop("KIRO_DEMO_DIR", None)
    else:
        os.environ["KIRO_DEMO_DIR"] = old_env


# Export fixture specs for test assertions
def get_fixture_spec(name: str) -> dict:
    """Get the spec for a named integration fixture."""
    from tests.fixtures.integration_sessions import INTEGRATION_SESSIONS
    return INTEGRATION_SESSIONS.get(name, {})
