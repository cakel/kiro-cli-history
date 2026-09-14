"""tests/test_highlight_rendering.py — Verify highlight is actually rendered in RichLog.

Inspects RichLog.lines (Strip objects containing Segments with style info)
to confirm that matching messages have background color applied.
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from kiro_history import KiroHistory, SessionItem
from textual.widgets import Input, ListView, RichLog, Static

LOAD_TIMEOUT = 5.0
SEARCH_TIMEOUT = 10.0
POLL = 0.05


async def _wait_sessions_loaded(app, pilot, timeout=LOAD_TIMEOUT):
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        await pilot.pause(POLL)
        text = str(app.query_one("#status-bar", Static).content)
        if "sessions" in text and "Loading" not in text:
            return True
    return False


async def _select_first_session(app, pilot):
    lv = app.query_one("#session-list", ListView)
    lv.focus()
    await pilot.press("j")
    start = time.monotonic()
    while time.monotonic() - start < LOAD_TIMEOUT:
        await pilot.pause(POLL)
        if app.selected_session and len(app._preview_messages) > 0:
            return True
    return False


async def _open_search_and_execute(app, pilot, query, timeout=SEARCH_TIMEOUT):
    app.query_one("#preview", RichLog).focus()
    await pilot.pause(POLL)
    await pilot.press("ctrl+f")
    start = time.monotonic()
    while time.monotonic() - start < 2.0:
        await pilot.pause(POLL)
        if app.query_one("#preview-search", Input).display:
            break

    for ch in query:
        await pilot.press(ch)
    await pilot.pause(POLL)
    await pilot.press("enter")

    start = time.monotonic()
    while time.monotonic() - start < timeout:
        await pilot.pause(POLL)
        if app._preview_search_executed == query:
            return True
    return False


def _richlog_has_background(richlog: RichLog, bg_color: str) -> bool:
    """Check if any Strip in RichLog.lines has a segment with given background color."""
    for strip in richlog.lines:
        for segment in strip:
            if segment.style and segment.style.bgcolor:
                color_str = str(segment.style.bgcolor).lower()
                if bg_color.lower() in color_str or color_str in bg_color.lower():
                    return True
    return False


def _richlog_count_highlighted_lines(richlog: RichLog) -> int:
    """Count lines (Strips) that contain at least one highlighted segment."""
    count = 0
    for strip in richlog.lines:
        for segment in strip:
            if segment.style and segment.style.bgcolor:
                count += 1
                break
    return count


def _richlog_collect_bg_colors(richlog: RichLog) -> set:
    """Collect all unique background colors used in RichLog."""
    colors = set()
    for strip in richlog.lines:
        for segment in strip:
            if segment.style and segment.style.bgcolor:
                colors.add(str(segment.style.bgcolor))
    return colors


@pytest.mark.asyncio
async def test_highlight_applied_to_richlog(fixture_env):
    """After search, RichLog must contain segments with background color."""
    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await _wait_sessions_loaded(app, pilot)
        await _select_first_session(app, pilot)

        if not app._preview_messages:
            pytest.skip("No messages")

        # Find a query that will match something
        query = None
        for msg in app._preview_messages:
            words = [w for w in msg.get("text", "").split() if len(w) >= 2]
            if words:
                query = words[0]
                break
        if not query:
            pytest.skip("No searchable word")

        searched = await _open_search_and_execute(app, pilot, query)
        assert searched, f"Search did not complete for '{query}'"

        if not app._preview_search_matches:
            pytest.skip(f"No matches for '{query}'")

        # CORE CHECK: RichLog must have segments with background color
        preview = app.query_one("#preview", RichLog)
        bg_colors = _richlog_collect_bg_colors(preview)
        assert bg_colors, (
            f"No background colors found in RichLog after search for '{query}'. "
            f"matches={app._preview_search_matches[:5]}, "
            f"total_lines={len(preview.lines)}"
        )


@pytest.mark.asyncio
async def test_highlight_count_matches_search_results(fixture_env):
    """Number of highlighted lines must be >= number of matched messages."""
    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await _wait_sessions_loaded(app, pilot)
        await _select_first_session(app, pilot)

        if not app._preview_messages:
            pytest.skip("No messages")

        query = None
        for msg in app._preview_messages:
            words = [w for w in msg.get("text", "").split() if len(w) >= 2]
            if words:
                query = words[0]
                break
        if not query:
            pytest.skip("No query")

        searched = await _open_search_and_execute(app, pilot, query)
        assert searched

        if not app._preview_search_matches:
            pytest.skip(f"No matches for '{query}'")

        preview = app.query_one("#preview", RichLog)
        highlighted_lines = _richlog_count_highlighted_lines(preview)
        n_matches = len(app._preview_search_matches)

        # Each match has at least 1 highlighted line
        assert highlighted_lines >= n_matches, (
            f"Expected ≥{n_matches} highlighted lines, got {highlighted_lines}. "
            f"query={query!r}"
        )


@pytest.mark.asyncio
async def test_no_highlight_after_esc(fixture_env):
    """After Esc, RichLog must NOT have background-colored segments."""
    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await _wait_sessions_loaded(app, pilot)
        await _select_first_session(app, pilot)

        if not app._preview_messages:
            pytest.skip("No messages")

        query = None
        for msg in app._preview_messages:
            words = [w for w in msg.get("text", "").split() if len(w) >= 2]
            if words:
                query = words[0]
                break
        if not query:
            pytest.skip("No query")

        searched = await _open_search_and_execute(app, pilot, query)
        assert searched

        if not app._preview_search_matches:
            pytest.skip("No matches")

        # Verify highlights are present before Esc
        preview = app.query_one("#preview", RichLog)
        bg_before = _richlog_collect_bg_colors(preview)
        assert bg_before, "No highlights before Esc (precondition failed)"

        # Press Esc
        await pilot.press("escape")
        await pilot.pause(0.3)

        # After Esc, no background color
        bg_after = _richlog_collect_bg_colors(preview)
        assert not bg_after, (
            f"Background colors still present after Esc: {bg_after}"
        )


@pytest.mark.asyncio
async def test_large_session_highlight_applied(tmp_path, monkeypatch):
    """For >30-message session, highlights must appear even for late-batch matches.

    Specifically tests that matches beyond the first batch (index > 30) are
    highlighted — this is the race-condition regression test.
    """
    import json
    import uuid as _uuid
    import kiro_history as kh
    import session_store as ss

    N = 90  # 3 batches of 30
    KEYWORD = "하이라이트검증키워드"

    session_id = str(_uuid.uuid4())
    session_dir = tmp_path / "chats"
    session_dir.mkdir(parents=True, exist_ok=True)
    session_file = session_dir / f"{session_id}.jsonl"

    # Put keyword ONLY in messages 60-89 (3rd batch only)
    expected_matches = 0
    file_lines = []
    for i in range(N):
        if i >= 60:  # only in 3rd batch
            text = f"{KEYWORD} 메시지 {i}"
            expected_matches += 1
        else:
            text = f"일반 메시지 {i}"
        kind = "Prompt" if i % 2 == 0 else "AssistantMessage"
        file_lines.append(json.dumps({
            "kind": kind,
            "data": {"content": [{"kind": "text", "data": text}]}
        }))
    session_file.write_text("\n".join(file_lines), encoding="utf-8")

    synthetic = {
        "session_id": session_id,
        "title": "Highlight Race Condition Test",
        "cwd": str(tmp_path),
        "msg_count": N,
        "jsonl_path": str(session_file),
        "source": "jsonl",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T01:00:00",
        "duration_min": 60,
    }

    monkeypatch.setattr(kh, "get_sessions", lambda: [synthetic])
    monkeypatch.setattr(ss, "get_sessions", lambda: [synthetic])

    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        # Wait for session
        start = time.monotonic()
        while time.monotonic() - start < LOAD_TIMEOUT:
            await pilot.pause(POLL)
            items = [c for c in app.query_one("#session-list", ListView).children
                     if isinstance(c, SessionItem)]
            if items and items[0].session.get("session_id") == session_id:
                break
        assert items

        # Select
        lv = app.query_one("#session-list", ListView)
        lv.focus()
        await pilot.press("j")

        # Wait for first batch
        start = time.monotonic()
        while time.monotonic() - start < LOAD_TIMEOUT:
            await pilot.pause(POLL)
            if (app.selected_session and
                    app.selected_session.get("session_id") == session_id and
                    len(app._preview_messages) > 0):
                break

        assert app.selected_session.get("session_id") == session_id
        first_batch = len(app._preview_messages)
        assert 0 < first_batch <= 30
        # First batch has NO keyword matches
        assert not app._preview_all_loaded

        # Search
        searched = await _open_search_and_execute(app, pilot, KEYWORD, timeout=15.0)
        assert searched, (
            f"Search timed out. executed={app._preview_search_executed!r} "
            f"msgs={len(app._preview_messages)}"
        )

        # All messages loaded
        assert len(app._preview_messages) == N
        assert len(app._preview_search_matches) == expected_matches

        # All matches are in 3rd batch (index >= 60)
        assert all(idx >= 60 for idx in app._preview_search_matches), (
            f"Expected all matches >= 60, got {app._preview_search_matches}"
        )

        # CORE: RichLog must have background color (highlights from 3rd batch)
        preview = app.query_one("#preview", RichLog)
        bg_colors = _richlog_collect_bg_colors(preview)
        assert bg_colors, (
            f"No background colors in RichLog! "
            f"matches={app._preview_search_matches}, "
            f"total_lines={len(preview.lines)}. "
            f"Race condition: 3rd-batch highlights were overwritten by _render_messages."
        )

        # Highlighted line count must match expected matches
        highlighted = _richlog_count_highlighted_lines(preview)
        assert highlighted >= expected_matches, (
            f"Expected ≥{expected_matches} highlighted lines, got {highlighted}"
        )
