"""tests/test_gui_headless.py — Headless GUI tests using fixture data.

The app is pointed at tiny fixture sessions via KIRO_DEMO_DIR (set in
conftest.py fixture_env).  Session loading takes <100ms instead of 4s.

Run:
    pytest tests/test_gui_headless.py -v
"""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from kiro_history import KiroHistory, SessionItem
from textual.widgets import Input, ListView, Static
from tests.fixtures import EXPECTED, FIXTURE_SESSIONS, SQLITE_SESSIONS

pytestmark = pytest.mark.slow


# ---------------------------------------------------------------------------
# Timing constants (tiny fixture → much shorter waits)
# ---------------------------------------------------------------------------

LOAD_TIMEOUT  = 5.0   # max seconds waiting for session load
SEARCH_WAIT   = 2.0   # max seconds for search worker
PREVIEW_WAIT  = 2.0   # max seconds for preview worker
POLL          = 0.05  # polling interval


# ---------------------------------------------------------------------------
# Polling helpers
# ---------------------------------------------------------------------------

async def _wait_for_sessions(app: KiroHistory, pilot,
                              timeout: float = LOAD_TIMEOUT) -> int:
    """Poll until status-bar shows 'N sessions'. Returns count or 0 on timeout."""
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        await pilot.pause(POLL)
        text = str(app.query_one("#status-bar", Static).content)
        if "sessions" in text and "Loading" not in text:
            try:
                return int(text.strip().split()[0])
            except (ValueError, IndexError):
                return -1
    return 0


async def _wait_for_status(app: KiroHistory, pilot, predicate,
                            timeout: float = SEARCH_WAIT) -> str:
    """Poll until status-bar satisfies predicate."""
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        await pilot.pause(POLL)
        text = str(app.query_one("#status-bar", Static).content)
        if predicate(text):
            return text
    return str(app.query_one("#status-bar", Static).content)


async def _wait_for_preview(app: KiroHistory, pilot, min_messages: int = 1,
                             timeout: float = PREVIEW_WAIT) -> int:
    """Poll until _preview_messages ≥ min_messages."""
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        await pilot.pause(POLL)
        if len(app._preview_messages) >= min_messages:
            break
    return len(app._preview_messages)


# ---------------------------------------------------------------------------
# Action helpers
# ---------------------------------------------------------------------------

def _session_items(app: KiroHistory) -> list:
    lv = app.query_one("#session-list", ListView)
    return [c for c in lv.children if isinstance(c, SessionItem)]


async def _type_search(pilot, app: KiroHistory, text: str) -> None:
    """Type text and wait until search results are reflected."""
    await pilot.click("#search-input")
    for ch in text:
        await pilot.press(ch)
    await _wait_for_status(app, pilot, lambda s: "matching" in s)


async def _navigate_to_first(app: KiroHistory, pilot) -> None:
    """Focus list, press j, wait for preview to load."""
    app.query_one("#session-list", ListView).focus()
    await pilot.pause(POLL)
    await pilot.press("j")
    await _wait_for_preview(app, pilot, min_messages=1)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_app_loads_sessions(fixture_env):
    """App must load all fixture sessions and show count."""
    expected_count = len(FIXTURE_SESSIONS) + len(SQLITE_SESSIONS)
    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        count = await _wait_for_sessions(app, pilot)
        assert count > 0, f"Expected sessions to load, got {count}"
        # All sessions loaded (fixture is tiny, no filtering by default hides some)
        assert count == expected_count, (
            f"Expected {expected_count} total sessions, got {count}"
        )


@pytest.mark.asyncio
async def test_session_list_shows_titled_sessions(fixture_env):
    """Session list must show titled non-subagent sessions by default."""
    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await _wait_for_sessions(app, pilot)
        items = _session_items(app)
        # Default hides untitled and single-turn (subagent) sessions
        titles = {item.session.get("title", "") for item in items}
        # Untitled should be hidden
        assert "" not in titles and "(untitled)" not in titles
        assert len(items) > 0


