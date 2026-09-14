"""Integration test: Large session highlight search."""
import sys
import time
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import session_store
from kiro_history import KiroHistory, SessionItem
from textual.widgets import Input, ListView, RichLog, Static

LOAD_TIMEOUT = 10.0
SEARCH_TIMEOUT = 20.0
POLL = 0.05

# Use portable fixture
FIXTURE_NAME = "int-large"


def _get_spec():
    from tests.fixtures.integration_sessions import INTEGRATION_SESSIONS
    return INTEGRATION_SESSIONS[FIXTURE_NAME]


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
async def test_large_session_highlight():
    """Test highlight search in large session (800+ messages)."""
    spec = _get_spec()
    session_prefix = spec["session_id"][:12]
    query = spec["search_term"]
    expected_matches = spec["expected_matches"]
    
    sessions = session_store.get_sessions()
    target = next((s for s in sessions if s.get('session_id','').startswith(session_prefix)), None)
    if not target:
        pytest.skip(f"Fixture session {session_prefix} not found")
    
    msgs = session_store.extract_messages(target, limit=None)
    print(f"Session has {len(msgs)} messages")
    
    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 50)) as pilot:
        await _wait_sessions(app, pilot)
        
        lv = app.query_one("#session-list", ListView)
        lv.focus()
        
        # Find and select the target session
        for i in range(10):
            await pilot.press("j")
            await pilot.pause(0.1)
            if (app.selected_session and 
                app.selected_session.get('session_id','').startswith(session_prefix)):
                break
        
        if not app.selected_session or not app.selected_session.get('session_id','').startswith(session_prefix):
            pytest.skip(f"Could not select session {session_prefix}")
        
        await pilot.pause(0.5)
        
        # Open search
        rl = app.query_one("#preview", RichLog)
        rl.focus()
        await pilot.pause(0.1)
        
        await pilot.press("ctrl+f")
        await pilot.pause(0.5)
        
        from kiro_history import PreviewSearchInput
        search_input = app.query_one(PreviewSearchInput)
        search_input.value = query
        await pilot.press("enter")
        
        # Wait for search (may take longer for large sessions)
        start = time.monotonic()
        while time.monotonic() - start < SEARCH_TIMEOUT:
            await pilot.pause(POLL)
            if app._preview_search_executed == query and app._preview_all_loaded:
                break
        
        assert len(app._preview_search_matches) == expected_matches, (
            f"Expected {expected_matches} matches, got {len(app._preview_search_matches)}"
        )
        
        # Verify highlights
        bg_colors = _richlog_collect_bg_colors(rl)
        
        highlighted_lines = _richlog_count_highlighted_lines(rl)
        
        assert highlighted_lines > 0, (
            f"No highlighted lines found!\n"
            f"BG colors: {bg_colors}\n"
            f"matches={app._preview_search_matches}"
        )
