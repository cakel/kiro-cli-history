"""
4aa3b6f9 세션 (818 msgs) - '두 가지' 검색 시
RichLog에 실제로 하이라이트가 적용되는지 검증.
"""
import sys
import time
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import session_store
from kiro_history import KiroHistory, SessionItem
from textual.widgets import Input, ListView, RichLog, Static

LOAD_TIMEOUT = 10.0
SEARCH_TIMEOUT = 30.0
POLL = 0.05

SESSION_PREFIX = "4aa3b6f9"
QUERY = "두 가지"


def _richlog_collect_bg_colors(richlog):
    colors = set()
    for strip in richlog.lines:
        for segment in strip:
            if segment.style and segment.style.bgcolor:
                colors.add(str(segment.style.bgcolor))
    return colors


def _richlog_count_highlighted_lines(richlog):
    count = 0
    for strip in richlog.lines:
        for segment in strip:
            if segment.style and segment.style.bgcolor:
                count += 1
                break
    return count


async def _wait_sessions(app, pilot):
    start = time.monotonic()
    while time.monotonic() - start < LOAD_TIMEOUT:
        await pilot.pause(POLL)
        text = str(app.query_one("#status-bar", Static).content)
        if "sessions" in text and "Loading" not in text:
            return True
    return False


@pytest.mark.asyncio
async def test_large_real_session_highlight():
    """818-message session: '두 가지' search must produce highlighted lines in RichLog."""
    sessions = session_store.get_sessions()
    target = next((s for s in sessions if s.get('session_id','').startswith(SESSION_PREFIX)), None)
    if not target:
        pytest.skip(f"Session {SESSION_PREFIX} not found")

    all_msgs = session_store.extract_messages(target, limit=None)
    expected = [i for i,m in enumerate(all_msgs) if QUERY in m.get('text','')]
    print(f"\nExpected {len(expected)} matches, in first 30: {[i for i in expected if i<30]}")

    app = KiroHistory()
    async with app.run_test(headless=True, size=(160, 50)) as pilot:
        await _wait_sessions(app, pilot)

        # 세션 선택
        lv = app.query_one("#session-list", ListView)
        lv.focus()
        items = [c for c in lv.children if isinstance(c, SessionItem)]
        idx = next((i for i,item in enumerate(items)
                    if item.session.get('session_id','').startswith(SESSION_PREFIX)), None)
        if idx is None:
            pytest.skip("Session not in list")
        for _ in range(idx):
            await pilot.press("j")
        await pilot.press("j")
        await pilot.pause(0.5)

        # 첫 배치 대기
        start = time.monotonic()
        while time.monotonic() - start < LOAD_TIMEOUT:
            await pilot.pause(POLL)
            if (app.selected_session and
                app.selected_session.get('session_id','').startswith(SESSION_PREFIX) and
                len(app._preview_messages) > 0):
                break

        first_batch = len(app._preview_messages)
        print(f"First batch: {first_batch}")
        assert 0 < first_batch <= 30

        # 검색
        app.query_one("#preview", RichLog).focus()
        await pilot.pause(POLL)
        await pilot.press("ctrl+f")
        start = time.monotonic()
        while time.monotonic() - start < 2.0:
            await pilot.pause(POLL)
            if app.query_one("#preview-search", Input).display:
                break

        for ch in QUERY:
            await pilot.press(ch)
        await pilot.pause(POLL)
        await pilot.press("enter")

        start = time.monotonic()
        while time.monotonic() - start < SEARCH_TIMEOUT:
            await pilot.pause(POLL)
            if app._preview_search_executed == QUERY:
                break

        assert app._preview_search_executed == QUERY, "Search timed out"
        print(f"After search: {len(app._preview_messages)} msgs, {len(app._preview_search_matches)} matches")
        print(f"Match indices: {app._preview_search_matches}")

        # 전체 로드 확인
        assert app._preview_all_loaded
        assert len(app._preview_messages) == len(all_msgs), (
            f"Expected {len(all_msgs)}, got {len(app._preview_messages)}"
        )
        assert len(app._preview_search_matches) == len(expected), (
            f"Expected {len(expected)} matches, got {len(app._preview_search_matches)}"
        )

        # 핵심: RichLog에 배경색 확인
        preview = app.query_one("#preview", RichLog)
        bg_colors = _richlog_collect_bg_colors(preview)
        print(f"BG colors in RichLog: {bg_colors}")
        print(f"Total RichLog lines: {len(preview.lines)}")
        hl_lines = _richlog_count_highlighted_lines(preview)
        print(f"Highlighted lines: {hl_lines}")

        assert bg_colors, (
            f"NO background colors in RichLog after search!\n"
            f"matches={app._preview_search_matches}\n"
            f"total_lines={len(preview.lines)}\n"
            f"This means _render_messages overwrote the highlighted re-render."
        )
        assert hl_lines >= len(expected), (
            f"Expected ≥{len(expected)} highlighted lines, got {hl_lines}"
        )
