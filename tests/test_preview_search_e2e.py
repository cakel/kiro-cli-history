"""tests/test_preview_search_e2e.py — E2E tests for preview in-pane search.

Verifies the full search flow:
  1. All messages loaded before search
  2. Correct match count
  3. Highlight applied to matching messages
  4. Navigation (Enter=next, Shift+Tab=prev) changes current index
  5. Esc closes search and clears highlights
  6. No stale state after session switch

Uses fixture sessions (in-memory, fast). For large-session race-condition
checks, uses a synthetic session with >30 messages.
"""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import session_store
from kiro_history import KiroHistory, SessionItem
from textual.widgets import Input, ListView, RichLog, Static

# ---------------------------------------------------------------------------
# Timing constants
# ---------------------------------------------------------------------------
LOAD_TIMEOUT = 5.0
SEARCH_TIMEOUT = 8.0   # search may load all messages
POLL = 0.05


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _wait_sessions_loaded(app, pilot, timeout=LOAD_TIMEOUT):
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        await pilot.pause(POLL)
        text = str(app.query_one("#status-bar", Static).content)
        if "sessions" in text and "Loading" not in text:
            return True
    return False


async def _select_session_by_id(app, pilot, session_id_prefix: str):
    """Select a session from the list by session_id prefix."""
    lv = app.query_one("#session-list", ListView)
    lv.focus()
    items = [c for c in lv.children if isinstance(c, SessionItem)]
    for idx, item in enumerate(items):
        if item.session.get("session_id", "").startswith(session_id_prefix):
            # Navigate to item
            for _ in range(idx):
                await pilot.press("j")
            await pilot.pause(0.1)
            # Wait for preview to load
            start = time.monotonic()
            while time.monotonic() - start < LOAD_TIMEOUT:
                await pilot.pause(POLL)
                if app.selected_session and app.selected_session.get(
                    "session_id", ""
                ).startswith(session_id_prefix):
                    break
            return True
    return False


async def _select_first_session(app, pilot):
    """Select the first session in the list."""
    lv = app.query_one("#session-list", ListView)
    lv.focus()
    await pilot.press("j")
    await pilot.pause(0.2)
    start = time.monotonic()
    while time.monotonic() - start < LOAD_TIMEOUT:
        await pilot.pause(POLL)
        if app.selected_session and len(app._preview_messages) > 0:
            return True
    return False


async def _open_preview_search(app, pilot):
    """Open preview search bar with Ctrl+F (preview must have focus)."""
    preview = app.query_one("#preview", RichLog)
    preview.focus()
    await pilot.pause(POLL)
    await pilot.press("ctrl+f")
    await pilot.pause(POLL)
    # Wait for search input to appear
    start = time.monotonic()
    while time.monotonic() - start < 2.0:
        await pilot.pause(POLL)
        ps = app.query_one("#preview-search", Input)
        if ps.display and ps.has_focus:
            return True
    return False


async def _type_preview_search(pilot, app, query: str):
    """Type a query into preview search and press Enter to execute."""
    ps = app.query_one("#preview-search", Input)
    ps.value = ""
    for ch in query:
        await pilot.press(ch)
    await pilot.pause(POLL)
    # Press Enter to execute search
    await pilot.press("enter")
    # Wait for search to complete (_preview_search_executed is set)
    start = time.monotonic()
    while time.monotonic() - start < SEARCH_TIMEOUT:
        await pilot.pause(POLL)
        if app._preview_search_executed == query:
            return True
    return False


# ---------------------------------------------------------------------------
# Fixture: synthetic session with >30 messages to test large-session path
# ---------------------------------------------------------------------------

