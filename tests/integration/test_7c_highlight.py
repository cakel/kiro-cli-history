"""7c1632f6 세션 lge.com 검색 후 하이라이트 + 스크롤 검증."""
import sys
import time
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import session_store
from kiro_history import KiroHistory, SessionItem
from textual.widgets import Input, ListView, RichLog, Static

LOAD_TIMEOUT = 10.0
SEARCH_TIMEOUT = 15.0
POLL = 0.05

SESSION_PREFIX = "7c1632f6"
QUERY = "lge.com"


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
async def test_7c1632f6_lge_com_highlight():
    """117-message session: 'lge.com' search highlight verification."""
    sessions = session_store.get_sessions()
    target = next((s for s in sessions if s.get('session_id','').startswith(SESSION_PREFIX)), None)
    if not target:
        pytest.skip(f"Session {SESSION_PREFIX} not found")

    all_msgs = session_store.extract_messages(target, limit=None)
    expected = [i for i,m in enumerate(all_msgs) if QUERY in m.get('text','').lower()]
    print(f"\nExpected {len(expected)} matches: {expected}")

    app = KiroHistory()
    async with app.run_test(headless=True, size=(160, 50)) as pilot:
        await _wait_sessions(app, pilot)

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

        start = time.monotonic()
        while time.monotonic() - start < LOAD_TIMEOUT:
            await pilot.pause(POLL)
            if (app.selected_session and
                app.selected_session.get('session_id','').startswith(SESSION_PREFIX) and
                len(app._preview_messages) > 0):
                break

        first_batch = len(app._preview_messages)
        print(f"First batch: {first_batch}, all_loaded: {app._preview_all_loaded}")
        print(f"Selected session: {app.selected_session.get('session_id')[:8] if app.selected_session else None}")
        print(f"Expected: {SESSION_PREFIX}")
        
        # Debug: first message text
        if app._preview_messages:
            first_msg_text = app._preview_messages[0].get('text', '')[:60]
            print(f"First msg text: {first_msg_text!r}")
        
        # Debug: what does extract_messages return inside the app context?
        from kiro_history import extract_messages as app_extract
        app_msgs = app_extract(app.selected_session, limit=None)
        print(f"App extract_messages(limit=None): {len(app_msgs)} msgs")
        
        # Compare with direct session_store call
        import session_store as ss
        ss_msgs = ss.extract_messages(app.selected_session, limit=None)
        print(f"session_store.extract_messages(limit=None): {len(ss_msgs)} msgs")
        
        # First message from extract_messages
        if app_msgs:
            print(f"extract first msg: {app_msgs[0].get('text','')[:60]!r}")

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

        assert app._preview_search_executed == QUERY, f"Search timed out, executed={app._preview_search_executed!r}"
        print(f"After search: {len(app._preview_messages)} msgs, {len(app._preview_search_matches)} matches")
        print(f"Match indices: {app._preview_search_matches}")

        # 전체 로드 확인
        assert app._preview_all_loaded, "_preview_all_loaded is False"
        assert len(app._preview_messages) == len(all_msgs), (
            f"Expected {len(all_msgs)}, got {len(app._preview_messages)}"
        )

        # 매칭 수 확인
        assert len(app._preview_search_matches) == len(expected), (
            f"Expected {len(expected)} matches, got {len(app._preview_search_matches)}"
        )

        # RichLog에 배경색 확인
        preview = app.query_one("#preview", RichLog)
        bg_colors = _richlog_collect_bg_colors(preview)
        hl_lines = _richlog_count_highlighted_lines(preview)
        print(f"BG colors: {bg_colors}")
        print(f"Total lines: {len(preview.lines)}, highlighted: {hl_lines}")

        assert bg_colors, "No background colors in RichLog!"
        assert hl_lines >= len(expected), (
            f"Expected ≥{len(expected)} highlighted lines, got {hl_lines}"
        )

        # 스크롤 위치 확인: _preview_msg_line_offsets에 첫 매칭(idx=0)이 있어야
        offsets = app._preview_msg_line_offsets
        assert 0 in offsets, f"No offset for msg 0. Keys: {sorted(offsets.keys())[:10]}"
        scroll_y = offsets[0]
        print(f"Scroll y for first match (idx=0): {scroll_y}")

        # scroll_y 근처에 하이라이트가 있어야
        found = False
        for ln in range(scroll_y, min(scroll_y + 30, len(preview.lines))):
            for seg in preview.lines[ln]:
                if seg.style and seg.style.bgcolor:
                    found = True
                    break
            if found:
                break
        assert found, f"No highlight near scroll_y={scroll_y}"

        print("✓ All checks passed")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_7c1632f6_lge_com_highlight())
