"""tests/test_search_correctness.py — Search correctness + thread-safety tests.

Uses tiny fixture data — runs in <2s total.
Thread-safety test (concurrent prebuild) verifies lock logic, not I/O speed.

Run:
    pytest tests/test_search_correctness.py -v
"""

import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import session_store
from tests.helpers import reset_cache, result_ids as _ids
from tests.fixtures import EXPECTED


# ---------------------------------------------------------------------------
# Ground-truth helpers (fast — works directly on in-memory fixture dict)
# ---------------------------------------------------------------------------

def _ground_truth(query: str, sessions: list) -> set:
    """Reference search: reset cache, search, return ids. Single source of truth."""
    reset_cache(sessions)
    return _ids(session_store.search_sessions(query, sessions))


# ---------------------------------------------------------------------------
# Correctness tests
# ---------------------------------------------------------------------------

def test_cold_matches_expected(fx_sessions):
    """Cold search on fixture must match EXPECTED ground truth."""
    for query, expected_ids in EXPECTED.items():
        reset_cache(fx_sessions)
        got = _ids(session_store.search_sessions(query, fx_sessions))
        missing = expected_ids - got
        extra   = got - expected_ids
        assert not missing, f'"{query}": missed {missing}'
        assert not extra,   f'"{query}": extra  {extra}'


def test_warm_matches_expected(fx_sessions):
    """Warm (cached) search must match EXPECTED ground truth."""
    reset_cache(fx_sessions)
    session_store.prebuild_cache(fx_sessions)
    for query, expected_ids in EXPECTED.items():
        got = _ids(session_store.search_sessions(query, fx_sessions))
        missing = expected_ids - got
        extra   = got - expected_ids
        assert not missing, f'"{query}": missed {missing}'
        assert not extra,   f'"{query}": extra  {extra}'


def test_cold_warm_consistent(fx_sessions):
    """Cold and warm must return identical results for every query."""
    for query in EXPECTED:
        reset_cache(fx_sessions)
        cold = _ids(session_store.search_sessions(query, fx_sessions))
        warm = _ids(session_store.search_sessions(query, fx_sessions))
        assert cold == warm, (
            f'"{query}": cold={cold} warm={warm}, diff={cold^warm}'
        )


def test_empty_query_returns_all(fx_sessions):
    all_ids = _ids(fx_sessions)
    assert _ids(session_store.search_sessions("", fx_sessions)) == all_ids


def test_no_match_returns_empty(fx_warm):
    assert session_store.search_sessions("xyzzy_no_match_42_플루토늄", fx_warm) == []


def test_no_false_positives(fx_sessions):
    """After prebuild, search must not include non-matching sessions."""
    reset_cache(fx_sessions)
    session_store.prebuild_cache(fx_sessions)
    for query, expected_ids in EXPECTED.items():
        got = _ids(session_store.search_sessions(query, fx_sessions))
        extra = got - expected_ids
        assert not extra, f'"{query}": false positives {extra}'


def test_title_match(fx_warm):
    """Search must find sessions by title substring."""
    results = session_store.search_sessions("Docker", fx_warm)
    ids = _ids(results)
    assert "aaaaaaaa-0005-0005-0005-000000000005" in ids


def test_cwd_match(fx_warm):
    """Search must find sessions by cwd substring."""
    results = session_store.search_sessions("acme-player", fx_warm)
    ids = _ids(results)
    # cwd is "D:/Work/acme-player"
    assert "aaaaaaaa-0001-0001-0001-000000000001" in ids


def test_content_match_not_in_title(fx_warm):
    """Search must find sessions by conversation content even if not in title."""
    # "prebuild_cache" appears in the reply text, not in title
    results = session_store.search_sessions("prebuild_cache", fx_warm)
    ids = _ids(results)
    assert "aaaaaaaa-0002-0002-0002-000000000002" in ids


# ---------------------------------------------------------------------------
# Thread-safety: concurrent prebuild + search
# ---------------------------------------------------------------------------

def test_concurrent_prebuild_no_missing_results(fx_sessions):
    """Search during concurrent prebuild must never miss expected results.

    With tiny fixture data this runs in <100ms while still exercising
    the per-session lock logic.
    """
    QUERY = "에이스플레이어"
    expected = EXPECTED[QUERY]

    reset_cache(fx_sessions)
    errors: list[str] = []
    done = threading.Event()

    def searcher():
        for i in range(20):
            time.sleep(0.002)  # interleave with prebuild
            got = _ids(session_store.search_sessions(QUERY, fx_sessions))
            missing = expected - got
            if missing:
                errors.append(f"search #{i+1}: missed {missing}")
        done.set()

    prebuild_t = session_store.start_cache_prebuild(fx_sessions)
    search_t = threading.Thread(target=searcher, daemon=True)
    search_t.start()
    prebuild_t.join(timeout=5)
    done.wait(timeout=5)

    assert not errors, "Results dropped during concurrent prebuild:\n" + "\n".join(errors)


def test_concurrent_multiple_searches_consistent(fx_sessions):
    """Multiple threads searching simultaneously must all return same results."""
    QUERY = "에이스플레이어"
    reset_cache(fx_sessions)
    session_store.prebuild_cache(fx_sessions)

    result_sets: list[set] = []
    errors: list[str] = []

    def worker(idx: int):
        got = _ids(session_store.search_sessions(QUERY, fx_sessions))
        result_sets.append(got)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads: t.start()
    for t in threads: t.join(timeout=5)

    reference = result_sets[0]
    for i, rs in enumerate(result_sets[1:], 1):
        assert rs == reference, f"Thread {i} returned different results: {rs} != {reference}"


# ---------------------------------------------------------------------------
# Filter logic (single-turn / untitled)
# ---------------------------------------------------------------------------

def test_subagent_session_is_single_turn(fx_sessions):
    """Session with parent_session_id must be classified as single-turn."""
    from kiro_history import KiroHistory
    app = KiroHistory.__new__(KiroHistory)
    # Set required attrs for _is_single_turn
    subagent = next(
        s for s in fx_sessions
        if s.get("session_id") == "aaaaaaaa-0007-0007-0007-000000000007"
    )
    assert app._is_single_turn(subagent), "Subagent session must be single-turn"


def test_multi_turn_not_single_turn(fx_sessions):
    """Session with 2+ exchanges must NOT be classified as single-turn."""
    from kiro_history import KiroHistory
    app = KiroHistory.__new__(KiroHistory)
    multi = next(
        s for s in fx_sessions
        if s.get("session_id") == "aaaaaaaa-0001-0001-0001-000000000001"
    )
    assert not app._is_single_turn(multi), "2-turn session must not be single-turn"
