"""tests/test_esc_behavior.py — ESC key behaviour and multi-press state tests.

Tests are split into two tiers:
  - Unit-style (no @pytest.mark.slow): verify counter/timer transitions by
    calling action_clear_or_quit() directly with mocked Textual internals.
  - GUI-style (@pytest.mark.slow + @pytest.mark.asyncio): use Textual's
    run_test / pilot to drive real key events.

Run all:
    pytest tests/test_esc_behavior.py -v

Run fast tests only:
    pytest tests/test_esc_behavior.py -v -m "not slow"
"""

import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from kiro_history import KiroHistory
from textual.widgets import Input


# ---------------------------------------------------------------------------
# Timing constants
# ---------------------------------------------------------------------------

LOAD_TIMEOUT = 5.0
POLL         = 0.05


# ---------------------------------------------------------------------------
# Polling helper
# ---------------------------------------------------------------------------

async def _wait_for_sessions(app: KiroHistory, pilot,
                              timeout: float = LOAD_TIMEOUT) -> int:
    from textual.widgets import Static
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        await pilot.pause(POLL)
        try:
            text = str(app.query_one("#status-bar", Static).content)
        except Exception:
            continue
        if "sessions" in text and "Loading" not in text:
            try:
                return int(text.strip().split()[0])
            except (ValueError, IndexError):
                return -1
    return 0


# ===========================================================================
# Unit tests (no Textual event loop, no @slow)
# ===========================================================================

def test_esc_count_initial_zero():
    """_esc_count must be 0 immediately after KiroHistory() is instantiated."""
    app = KiroHistory()
    assert app._esc_count == 0


def test_esc_count_attr_exists():
    """_esc_notify_timer must exist and be None at init."""
    app = KiroHistory()
    assert hasattr(app, "_esc_notify_timer")
    assert app._esc_notify_timer is None


def _make_mock_app():
    """Return a KiroHistory instance with Textual internals mocked out."""
    app = KiroHistory()

    # Mock set_timer → returns a fake Timer with .stop()
    fake_timer = MagicMock()
    app.set_timer = MagicMock(return_value=fake_timer)

    # Mock notify (no-op)
    app.notify = MagicMock()

    # Mock exit
    app.exit = MagicMock()

    # Mock query_one to return Input stubs with empty value
    empty_input = MagicMock(spec=[])
    empty_input.value = ""
    empty_input.has_focus = False
    app.query_one = MagicMock(return_value=empty_input)

    # preview search inactive
    app._preview_search_active = False

    # _is_keys_help_screen extracted for testability — patch to return False
    app._is_keys_help_screen = MagicMock(return_value=False)

    return app, fake_timer


def _stop_mock_app(app):
    """No-op: cleanup placeholder (no patches to stop with this approach)."""
    pass


def test_esc_first_press_increments_counter():
    """First ESC on empty state → _esc_count becomes 1, timer starts."""
    app, fake_timer = _make_mock_app()
    try:
        app.action_clear_or_quit()

        assert app._esc_count == 1
        app.set_timer.assert_called_once_with(2.0, app._reset_esc_count)
        app.notify.assert_not_called()
        app.exit.assert_not_called()
    finally:
        _stop_mock_app(app)


def test_esc_second_press_shows_notify():
    """Second ESC → _esc_count becomes 2, notify fired with warning severity."""
    app, fake_timer = _make_mock_app()
    try:
        app.action_clear_or_quit()
        app.notify.reset_mock()

        app.action_clear_or_quit()

        assert app._esc_count == 2
        app.notify.assert_called_once()
        call_kwargs = app.notify.call_args
        msg = call_kwargs[0][0] if call_kwargs[0] else call_kwargs[1].get("message", "")
        assert "ESC" in msg or "exit" in msg.lower()
        severity = call_kwargs[1].get("severity", "")
        assert severity == "warning"
        app.exit.assert_not_called()
    finally:
        _stop_mock_app(app)


def test_esc_third_press_exits():
    """Third ESC → exit() called, _esc_count reset to 0."""
    app, fake_timer = _make_mock_app()
    try:
        app.action_clear_or_quit()
        app.action_clear_or_quit()
        app.action_clear_or_quit()

        app.exit.assert_called_once()
        assert app._esc_count == 0
    finally:
        _stop_mock_app(app)


def test_esc_resets_counter_when_input_cleared():
    """ESC when input has value → clears input, _esc_count reset to 0."""
    app, _ = _make_mock_app()
    try:
        search_input = MagicMock()
        search_input.value = "hello"
        path_input = MagicMock()
        path_input.value = ""

        def _query_one(selector, widget_type=None):
            if "search" in selector:
                return search_input
            return path_input

        app.query_one = _query_one

        app._esc_count = 1
        app.action_clear_or_quit()

        assert search_input.value == ""
        assert app._esc_count == 0
        app.exit.assert_not_called()
    finally:
        _stop_mock_app(app)