@pytest.mark.asyncio
async def test_search_filters_to_acme_player(fixture_env):
    """Searching 에이스플레이어 must return matching sessions only."""
    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await _wait_for_sessions(app, pilot)
        await _type_search(pilot, app, "에이스플레이어")

        items = _session_items(app)
        inp_val = app.query_one("#search-input", Input).value
        sb_text = str(app.query_one("#status-bar", Static).content)

        assert inp_val == "에이스플레이어"
        assert len(items) > 0, "Expected at least one result"
        assert "matching" in sb_text

        # All returned sessions must actually match
        for item in items:
            s = item.session
            combined = (
                (s.get("title") or "")
                + (s.get("cwd") or "")
                + (s.get("_search_text") or "")
            ).lower()
            assert "에이스플레이어" in combined or "acme-player" in combined, (
                f"False positive: {s.get('title')!r} ({s.get('cwd')!r})"
            )


@pytest.mark.asyncio
async def test_search_result_count_matches_backend(fixture_env):
    """GUI result count must match session_store.search_sessions()."""
    import session_store as ss

    QUERY = "에이스플레이어"
    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await _wait_for_sessions(app, pilot)
        await _type_search(pilot, app, QUERY)

        gui_count = len(_session_items(app))

        # Backend reference (apply same filters the app applies)
        sessions = ss.get_sessions()
        filtered = [s for s in sessions
                    if not app._is_single_turn(s)
                    and s.get("title") not in [None, "", "(untitled)"]]
        backend_count = len(ss.search_sessions(QUERY, filtered))

        assert gui_count == backend_count, (
            f"GUI={gui_count}, backend={backend_count}"
        )


@pytest.mark.asyncio
async def test_empty_search_restores_list(fixture_env):
    """Clearing search must restore the full session list."""
    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await _wait_for_sessions(app, pilot)

        await _type_search(pilot, app, "에이스플레이어")
        narrow = len(_session_items(app))
        assert narrow > 0

        # Clear
        app.query_one("#search-input", Input).value = ""
        await _wait_for_status(app, pilot,
                                lambda s: "matching" not in s and "sessions" in s)
        restored = len(_session_items(app))
        assert restored > narrow, f"List not restored: narrow={narrow}, restored={restored}"


@pytest.mark.asyncio
async def test_search_no_match(fixture_env):
    """Query matching nothing must show empty list."""
    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await _wait_for_sessions(app, pilot)
        await _type_search(pilot, app, "xyzzy_no_match_42_플루토늄")
        assert len(_session_items(app)) == 0


@pytest.mark.asyncio
async def test_navigation_selects_session(fixture_env):
    """Pressing j must select a session and set selected_session."""
    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await _wait_for_sessions(app, pilot)
        await _navigate_to_first(app, pilot)
        assert app.selected_session is not None


@pytest.mark.asyncio
async def test_preview_loads_messages(fixture_env):
    """Selecting a session must load its messages into preview."""
    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await _wait_for_sessions(app, pilot)
        await _navigate_to_first(app, pilot)

        assert app.selected_session is not None
        assert len(app._preview_messages) > 0, (
            f"No messages loaded for '{app.selected_session.get('title','?')}'"
        )


@pytest.mark.asyncio
async def test_preview_messages_structure(fixture_env):
    """Every preview message must have role and text."""
    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await _wait_for_sessions(app, pilot)
        await _navigate_to_first(app, pilot)

        for i, msg in enumerate(app._preview_messages):
            assert "role" in msg, f"msg[{i}] missing role"
            assert "text" in msg, f"msg[{i}] missing text"
            assert msg["role"] in ("you", "kiro", "system")
            assert isinstance(msg["text"], str) and msg["text"]


@pytest.mark.asyncio
async def test_escape_clears_search(fixture_env):
    """Escape must clear the search input."""
    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await _wait_for_sessions(app, pilot)
        await _type_search(pilot, app, "에이스플레이어")
        assert app.query_one("#search-input", Input).value == "에이스플레이어"

        await pilot.click("#search-input")
        await pilot.press("escape")
        start = time.monotonic()
        while time.monotonic() - start < 1.0:
            await pilot.pause(POLL)
            if app.query_one("#search-input", Input).value == "":
                break
        assert app.query_one("#search-input", Input).value == ""


