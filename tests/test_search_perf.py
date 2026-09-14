"""tests/test_search_perf.py — Search performance tests (fixture data).

Uses tiny in-memory fixture sessions — no real ~/.kiro access.
All tests complete in <1s total.

Run:
    pytest tests/test_search_perf.py -v
"""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import session_store
from tests.helpers import reset_cache, result_ids as _ids
from tests.fixtures import EXPECTED, FIXTURE_SESSIONS, SQLITE_SESSIONS


# ---------------------------------------------------------------------------
# Basic data layer tests
# ---------------------------------------------------------------------------

def test_get_sessions_returns_list(fx_sessions):
    assert isinstance(fx_sessions, list)
    # fixture has 7 JSONL + 2 SQLite sessions
    expected_count = len(FIXTURE_SESSIONS) + len(SQLITE_SESSIONS)
    assert len(fx_sessions) == expected_count, (
        f"Expected {expected_count} sessions, got {len(fx_sessions)}"
    )


def test_sessions_have_required_fields(fx_sessions):
    required = {"session_id", "title", "cwd", "source"}
    for s in fx_sessions:
        missing = required - s.keys()
        assert not missing, f"Session missing fields: {missing}"


def test_session_sources(fx_sessions):
    sources = {s["source"] for s in fx_sessions}
    assert "jsonl" in sources
    assert "sqlite_v2" in sources


def test_sessions_sorted_by_recency(fx_sessions):
    """Sessions with timestamps must be sorted newest-first."""
    timestamped = [s for s in fx_sessions if s.get("updated_at")]
    for i in range(len(timestamped) - 1):
        assert timestamped[i]["updated_at"] >= timestamped[i + 1]["updated_at"], (
            f"Not sorted: {timestamped[i]['updated_at']} < {timestamped[i+1]['updated_at']}"
        )


# ---------------------------------------------------------------------------
# Search correctness (fast — fixture is tiny)
# ---------------------------------------------------------------------------

def test_empty_query_returns_all(fx_sessions):
    results = session_store.search_sessions("", fx_sessions)
    assert results == fx_sessions


def test_search_acme_player(fx_sessions):
    reset_cache(fx_sessions)
    results = session_store.search_sessions("에이스플레이어", fx_sessions)
    ids = _ids(results)
    assert EXPECTED["에이스플레이어"] == ids, f"Got: {ids}"


def test_search_session_store(fx_sessions):
    reset_cache(fx_sessions)
    results = session_store.search_sessions("session_store", fx_sessions)
    ids = _ids(results)
    assert EXPECTED["session_store"] == ids, f"Got: {ids}"


def test_search_python(fx_sessions):
    reset_cache(fx_sessions)
    results = session_store.search_sessions("python", fx_sessions)
    ids = _ids(results)
    assert EXPECTED["python"] == ids, f"Got: {ids}"


def test_search_no_match(fx_warm):
    results = session_store.search_sessions("xyzzy_no_match_42", fx_warm)
    assert results == []


def test_search_case_insensitive(fx_warm):
    """Search must be case-insensitive."""
    lower = _ids(session_store.search_sessions("acme-player", fx_warm))
    upper = _ids(session_store.search_sessions("ACME-PLAYER", fx_warm))
    assert lower == upper


def test_search_partial_word(fx_warm):
    """Partial token match must work (fuzzy)."""
    # "acme" should match the cwd "D:/Work/acme-player"
    results = session_store.search_sessions("acme", fx_warm)
    ids = _ids(results)
    assert "aaaaaaaa-0001-0001-0001-000000000001" in ids


def test_search_multi_token(fx_warm):
    """Multi-word query must require all tokens."""
    results = session_store.search_sessions("에이스플레이어 설정", fx_warm)
    assert len(results) >= 1
    # A query where one token is absent should return empty
    results2 = session_store.search_sessions("에이스플레이어 xyzzy_absent", fx_warm)
    assert results2 == []


# ---------------------------------------------------------------------------
# Cache mechanics
# ---------------------------------------------------------------------------

def test_cold_warm_same_results(fx_sessions):
    """Cold and warm searches must return identical results."""
    query = "에이스플레이어"
    reset_cache(fx_sessions)
    cold = _ids(session_store.search_sessions(query, fx_sessions))
    warm = _ids(session_store.search_sessions(query, fx_sessions))
    assert cold == warm


def test_warm_search_fast(fx_warm):
    """Warm search on tiny fixture must be near-instant."""
    t0 = time.perf_counter()
    session_store.search_sessions("에이스플레이어", fx_warm)
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.1, f"Warm search too slow: {elapsed:.3f}s"


def test_prebuild_covers_all_jsonl(fx_sessions):
    """After prebuild_cache(), all JSONL sessions have _search_text."""
    reset_cache(fx_sessions)
    jsonl_sessions = [s for s in fx_sessions if s.get("source") == "jsonl"]
    session_store.prebuild_cache(fx_sessions)
    still_none = [s for s in jsonl_sessions if s.get("_search_text") is None]
    assert not still_none, f"{len(still_none)} sessions still None after prebuild"


def test_background_prebuild(fx_sessions):
    """start_cache_prebuild must complete without error."""
    reset_cache(fx_sessions)
    thread = session_store.start_cache_prebuild(fx_sessions)
    thread.join(timeout=5)
    assert not thread.is_alive()
    cached = sum(1 for s in fx_sessions if s.get("_search_text") is not None)
    jsonl_total = sum(1 for s in fx_sessions if s.get("source") == "jsonl")
    assert cached == jsonl_total


# ---------------------------------------------------------------------------
# Message extraction
# ---------------------------------------------------------------------------

def test_extract_messages_jsonl(fx_sessions):
    """extract_messages must return correct role/text for JSONL session."""
    s = next(s for s in fx_sessions
             if s.get("session_id") == "aaaaaaaa-0001-0001-0001-000000000001")
    msgs = session_store.extract_messages(s)
    assert len(msgs) == 4  # 2 prompts + 2 replies
    assert msgs[0]["role"] == "you"
    assert "에이스플레이어" in msgs[0]["text"]
    assert msgs[1]["role"] == "kiro"


def test_extract_messages_sqlite(fx_sessions):
    """extract_messages must return correct messages for SQLite v2 session."""
    s = next(s for s in fx_sessions
             if s.get("session_id") == "bbbbbbbb-0001-0001-0001-000000000001")
    msgs = session_store.extract_messages(s)
    assert len(msgs) >= 1
    assert msgs[0]["role"] == "you"
    assert "에이스플레이어" in msgs[0]["text"]


def test_extract_messages_limit(fx_sessions):
    """limit parameter must cap the number of messages returned."""
    s = next(s for s in fx_sessions
             if s.get("session_id") == "aaaaaaaa-0001-0001-0001-000000000001")
    msgs = session_store.extract_messages(s, limit=2)
    assert len(msgs) == 2


def test_extract_messages_offset(fx_sessions):
    """offset parameter must skip messages from the start."""
    s = next(s for s in fx_sessions
             if s.get("session_id") == "aaaaaaaa-0001-0001-0001-000000000001")
    all_msgs = session_store.extract_messages(s)
    offset_msgs = session_store.extract_messages(s, offset=1)
    assert len(offset_msgs) == len(all_msgs) - 1
    assert offset_msgs[0]["text"] == all_msgs[1]["text"]
