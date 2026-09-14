"""
실제 87009c52 세션(757개 메시지)을 사용해서 '전체' 검색 시
_preview_messages가 전체 로드되고 3번째 매칭이 포함되는지 검증.
"""
import sys
import time
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import session_store
from kiro_history import KiroHistory, SessionItem
from textual.widgets import Input, ListView, RichLog, Static

LOAD_TIMEOUT = 15.0
SEARCH_TIMEOUT = 30.0  # 757개 로드는 느릴 수 있음
POLL = 0.05
SESSION_PREFIX = "87009c52"
QUERY = "전체"


async def _wait_sessions_loaded(app, pilot, timeout=LOAD_TIMEOUT):
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        await pilot.pause(POLL)
        text = str(app.query_one("#status-bar", Static).content)
        if "sessions" in text and "Loading" not in text:
            return True
    return False


async def _type_preview_search(pilot, app, query: str, timeout=SEARCH_TIMEOUT):
    ps = app.query_one("#preview-search", Input)
    ps.value = ""
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


@pytest.mark.asyncio
async def test_real_session_search():
    """87009c52 (757 msgs) — '전체' 검색 시 전체 매칭 로드 검증."""
    # 실제 세션 데이터 사전 확인
    sessions = session_store.get_sessions()
    target = next((s for s in sessions if s.get('session_id','').startswith(SESSION_PREFIX)), None)
    if not target:
        pytest.skip(f"Session {SESSION_PREFIX} not found (integration test requires real data)")

    msgs_all = session_store.extract_messages(target, limit=None)
    expected_hits = [i for i,m in enumerate(msgs_all) if QUERY in m.get('text','').lower()]
    print(f"\nExpected: {len(expected_hits)} matches, indices: {expected_hits[:10]}")
    print(f"3rd match at idx={expected_hits[2]}")

    app = KiroHistory()
    async with app.run_test(headless=True, size=(160, 50)) as pilot:
        # 세션 로드 대기
        loaded = await _wait_sessions_loaded(app, pilot)
        assert loaded

        # 87009c52 세션 찾아 선택
        lv = app.query_one("#session-list", ListView)
        lv.focus()

        items = [c for c in lv.children if isinstance(c, SessionItem)]
        target_idx = None
        for i, item in enumerate(items):
            if item.session.get('session_id','').startswith(SESSION_PREFIX):
                target_idx = i
                break
        if target_idx is None:
            pytest.skip(f"Session {SESSION_PREFIX} not in list")

        for _ in range(target_idx):
            await pilot.press("j")
        await pilot.press("j")
        await pilot.pause(0.5)

        # 첫 배치 로드 대기
        start = time.monotonic()
        while time.monotonic() - start < LOAD_TIMEOUT:
            await pilot.pause(POLL)
            if (app.selected_session and
                app.selected_session.get('session_id','').startswith(SESSION_PREFIX) and
                len(app._preview_messages) > 0):
                break

        assert app.selected_session is not None
        first_batch = len(app._preview_messages)
        print(f"First batch: {first_batch} msgs")
        assert 0 < first_batch <= 30

        # Ctrl+F 검색바 열기
        app.query_one("#preview", RichLog).focus()
        await pilot.pause(POLL)
        await pilot.press("ctrl+f")
        start = time.monotonic()
        while time.monotonic() - start < 2.0:
            await pilot.pause(POLL)
            if app.query_one("#preview-search", Input).display:
                break

        # '전체' 검색
        searched = await _type_preview_search(pilot, app, QUERY)
        assert searched, (
            f"Search timed out. executed={app._preview_search_executed!r} "
            f"msgs={len(app._preview_messages)} all_loaded={app._preview_all_loaded}"
        )

        print(f"After search: {len(app._preview_messages)} msgs, {len(app._preview_search_matches)} matches")
        print(f"Match indices: {app._preview_search_matches[:10]}")

        # 전체 로드 확인
        assert app._preview_all_loaded
        assert len(app._preview_messages) == len(msgs_all), (
            f"Expected {len(msgs_all)} msgs, got {len(app._preview_messages)}"
        )

        # 매칭 수 확인
        assert len(app._preview_search_matches) == len(expected_hits), (
            f"Expected {len(expected_hits)} matches, got {len(app._preview_search_matches)}\n"
            f"Expected indices: {expected_hits[:10]}\n"
            f"Got indices: {app._preview_search_matches[:10]}"
        )

        # 3번째 매칭 포함 확인
        assert expected_hits[2] in app._preview_search_matches, (
            f"3rd match idx={expected_hits[2]} missing from matches"
        )

        # false negative 없음
        match_set = set(app._preview_search_matches)
        for i, msg in enumerate(app._preview_messages):
            if QUERY in msg.get('text','').lower():
                assert i in match_set, f"Message {i} has '{QUERY}' but not in matches"
