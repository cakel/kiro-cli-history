"""tests/integration/test_real_data.py — Real ~/.kiro data tests.

Excluded from the default test run; execute with:
    pytest -m integration
    pytest tests/integration/

The use_real_data fixture in integration/conftest.py ensures these tests
always see the real session store, never the fixture-patched one.
"""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import session_store

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Skip guard — evaluated inside tests (after use_real_data restores real paths)
# ---------------------------------------------------------------------------

def _skip_if_no_data():
    """Call inside a test body to skip when no real data is available."""
    if not (session_store.SESSIONS_DIR.exists() or session_store.SQLITE_DB.exists()):
        pytest.skip("No real ~/.kiro session data found")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_real_get_sessions():
    """Can load real sessions without error."""
    _skip_if_no_data()
    t0 = time.perf_counter()
    sessions = session_store.get_sessions()
    elapsed = time.perf_counter() - t0
    assert isinstance(sessions, list)
    print(f"\n  {len(sessions)} real sessions in {elapsed:.3f}s")


def test_real_search_acme_player():
    """에이스플레이어 search on real data must return results."""
    _skip_if_no_data()
    sessions = session_store.get_sessions()
    results = session_store.search_sessions("에이스플레이어", sessions)
    assert isinstance(results, list)
    print(f"\n  에이스플레이어: {len(results)} results from {len(sessions)} sessions")


def test_real_warm_search_fast():
    """After prebuild, real-data search must complete in <0.5s."""
    _skip_if_no_data()
    sessions = session_store.get_sessions()
    session_store.prebuild_cache(sessions)

    t0 = time.perf_counter()
    session_store.search_sessions("에이스플레이어", sessions)
    elapsed = time.perf_counter() - t0

    assert elapsed < 0.5, f"Warm search too slow on real data: {elapsed:.3f}s"
    print(f"\n  warm search: {elapsed:.3f}s")


def test_real_cold_warm_consistent():
    """Cold and warm searches must return identical results on real data."""
    _skip_if_no_data()
    sessions = session_store.get_sessions()
    for s in sessions:
        s.pop("_search_text", None)
        s.pop("_lock", None)

    query = "에이스플레이어"
    cold = {s.get("session_id") or s.get("cwd")
            for s in session_store.search_sessions(query, sessions)}
    warm = {s.get("session_id") or s.get("cwd")
            for s in session_store.search_sessions(query, sessions)}

    assert cold == warm, f"Inconsistency: diff={cold.symmetric_difference(warm)}"


def test_real_extract_messages():
    """extract_messages must work on a real session."""
    _skip_if_no_data()
    sessions = session_store.get_sessions()
    candidate = next((s for s in sessions if s.get("msg_count", 0) > 4), None)
    if candidate is None:
        pytest.skip("No real session with >4 messages")
    msgs = session_store.extract_messages(candidate, limit=5)
    assert len(msgs) > 0
    for m in msgs:
        assert "role" in m and "text" in m