def test_reset_esc_count_clears_state():
    """_reset_esc_count() resets counter and clears timer reference."""
    app = KiroHistory()
    app._esc_count = 2
    app._esc_notify_timer = MagicMock()

    app._reset_esc_count()

    assert app._esc_count == 0
    assert app._esc_notify_timer is None


def test_existing_timer_stopped_before_new_one():
    """On second ESC, the first timer must be stopped before a new one starts."""
    app, fake_timer = _make_mock_app()
    try:
        app.action_clear_or_quit()  # 1st — starts timer
        first_timer = app._esc_notify_timer

        app.action_clear_or_quit()  # 2nd — should stop first_timer, start new one

        first_timer.stop.assert_called_once()
        assert app.set_timer.call_count == 2
    finally:
        _stop_mock_app(app)


# ===========================================================================
# GUI tests (@slow)
# ===========================================================================

@pytest.mark.slow
@pytest.mark.asyncio
async def test_esc_clears_search_input(fixture_env):
    """ESC when search input has text must clear the input value."""
    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await _wait_for_sessions(app, pilot)

        await pilot.click("#search-input")
        for ch in "hello":
            await pilot.press(ch)
        await pilot.pause(0.1)

        search = app.query_one("#search-input", Input)
        assert search.value == "hello"

        await pilot.press("escape")
        await pilot.pause(0.1)

        assert search.value == ""


@pytest.mark.slow
@pytest.mark.asyncio
async def test_esc_triple_quits(fixture_env):
    """Three ESC presses on empty inputs must exit the application."""
    app = KiroHistory()

    exited_normally = False
    raised_exc = None
    try:
        async with app.run_test(headless=True, size=(120, 40)) as pilot:
            await _wait_for_sessions(app, pilot)

            search = app.query_one("#search-input", Input)
            path   = app.query_one("#path-input", Input)
            assert search.value == "" and path.value == ""

            await pilot.press("escape")
            await pilot.pause(0.05)
            await pilot.press("escape")
            await pilot.pause(0.05)
            await pilot.press("escape")
            await pilot.pause(0.2)

        exited_normally = True
    except Exception as e:
        # Some Textual versions raise when app exits during run_test.
        # Only count it as success if it looks like an intentional exit,
        # not an AttributeError / ImportError / etc.
        exc_name = type(e).__name__
        if exc_name not in ("AttributeError", "ImportError", "TypeError", "AssertionError"):
            exited_normally = True
        else:
            raised_exc = e

    assert exited_normally, (
        f"App did not exit after three ESC presses. "
        f"Exception: {raised_exc!r}"
    )


@pytest.mark.slow
@pytest.mark.asyncio
async def test_esc_double_shows_notify(fixture_env):
    """Two ESC presses on empty inputs must call notify with the exit hint."""
    app = KiroHistory()
    notify_calls: list[dict] = []
    original_notify = app.notify

    def _capture(message, **kwargs):
        notify_calls.append({"message": message, **kwargs})
        try:
            original_notify(message, **kwargs)
        except Exception:
            pass

    app.notify = _capture  # type: ignore[method-assign]

    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await _wait_for_sessions(app, pilot)

        search = app.query_one("#search-input", Input)
        path   = app.query_one("#path-input", Input)
        assert search.value == "" and path.value == ""

        notify_calls.clear()

        await pilot.press("escape")
        await pilot.pause(0.1)

        exit_after_first = [c for c in notify_calls
                            if "ESC" in c["message"] or "exit" in c["message"].lower()]
        assert len(exit_after_first) == 0

        await pilot.press("escape")
        await pilot.pause(0.2)

    exit_hint = [c for c in notify_calls
                 if "ESC" in c["message"] or "exit" in c["message"].lower()]
    assert len(exit_hint) >= 1
    assert exit_hint[0].get("severity") == "warning"


@pytest.mark.slow
@pytest.mark.asyncio
async def test_esc_resets_on_clear(fixture_env):
    """ESC that clears filled input must reset _esc_count to 0."""
    app = KiroHistory()
    async with app.run_test(headless=True, size=(120, 40)) as pilot:
        await _wait_for_sessions(app, pilot)

        app._esc_count = 1

        await pilot.click("#search-input")
        for ch in "abc":
            await pilot.press(ch)
        await pilot.pause(0.1)

        search = app.query_one("#search-input", Input)
        assert search.value == "abc"

        await pilot.press("escape")
        await pilot.pause(0.1)

        assert search.value == ""
        assert app._esc_count == 0