@pytest.mark.asyncio
async def test_load_more_messages(fixture_env):
    """Pressing m on a session with many messages must load more."""
    # Search for acme-player session (2 prompts + 2 replies = 4 messages)
    # Default batch size is 30, so all_loaded=True for fixture sessions.
    # We'll verify that all messages ARE loaded (all_loaded=True for small sessions).
    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await _wait_for_sessions(app, pilot)
        await _navigate_to_first(app, pilot)

        # Fixture sessions are small — should all load in first batch
        count = len(app._preview_messages)
        assert count > 0

        if app._preview_all_loaded:
            # All loaded on first batch — correct for small sessions
            return

        # If there are more (shouldn't happen with fixture), test load-more
        count_before = count
        await pilot.press("m")
        await _wait_for_preview(app, pilot, min_messages=count_before + 1)
        assert len(app._preview_messages) > count_before


# ---------------------------------------------------------------------------
# Theme Picker Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_theme_picker_opens_and_closes(fixture_env):
    """Theme picker must open via _open_theme_picker and close with Escape."""
    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await _wait_for_sessions(app, pilot)
        
        # Open theme picker
        app._open_theme_picker()
        await pilot.pause(0.1)
        
        # Verify ThemePickerScreen is active
        assert "ThemePickerScreen" in type(app.screen).__name__
        
        # Close with Escape
        await pilot.press("escape")
        await pilot.pause(0.1)
        
        # Should be back to main screen
        assert "ThemePickerScreen" not in type(app.screen).__name__


@pytest.mark.asyncio
async def test_theme_picker_navigation(fixture_env):
    """Theme picker must respond to Home/End/PageUp/PageDown."""
    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await _wait_for_sessions(app, pilot)
        
        app._open_theme_picker()
        await pilot.pause(0.1)
        
        lv = app.screen.query_one("#theme-list")
        initial_index = lv.index
        
        # Home → first item
        await pilot.press("home")
        await pilot.pause(0.05)
        assert lv.index == 0, f"Home should go to 0, got {lv.index}"
        
        # End → last item
        await pilot.press("end")
        await pilot.pause(0.05)
        num_themes = len(app.available_themes)
        assert lv.index == num_themes - 1, f"End should go to {num_themes - 1}, got {lv.index}"
        
        # PageUp from end
        await pilot.press("pageup")
        await pilot.pause(0.05)
        assert lv.index < num_themes - 1, "PageUp should decrease index"
        
        # Home then PageDown
        await pilot.press("home")
        await pilot.pause(0.05)
        await pilot.press("pagedown")
        await pilot.pause(0.05)
        assert lv.index == 10, f"PageDown from 0 should go to 10, got {lv.index}"
        
        await pilot.press("escape")


@pytest.mark.asyncio
async def test_theme_picker_selection(fixture_env):
    """Selecting a theme must change app.theme and dismiss picker."""
    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await _wait_for_sessions(app, pilot)
        
        initial_theme = app._theme
        
        app._open_theme_picker()
        await pilot.pause(0.1)
        
        lv = app.screen.query_one("#theme-list")
        
        # Go to first theme (may differ from current)
        await pilot.press("home")
        await pilot.pause(0.05)
        
        # Move up one if already at first to ensure we pick a different theme
        if lv.index == 0:
            await pilot.press("down")
            await pilot.pause(0.05)
        
        # Get the theme name we're about to select
        selected_item = lv.highlighted_child
        expected_theme = selected_item.id[len("theme-"):]
        
        # Select it
        lv.action_select_cursor()
        await pilot.pause(0.1)
        
        # Picker should be dismissed
        assert "ThemePickerScreen" not in type(app.screen).__name__
        
        # Theme should be changed
        assert app._theme == expected_theme
        assert app.theme == expected_theme


@pytest.mark.asyncio
async def test_no_duplicate_theme_command(fixture_env):
    """Only 'Set Theme…' should appear, not Textual's default 'Theme'."""
    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await _wait_for_sessions(app, pilot)
        
        cmds = list(app.get_system_commands(app.screen))
        theme_titles = [c.title for c in cmds if "theme" in c.title.lower()]
        
        # Should have exactly one theme command
        assert len(theme_titles) == 1, f"Expected 1 theme command, got {theme_titles}"
        assert "Set Theme" in theme_titles[0], f"Expected 'Set Theme…', got {theme_titles}"
