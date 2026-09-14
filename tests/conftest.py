"""conftest.py — pytest fixtures for kiro-cli-history unit tests.

ALL unit tests use in-memory fixture data (no real ~/.kiro access).
Real-data tests live in tests/integration/ and have their own conftest.py.

Key fixtures
------------
fixture_dir    : session-scope tmp dir with fake JSONL + SQLite data
fixture_env    : session-scope — patches session_store to use fixture dir.
                 NOT autouse: tests must declare it explicitly or via fx_sessions.
fx_sessions    : all sessions loaded from fixture (session-scope, loaded once)
fx_warm        : fx_sessions with full _search_text cache prebuilt (session-scope)
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Fixture directory (built once per pytest session)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def fixture_dir(tmp_path_factory):
    """Create a temp directory with fake session data. Built once per session."""
    from tests.fixtures import build_fixture_dir
    tmp = tmp_path_factory.mktemp("kiro_fixture")
    return build_fixture_dir(tmp)


@pytest.fixture(scope="session")
def fixture_env(fixture_dir):
    """Patch session_store module globals to point at fixture data.

    NOT autouse — only active for tests that explicitly depend on this fixture
    (directly or via fx_sessions / fx_warm).  This keeps integration tests
    isolated from the fixture patch.
    """
    import session_store

    demo_dir = str(fixture_dir)
    new_sessions_dir = fixture_dir / "kiro" / "sessions" / "cli"
    new_sqlite_db    = fixture_dir / "kiro-cli" / "data.sqlite3"

    old_sessions_dir = session_store.SESSIONS_DIR
    old_sqlite_db    = session_store.SQLITE_DB
    old_demo_dir     = session_store._DEMO_DIR
    old_env          = os.environ.get("KIRO_DEMO_DIR")

    session_store.SESSIONS_DIR = new_sessions_dir
    session_store.SQLITE_DB    = new_sqlite_db
    session_store._DEMO_DIR    = demo_dir
    os.environ["KIRO_DEMO_DIR"] = demo_dir

    yield

    session_store.SESSIONS_DIR = old_sessions_dir
    session_store.SQLITE_DB    = old_sqlite_db
    session_store._DEMO_DIR    = old_demo_dir
    if old_env is None:
        os.environ.pop("KIRO_DEMO_DIR", None)
    else:
        os.environ["KIRO_DEMO_DIR"] = old_env


# ---------------------------------------------------------------------------
# Session-scope data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def fx_sessions(fixture_env):
    """All sessions loaded from fixture data (cold cache, no prebuild)."""
    import session_store
    return session_store.get_sessions()


@pytest.fixture(scope="session")
def fx_warm(fixture_env):
    """Sessions with full _search_text cache prebuilt."""
    import session_store
    sessions = session_store.get_sessions()
    session_store.prebuild_cache(sessions)
    return sessions