def _make_large_session(tmp_path: Path, n_messages: int = 60) -> dict:
    """Create a JSONL session file with n_messages and return session dict."""
    import json
    import uuid

    session_id = str(uuid.uuid4())
    session_dir = tmp_path / "chats"
    session_dir.mkdir(parents=True, exist_ok=True)
    session_file = session_dir / f"{session_id}.jsonl"

    lines = []
    for i in range(n_messages):
        role = "user" if i % 2 == 0 else "assistant"
        # Every 10th message contains the search target
        text = f"검색대상_고유키워드 메시지 {i}" if i % 10 == 0 else f"일반 메시지 {i}"
        lines.append(json.dumps({
            "type": "user" if role == "user" else "assistant",
            "message": {
                "role": role,
                "content": [{"type": "text", "text": text}]
            }
        }))
    session_file.write_text("\n".join(lines), encoding="utf-8")

    return {
        "session_id": session_id,
        "title": "Large Session Test",
        "cwd": str(tmp_path),
        "msg_count": n_messages,
        "file_path": str(session_file),
        "format": "jsonlv3",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T01:00:00",
        "duration_min": 60,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_preview_search_basic(fixture_env):
    """Search in preview must find matches and set _preview_search_executed."""
    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await _wait_sessions_loaded(app, pilot)
        await _select_first_session(app, pilot)

        # Find a word that exists in this session
        if not app._preview_messages:
            pytest.skip("No messages in first session")

        # Pick first word from first message
        first_text = app._preview_messages[0].get("text", "")
        words = [w for w in first_text.split() if len(w) >= 2]
        if not words:
            pytest.skip("No searchable words in first message")
        query = words[0]

        opened = await _open_preview_search(app, pilot)
        assert opened, "Preview search bar did not open"

        searched = await _type_preview_search(pilot, app, query)
        assert searched, f"Search did not complete for '{query}'"

        assert app._preview_search_executed == query
        assert len(app._preview_search_matches) > 0
        assert app._preview_search_current == 0


@pytest.mark.asyncio
async def test_preview_search_all_messages_loaded(fixture_env):
    """Search must load all messages before searching."""
    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await _wait_sessions_loaded(app, pilot)
        await _select_first_session(app, pilot)

        if not app._preview_messages:
            pytest.skip("No messages")

        # Get expected total from session metadata
        expected_total = app.selected_session.get("msg_count", 0)
        query = "a"  # broad query to force full load

        opened = await _open_preview_search(app, pilot)
        assert opened

        searched = await _type_preview_search(pilot, app, query)
        assert searched

        # After search, all messages must be loaded
        assert app._preview_all_loaded, "Messages not fully loaded after search"
        assert len(app._preview_messages) == expected_total, (
            f"Expected {expected_total} messages, got {len(app._preview_messages)}"
        )


@pytest.mark.asyncio
async def test_preview_search_match_indices_correct(fixture_env):
    """Match indices must correspond to messages actually containing the query."""
    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await _wait_sessions_loaded(app, pilot)
        await _select_first_session(app, pilot)

        if not app._preview_messages:
            pytest.skip("No messages")

        # Find a rare word in first message
        first_text = app._preview_messages[0].get("text", "")
        words = [w for w in first_text.split() if len(w) >= 3]
        if not words:
            pytest.skip("No words")
        query = words[0]

        opened = await _open_preview_search(app, pilot)
        assert opened
        searched = await _type_preview_search(pilot, app, query)
        assert searched

        q = query.lower()
        # Verify: every index in matches actually contains the query
        for idx in app._preview_search_matches:
            txt = app._preview_messages[idx].get("text", "")
            assert q in txt.lower(), (
                f"Match index {idx} does not contain '{query}': {txt[:80]!r}"
            )

        # Verify: no false negatives (every message with query is in matches)
        match_set = set(app._preview_search_matches)
        for i, msg in enumerate(app._preview_messages):
            if q in msg.get("text", "").lower():
                assert i in match_set, (
                    f"Message {i} contains '{query}' but not in match_set"
                )


@pytest.mark.asyncio
async def test_preview_search_navigation_next(fixture_env):
    """Enter must advance _preview_search_current through matches."""
    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await _wait_sessions_loaded(app, pilot)
        await _select_first_session(app, pilot)

        if not app._preview_messages:
            pytest.skip("No messages")

        query = app._preview_messages[0].get("text", "").split()[0] if app._preview_messages[0].get("text", "").split() else None
        if not query:
            pytest.skip("No query")

        opened = await _open_preview_search(app, pilot)
        assert opened
        searched = await _type_preview_search(pilot, app, query)
        assert searched

        n = len(app._preview_search_matches)
        if n < 2:
            pytest.skip("Need ≥2 matches for navigation test")

        # Enter = next
        initial = app._preview_search_current  # 0
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert app._preview_search_current == (initial + 1) % n, (
            f"Enter did not advance: {initial} → {app._preview_search_current}"
        )

        # Enter again
        await pilot.press("enter")
        await pilot.pause(0.1)
        assert app._preview_search_current == (initial + 2) % n


@pytest.mark.asyncio
async def test_preview_search_navigation_prev(fixture_env):
    """Shift+Tab must go to previous match."""
    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await _wait_sessions_loaded(app, pilot)
        await _select_first_session(app, pilot)

        if not app._preview_messages:
            pytest.skip("No messages")

        query = app._preview_messages[0].get("text", "").split()[0] if app._preview_messages[0].get("text", "").split() else None
        if not query:
            pytest.skip("No query")

        opened = await _open_preview_search(app, pilot)
        assert opened
        searched = await _type_preview_search(pilot, app, query)
        assert searched

        n = len(app._preview_search_matches)
        if n < 2:
            pytest.skip("Need ≥2 matches for prev test")

        # Shift+Tab from position 0 → wraps to last
        assert app._preview_search_current == 0
        await pilot.press("shift+tab")
        await pilot.pause(0.1)
        assert app._preview_search_current == n - 1, (
            f"Shift+Tab did not go to last: got {app._preview_search_current}"
        )


@pytest.mark.asyncio
async def test_preview_search_esc_clears(fixture_env):
    """Esc must close search bar and clear all search state."""
    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await _wait_sessions_loaded(app, pilot)
        await _select_first_session(app, pilot)

        if not app._preview_messages:
            pytest.skip("No messages")

        query = "a"
        opened = await _open_preview_search(app, pilot)
        assert opened
        searched = await _type_preview_search(pilot, app, query)
        assert searched

        # Esc
        await pilot.press("escape")
        await pilot.pause(0.2)

        assert not app._preview_search_active, "Search bar still active after Esc"
        assert app._preview_search_executed == "", "executed not cleared"
        assert app._preview_search_matches == [], "matches not cleared"
        assert app._preview_search_current == -1, "current not reset"

        # Search bar hidden
        ps = app.query_one("#preview-search", Input)
        assert not ps.display, "Search bar still visible after Esc"


@pytest.mark.asyncio
async def test_preview_search_no_match(fixture_env):
    """Searching for non-existent term must result in 0 matches."""
    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await _wait_sessions_loaded(app, pilot)
        await _select_first_session(app, pilot)

        if not app._preview_messages:
            pytest.skip("No messages")

        opened = await _open_preview_search(app, pilot)
        assert opened
        searched = await _type_preview_search(pilot, app, "xyzzy_노매칭_9999")
        assert searched

        assert app._preview_search_matches == []
        assert app._preview_search_current == -1



@pytest.mark.asyncio
async def test_large_session_search_loads_all(tmp_path, monkeypatch):
    """Search on >30-message session must load ALL messages (race-condition test).

    Creates a synthetic 60-message JSONL session, patches get_sessions/extract_messages,
    then verifies that after search:
    - _preview_messages contains all 60 messages
    - _preview_search_matches contains exactly the expected matches
    """
    import json
    import uuid as _uuid
    import session_store as ss

    N = 120   # 4× batch size — covers the real-world 757-message case
    KEYWORD = "검색대상_고유키워드"

    # Build JSONL file
    session_id = str(_uuid.uuid4())
    session_dir = tmp_path / "chats"
    session_dir.mkdir(parents=True, exist_ok=True)
    session_file = session_dir / f"{session_id}.jsonl"

    expected_matches = 0
    file_lines = []
    for i in range(N):
        role = "user" if i % 2 == 0 else "assistant"
        text = f"{KEYWORD} msg {i}" if i % 10 == 0 else f"normal msg {i}"
        if i % 10 == 0:
            expected_matches += 1
        file_lines.append(json.dumps({
            "kind": "Prompt" if i % 2 == 0 else "AssistantMessage",
            "data": {"content": [{"kind": "text", "data": text}]}
        }))
    session_file.write_text("\n".join(file_lines), encoding="utf-8")

    synthetic = {
        "session_id": session_id,
        "title": "Large Session E2E Test",
        "cwd": str(tmp_path),
        "msg_count": N,
        "jsonl_path": str(session_file),
        "source": "jsonl",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T01:00:00",
        "duration_min": 60,
    }

    # Patch at every import level the app uses
    import kiro_history as kh
    monkeypatch.setattr(kh, "get_sessions", lambda: [synthetic])
    monkeypatch.setattr(ss, "get_sessions", lambda: [synthetic])

    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        # Wait for synthetic session to appear
        start = time.monotonic()
        while time.monotonic() - start < LOAD_TIMEOUT:
            await pilot.pause(POLL)
            items = [c for c in app.query_one("#session-list", ListView).children
                     if isinstance(c, SessionItem)]
            if items and items[0].session.get("session_id") == session_id:
                break
        assert items, "Synthetic session did not appear in list"

        # Select it
        lv = app.query_one("#session-list", ListView)
        lv.focus()
        await pilot.press("j")

        # Wait for first batch (should be <=30)
        start = time.monotonic()
        while time.monotonic() - start < LOAD_TIMEOUT:
            await pilot.pause(POLL)
            if (app.selected_session and
                    app.selected_session.get("session_id") == session_id and
                    len(app._preview_messages) > 0):
                break

        assert app.selected_session is not None
        assert app.selected_session.get("session_id") == session_id, (
            f"Wrong session: {app.selected_session.get('session_id')}"
        )
        first_batch = len(app._preview_messages)
        assert 0 < first_batch <= 30, f"First batch should be <=30, got {first_batch}"
        assert not app._preview_all_loaded, "Should not be all-loaded with only first batch"

        # Open preview search
        app.query_one("#preview", RichLog).focus()
        await pilot.pause(POLL)
        await pilot.press("ctrl+f")
        start = time.monotonic()
        while time.monotonic() - start < 2.0:
            await pilot.pause(POLL)
            if app.query_one("#preview-search", Input).display:
                break

        # Execute search (triggers _load_all_for_search)
        searched = await _type_preview_search(pilot, app, KEYWORD)
        assert searched, (
            f"Search timed out. executed={app._preview_search_executed!r} "
            f"msgs={len(app._preview_messages)} all_loaded={app._preview_all_loaded}"
        )

        # CRITICAL: all N messages must be in _preview_messages
        assert app._preview_all_loaded, "_preview_all_loaded is False after search"
        assert len(app._preview_messages) == N, (
            f"Expected {N} msgs, got {len(app._preview_messages)}"
        )

        # Correct match count
        assert len(app._preview_search_matches) == expected_matches, (
            f"Expected {expected_matches} matches, got {len(app._preview_search_matches)}"
        )

        # Every match index contains keyword
        for idx in app._preview_search_matches:
            txt = app._preview_messages[idx].get("text", "")
            assert KEYWORD in txt, f"Match at {idx} missing keyword: {txt!r}"

        # Matches must span the full range — not just first batch (30)
        # This is the core race-condition check
        max_match_idx = max(app._preview_search_matches)
        assert max_match_idx >= 30, (
            f"All matches in first batch only (max={max_match_idx}). "
            "Race condition: _preview_messages was overwritten with 30-msg batch."
        )

        # No false negatives: every message with keyword must be in matches
        match_set = set(app._preview_search_matches)
        for i, msg in enumerate(app._preview_messages):
            if KEYWORD in msg.get("text", "").lower():
                assert i in match_set, (
                    f"Message {i} contains keyword but not in matches (false negative)"
                )

@pytest.mark.asyncio
async def test_search_state_cleared_on_session_switch(fixture_env):
    """Switching sessions must clear all preview search state."""
    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await _wait_sessions_loaded(app, pilot)

        # Select first session and search
        lv = app.query_one("#session-list", ListView)
        lv.focus()
        await pilot.press("j")
        await pilot.pause(0.2)

        if not app._preview_messages:
            pytest.skip("No messages in first session")

        opened = await _open_preview_search(app, pilot)
        assert opened
        searched = await _type_preview_search(pilot, app, "a")
        assert searched
        assert app._preview_search_executed != ""

        # Switch to next session
        app.query_one("#session-list", ListView).focus()
        await pilot.pause(POLL)
        await pilot.press("j")
        await pilot.press("j")
        await pilot.pause(0.3)

        # Search state must be cleared
        assert not app._preview_search_active, "search still active after session switch"
        assert app._preview_search_executed == "", "executed not cleared on switch"
        assert app._preview_search_matches == [], "matches not cleared on switch"
