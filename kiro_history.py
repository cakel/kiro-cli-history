"""kiro-history: Fuzzy-search and browse Kiro CLI conversation history.

A terminal UI for searching, browsing, and resuming Kiro CLI sessions.
Reads from three stores (all read-only, never modifies session data):
  1. ~/.kiro/sessions/cli/*.json+jsonl        (v3: JSONL format, used by --classic mode)
  2. ~/Library/Application Support/kiro-cli/data.sqlite3 conversations_v2 (v2: SQLite, used by new TUI mode)
  3. ~/Library/Application Support/kiro-cli/data.sqlite3 conversations    (v1: SQLite, legacy)
"""

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.command import CommandPalette

# --- Data / search layer ---
from session_store import (
    SESSIONS_DIR,
    SQLITE_DB,
    MAX_FILE_SIZE,
    _sqlite_db_path,
    get_sessions,
    search_sessions,
    extract_messages,
    start_cache_prebuild,
)

# --- Config / logging ---
try:
    from config import load_config, save_config, DEFAULT_SETTINGS as _CONFIG_DEFAULTS
    from app_log import init_logging, log_perf, log_warn, log_error, close_logging
except ImportError:
    # Graceful degradation if modules not available
    _CONFIG_DEFAULTS = {"trust_all_tools": True, "show_single_turn": False, "show_untitled": False}
    def load_config(): return _CONFIG_DEFAULTS.copy()
    def save_config(s): return (False, "config module not available")
    def init_logging(): pass
    def log_perf(*a, **kw): pass
    def log_warn(*a, **kw): pass
    def log_error(*a, **kw): pass
    def close_logging(): pass

# --- Version ---

# Single source of truth: _version.py
# Injected at install time by install.sh / install.ps1
from _version import VERSION, _BUILT_VERSION, _BUILT_HASH

def _get_version_string() -> str:
    """Return version string: tag + short hash, always.

    Priority:
      1. _BUILT_VERSION/_BUILT_HASH injected at install time
      2. git describe/rev-parse from current repo (dev mode)
      3. VERSION constant (no git, no hash)
    """
    # 1. Use version/hash injected at install time
    if _BUILT_VERSION and _BUILT_HASH:
        return f"{_BUILT_VERSION}-{_BUILT_HASH}"
    if _BUILT_VERSION:
        return _BUILT_VERSION

    # 2. Try git (dev mode - running from repo)
    try:
        script_dir = Path(__file__).parent
        hash_result = subprocess.run(
            ["git", "-C", str(script_dir), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=2
        )
        if hash_result.returncode == 0:
            short_hash = hash_result.stdout.strip()
            tag = VERSION  # fallback if describe fails
            tag_result = subprocess.run(
                ["git", "-C", str(script_dir), "describe", "--tags", "--abbrev=0"],
                capture_output=True, text=True, timeout=2
            )
            if tag_result.returncode == 0:
                tag = tag_result.stdout.strip()
            return f"{tag}-{short_hash}"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    # 3. Fallback
    return VERSION

from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.message import Message
from textual.widgets import Footer, Header, Input, Static, ListView, ListItem, RichLog, Button
from rich.text import Text
from rich.markdown import Markdown


# --- UI Components (imported from widgets.py) ---
from widgets import PreviewSearchInput, RenameScreen, SessionItem

# --- Constants ---
PREVIEW_BATCH_SIZE = 30  # Messages per batch for lazy loading


class KiroHistory(App):
    """Kiro CLI session browser and search."""

    TITLE = f"kiro-cli-history ({_get_version_string()})"
    CSS = """
    Screen {
        layout: horizontal;
    }
    #left-pane {
        width: 2fr;
        min-width: 40;
        border-right: solid $accent;
    }
    #right-pane {
        width: 3fr;
        min-width: 50;
    }
    #search-input {
        dock: top;
        margin: 0 1;
    }
    #session-list {
        height: 1fr;
    }
    #preview {
        height: 1fr;
        padding: 0 1;
    }
    #preview:focus {
        border: solid $accent;
    }
    #preview-search {
        dock: top;
        display: none;
        margin: 1 1 0 1;
        border: tall $accent;
    }
    #preview-search:focus {
        border: tall $success;
    }
    #preview-search-info {
        dock: top;
        display: none;
        height: 1;
        background: $accent;
        color: $text;
        padding: 0 1;
    }
    #status-bar {
        dock: bottom;
        height: 1;
        background: $accent;
        color: $text;
        padding: 0 1;
    }
    SessionItem {
        padding: 0 1;
        height: 3;
    }
    SessionItem:hover {
        background: $boost;
    }
    ListView > SessionItem.-highlight {
        background: $accent;
    }
    """

    BINDINGS = [
        Binding("ctrl+r", "resume", "Resume session"),
        Binding("ctrl+n", "new_session", "New session"),
        Binding("ctrl+y", "copy_conversation", "Copy to clipboard"),
        Binding("ctrl+f", "open_preview_search", "Search preview", show=False),
        Binding("f2", "rename_session", "Rename"),
        Binding("escape", "clear_or_quit", "Clear / Quit"),
        Binding("ctrl+c", "quit", "Quit"),
        # Note: j/k/space/slash handled in on_key to avoid Input focus conflicts
        Binding("right", "focus_preview", "Preview", show=False),
        Binding("l", "focus_preview", "Preview", show=False),
        Binding("left", "focus_list", "List", show=False),
        Binding("h", "focus_list", "List", show=False),
        Binding("m", "load_more", "More", show=False),
    ]

    def __init__(self):
        super().__init__()
        self.all_sessions = []
        self.filtered_sessions = []
        self.selected_session = None
        # Load settings from config (or use defaults)
        cfg = load_config()
        self._trust_all_tools = cfg.get("trust_all_tools", _CONFIG_DEFAULTS["trust_all_tools"])
        self._show_single_turn = cfg.get("show_single_turn", _CONFIG_DEFAULTS["show_single_turn"])
        self._show_untitled = cfg.get("show_untitled", _CONFIG_DEFAULTS["show_untitled"])
        self._viewer_search_query = ""
        # Lazy loading state
        self._preview_messages = []  # Messages loaded so far
        self._preview_all_loaded = False  # Whether all messages are loaded
        self._preview_batch_size = PREVIEW_BATCH_SIZE
        self._preview_loading_session_id = None  # Guard for race condition
        self._sessions_loading = True  # Whether sessions are still loading
        self._search_id = 0  # Counter for search debounce
        # Preview in-pane search state
        self._preview_search_active = False  # Whether preview search bar is visible
        self._preview_search_query = ""      # Current input query (may not be searched yet)
        self._preview_search_executed = ""   # Query that was actually searched (results valid for this)
        self._preview_search_matches: list[int] = []  # Indices into _preview_messages
        self._preview_search_current = -1   # Current match index (-1 = no selection)
        self._preview_msg_line_offsets: dict[int, int] = {}  # msg_index → RichLog line number
        # Timing for perf logging
        self._start_time = None

    def get_system_commands(self, screen):
        """Add custom commands to the command palette."""
        from textual.app import SystemCommand
        yield from super().get_system_commands(screen)
        
        # Toggle --trust-all-tools
        trust_status = "ON" if self._trust_all_tools else "OFF"
        yield SystemCommand(
            f"Toggle --trust-all-tools (currently {trust_status})",
            "Enable/disable --trust-all-tools flag on resume/new",
            self._toggle_trust_all_tools
        )
        
        # Toggle single-turn sessions visibility
        single_turn_status = "shown" if self._show_single_turn else "hidden"
        yield SystemCommand(
            f"Toggle single-turn sessions (currently {single_turn_status})",
            "Show/hide sessions with only one exchange (hidden by default)",
            self._toggle_single_turn
        )
        
        # Toggle untitled sessions visibility
        untitled_status = "shown" if self._show_untitled else "hidden"
        untitled_count = sum(1 for s in self.all_sessions if s.get("title") in [None, "", "(untitled)"])
        yield SystemCommand(
            f"Toggle untitled sessions (currently {untitled_status}, {untitled_count} sessions)",
            "Show/hide sessions without a title",
            self._toggle_untitled
        )

        # --- Reset to Default Settings (bottom, separated) ---
        yield SystemCommand(
            "─── Reset to Default Settings",
            "Load kiro-cli-history.json and apply saved settings immediately",
            self._reset_to_saved_defaults
        )

    def _toggle_trust_all_tools(self) -> None:
        self._trust_all_tools = not self._trust_all_tools
        status = "enabled" if self._trust_all_tools else "disabled"
        self._apply_save_settings(f"--trust-all-tools {status}")

    def _toggle_single_turn(self) -> None:
        self._show_single_turn = not self._show_single_turn
        self._refresh_sessions()
        status = "shown" if self._show_single_turn else "hidden"
        self._apply_save_settings(f"Single-turn sessions {status}")

    def _toggle_untitled(self) -> None:
        self._show_untitled = not self._show_untitled
        self._refresh_sessions()
        status = "shown" if self._show_untitled else "hidden"
        self._apply_save_settings(f"Untitled sessions {status}")

    def _apply_save_settings(self, notify_msg: str) -> None:
        """Save current settings to config and notify user."""
        settings = {
            "trust_all_tools": self._trust_all_tools,
            "show_single_turn": self._show_single_turn,
            "show_untitled": self._show_untitled,
        }
        ok, err = save_config(settings)
        if ok:
            log_perf("config_save", **settings)
            self.notify(notify_msg, title="Settings", timeout=4)
        else:
            log_error("config_save_failed", error=err)
            self.notify(f"{notify_msg} (save failed: {err})", title="Settings", severity="warning", timeout=6)

    def _reset_to_saved_defaults(self) -> None:
        """Reset settings to DEFAULT_SETTINGS, apply immediately, persist to json."""
        self._trust_all_tools = _CONFIG_DEFAULTS["trust_all_tools"]
        self._show_single_turn = _CONFIG_DEFAULTS["show_single_turn"]
        self._show_untitled = _CONFIG_DEFAULTS["show_untitled"]
        # Refresh session list (applies new single-turn / untitled filters)
        self._refresh_sessions()
        # Update status bar to reflect new session count
        filtered = self._get_filtered_base()
        self.query_one("#status-bar", Static).update(
            f" {len(filtered)} sessions | Ctrl+R resume | / search | Ctrl+P menu"
        )
        # Persist so next startup also uses defaults
        save_config({
            "trust_all_tools": self._trust_all_tools,
            "show_single_turn": self._show_single_turn,
            "show_untitled": self._show_untitled,
        })
        trust = "ON" if self._trust_all_tools else "OFF"
        single = "shown" if self._show_single_turn else "hidden"
        untitled = "shown" if self._show_untitled else "hidden"
        self.notify(
            f"trust-all-tools={trust}  single-turn={single}  untitled={untitled}",
            title="Reset to Default Settings",
            timeout=5,
        )

    # Table name allowlist for SQL injection prevention
    _SQL_TABLES = {
        "sqlite_v2": ("conversations_v2", "conversation_id"),
        "sqlite_v1": ("conversations", "key"),  # V1 uses key-value structure
    }

    def _update_session_title(self, session: dict, new_title: str) -> bool:
        """Update session title in the source file."""
        source = session.get("source")
        
        if source == "jsonl":
            # Update JSONL metadata file (atomic write)
            jsonl_path = session.get("jsonl_path")
            if not jsonl_path:
                return False
            json_path = str(Path(jsonl_path).with_suffix(".json"))
            temp_path = None
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                metadata["title"] = new_title
                # Atomic write: write to temp file, then rename
                import tempfile
                dir_path = os.path.dirname(json_path)
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", suffix=".json",
                    dir=dir_path, delete=False
                ) as tf:
                    json.dump(metadata, tf, ensure_ascii=False, indent=2)
                    temp_path = tf.name
                os.replace(temp_path, json_path)
                return True
            except Exception as e:
                # Clean up temp file if rename failed
                log_error("rename_jsonl_failed", session_id=session.get("session_id", ""), error=str(e))
                try:
                    if temp_path and os.path.exists(temp_path):
                        os.unlink(temp_path)
                except OSError:
                    pass
                return False
        
        elif source in self._SQL_TABLES:
            # Update SQLite database
            db_path = _sqlite_db_path()
            if not db_path or not os.path.exists(db_path):
                return False
            try:
                table, id_col = self._SQL_TABLES[source]
                with sqlite3.connect(db_path) as conn:
                    if source == "sqlite_v1":
                        # V1 uses key-value structure: key=cwd, value=JSON
                        # Query by cwd, not session_id
                        lookup_key = session.get("cwd", "")
                        if not lookup_key:
                            return False
                        row = conn.execute(
                            f"SELECT value FROM {table} WHERE {id_col} = ?",
                            (lookup_key,)
                        ).fetchone()
                        if not row:
                            return False
                        data = json.loads(row[0])
                        data["title"] = new_title
                        conn.execute(
                            f"UPDATE {table} SET value = ? WHERE {id_col} = ?",
                            (json.dumps(data), lookup_key)
                        )
                        conn.commit()
                    else:
                        # V2: update title in value JSON (same structure as V1)
                        # conversations_v2 has: key(cwd), conversation_id, value(JSON), created_at, updated_at
                        lookup_key = session.get("session_id", "")
                        if not lookup_key:
                            return False
                        row = conn.execute(
                            f"SELECT value FROM {table} WHERE {id_col} = ?",
                            (lookup_key,)
                        ).fetchone()
                        if not row:
                            return False
                        data = json.loads(row[0])
                        data["title"] = new_title
                        conn.execute(
                            f"UPDATE {table} SET value = ? WHERE {id_col} = ?",
                            (json.dumps(data), lookup_key)
                        )
                        conn.commit()
                return True
            except Exception as e:
                log_error("rename_sqlite_failed", session_id=session.get("session_id", ""), source=source, error=str(e))
                return False
        
        return False

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="left-pane"):
                yield Input(placeholder="Search sessions...", id="search-input")
                yield ListView(id="session-list")
            with Vertical(id="right-pane"):
                yield PreviewSearchInput(placeholder="Search in preview... (Esc to close)",
                                         id="preview-search")
                yield Static("", id="preview-search-info")
                yield RichLog(id="preview", wrap=True, highlight=True, markup=True)
        yield Static("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        import time
        self._start_time = time.perf_counter()
        # Show loading indicator in the list area and status bar
        list_view = self.query_one("#session-list", ListView)
        list_view.append(ListItem(Static("Loading sessions...", classes="loading-hint")))
        self.query_one("#status-bar", Static).update(" Loading sessions… | Ctrl+P menu available after load")
        # Load sessions in background (init_logging runs inside worker to avoid I/O blocking)
        self._load_sessions_async()

    @work(thread=True)
    def _load_sessions_async(self) -> None:
        """Load sessions in background thread."""
        import time
        # Init logging here (worker thread) to avoid blocking on_mount with I/O
        init_logging()
        t0 = time.perf_counter()
        try:
            sessions = get_sessions()
        except Exception as e:
            def mark_error():
                self._sessions_loading = False
            self.call_from_thread(mark_error)
            log_error("load_sessions_failed", error=str(e))
            self.call_from_thread(
                self.notify,
                f"Failed to load sessions: {e}",
                severity="error"
            )
            self.call_from_thread(
                self.query_one("#status-bar", Static).update,
                " Error loading sessions | Check permissions"
            )
            return
        
        load_time = time.perf_counter() - t0
        # Log app start with session count, load time, and current settings
        total_time = time.perf_counter() - self._start_time if self._start_time else load_time
        log_perf("app_start", version=VERSION, sessions=len(sessions), load_time=load_time, total_time=total_time,
                 trust_all_tools=self._trust_all_tools, show_single_turn=self._show_single_turn, show_untitled=self._show_untitled)
        
        # Update shared state on main thread to avoid race conditions
        def update_sessions():
            self.all_sessions = sessions
            self._sessions_loading = False
        self.call_from_thread(update_sessions)
        
        # Apply filters and populate list
        self.call_from_thread(self._refresh_sessions)
        self.call_from_thread(
            self.query_one("#status-bar", Static).update,
            f" {len(sessions)} sessions | Ctrl+R resume | / search | Ctrl+P menu"
        )
        self.call_from_thread(
            self.notify,
            f"{len(sessions)} sessions loaded",
            title="Ready",
            timeout=3,
        )
        # If user typed search query while loading, apply it now
        def apply_search():
            search = self.query_one("#search-input", Input)
            if search.value:
                self._search_id += 1
                self._do_search(search.value, self._search_id)
        self.call_from_thread(apply_search)
        # Kick off background cache prebuild so subsequent searches are instant
        start_cache_prebuild(sessions)

    def _populate_list(self, sessions):
        list_view = self.query_one("#session-list", ListView)
        list_view.clear()
        for session in sessions:
            list_view.append(SessionItem(session))

    # --- Search ---

    @on(Input.Changed, "#search-input")
    def on_search_changed(self, event: Input.Changed) -> None:
        # Don't search while sessions are still loading
        if self._sessions_loading:
            return
        # Increment search ID to invalidate stale results
        self._search_id += 1
        self._do_search(event.value, self._search_id)

    def on_key(self, event) -> None:
        """Handle key events for navigation."""
        search_input = self.query_one("#search-input", Input)
        list_view = self.query_one("#session-list", ListView)
        preview = self.query_one("#preview", RichLog)
        ps = self.query_one("#preview-search", Input)

        # --- Preview search bar is active ---
        if ps.has_focus:
            if event.key == "escape":
                event.prevent_default()
                event.stop()
                self._close_preview_search()
                return
            # Note: Shift+Tab (prev match) handled by PreviewSearchInput.PrevMatchRequested message
            # Ctrl+F again → next match
            if event.key == "ctrl+f":
                event.prevent_default()
                event.stop()
                self._preview_search_next()
                return
            return  # let all other keys be handled by Input normally

        # Skip special key handling when session search Input has focus
        if search_input.has_focus:
            # Only handle down/j to move to session list
            if event.key in ("down", "j"):
                event.prevent_default()
                event.stop()
                list_view.focus()
            return

        # Session list navigation: j/k for up/down
        if list_view.has_focus:
            # Skip if Command Palette is open — let it handle Enter
            if CommandPalette.is_open(self):
                return
            # Enter: move focus to preview
            if event.key == "enter":
                event.prevent_default()
                event.stop()
                preview.focus()
                return
            # Shift+Enter: stay in list (no-op, just prevent default select behavior)
            if event.key == "shift+enter":
                event.prevent_default()
                event.stop()
                return
            if event.key == "j":
                event.prevent_default()
                event.stop()
                list_view.action_cursor_down()
                return
            if event.key == "k":
                if list_view.index == 0 or len(list_view.children) == 0:
                    event.prevent_default()
                    event.stop()
                    search_input.focus()
                else:
                    event.prevent_default()
                    event.stop()
                    list_view.action_cursor_up()
                return
            # space to load more (only in session list, not in ListView default toggle)
            if event.key == "space":
                event.prevent_default()
                event.stop()
                self.action_load_more()
                return

        # Preview pane: left/h moves back to session list
        if preview.has_focus:
            if event.key in ("left", "h"):
                event.prevent_default()
                event.stop()
                list_view.focus()
                return
            # space to load more in preview pane too
            if event.key == "space":
                event.prevent_default()
                event.stop()
                self.action_load_more()
                return
            # Page Down: scroll down, auto-load more if near bottom
            if event.key == "pagedown":
                event.prevent_default()
                event.stop()
                preview.scroll_page_down()
                # Auto-load more when scrolled near bottom
                if not self._preview_all_loaded:
                    max_scroll = preview.virtual_size.height - preview.size.height
                    if max_scroll > 0 and preview.scroll_y >= max_scroll - 10:
                        self.action_load_more()
                return
            # Page Up: scroll up
            if event.key == "pageup":
                event.prevent_default()
                event.stop()
                preview.scroll_page_up()
                return
            # Home: scroll to top
            if event.key == "home":
                event.prevent_default()
                event.stop()
                preview.scroll_home()
                return
            # End: scroll to bottom, load all remaining messages first
            if event.key == "end":
                event.prevent_default()
                event.stop()
                if not self._preview_all_loaded:
                    self._load_all_then_scroll_end()
                else:
                    preview.scroll_end()
                return
            # n/N: next/prev match when search has been executed
            if self._preview_search_executed:
                if event.key == "n":
                    event.prevent_default()
                    event.stop()
                    self._preview_search_next()
                    return
                if event.key == "N":
                    event.prevent_default()
                    event.stop()
                    self._preview_search_prev()
                    return

        # / to focus search (only when not in Input)
        if event.key == "slash":
            event.prevent_default()
            event.stop()
            search_input.focus()
            return

    @work(thread=True)
    def _do_search(self, query: str, search_id: int = 0) -> None:
        import time
        t0 = time.perf_counter()
        # Search within currently filtered base (respects single-turn/untitled toggles)
        base = self._get_filtered_base()
        results = search_sessions(query, base)
        search_time = time.perf_counter() - t0
        
        # Check if this search is still current (not superseded by newer search)
        if search_id and self._search_id != search_id:
            return  # Stale result, discard
        
        # Log search performance (only for non-stale results)
        cache_status = "warm" if any(s.get("_search_text") is not None for s in base[:10]) else "cold"
        log_perf("search", query_len=len(query), results=len(results), time=search_time, cache=cache_status)
        
        # Update filtered_sessions on main thread to avoid race condition
        def update_results():
            # Double-check search_id on main thread
            if search_id and self._search_id != search_id:
                return
            self.filtered_sessions = results
            self._populate_list(results)
            status_text = f" {len(results)}/{len(self.all_sessions)} sessions"
            if query:
                status_text += f" matching '{query}'"
            status_text += " | Ctrl+R resume | / search"
            self.query_one("#status-bar", Static).update(status_text)
        
        self.call_from_thread(update_results)

    # --- Preview ---

    @on(ListView.Highlighted, "#session-list")
    def on_session_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item is None:
            return
        # Skip non-session items (e.g., "Loading sessions..." placeholder)
        if not isinstance(event.item, SessionItem):
            return
        session = event.item.session
        self.selected_session = session
        self._preview_loading_session_id = session.get("session_id")
        # Always clear all preview state when switching sessions
        self._preview_messages = []
        self._preview_all_loaded = False
        self._preview_search_active = False
        self._preview_search_query = ""
        self._preview_search_executed = ""
        self._preview_search_matches = []
        self._preview_search_current = -1
        self._preview_msg_line_offsets = {}
        ps = self.query_one("#preview-search", Input)
        ps.value = ""
        ps.display = False
        self.query_one("#preview-search-info", Static).display = False
        self._load_preview(session)

    @work(thread=True)
    def _load_preview(self, session: dict) -> None:
        # Guard: if another session was selected while loading, abort
        session_id = session.get("session_id")
        if self._preview_loading_session_id != session_id:
            return

        preview = self.query_one("#preview", RichLog)
        self.call_from_thread(preview.clear)

        # Header
        title = session.get("title") or "(untitled)"
        cwd = session.get("cwd") or ""
        # Escape Rich markup characters
        title = title.replace("[", "\\[").replace("]", "\\]")
        cwd = cwd.replace("[", "\\[").replace("]", "\\]")
        created = (session.get("created_at") or "")[:19].replace("T", " ")
        updated = (session.get("updated_at") or "")[:19].replace("T", " ")
        msgs = session.get("msg_count", 0)
        dur = session.get("duration_min", 0)
        dur_str = "-" if dur == 0 else (f"{dur}m" if dur < 60 else f"{dur // 60}h {dur % 60}m")

        header = (
            f"[bold]SESSION:[/bold] {title}\n"
            f"[bold]DIRECTORY:[/bold] {cwd}\n"
            f"[bold]CREATED:[/bold] {created}\n"
            f"[bold]UPDATED:[/bold] {updated}\n"
            f"[bold]MESSAGES:[/bold] {msgs}\n"
            f"[bold]DURATION:[/bold] {dur_str}\n"
            f"[bold]ID:[/bold] {session.get('session_id', '')}\n"
        )
        
        # Recheck guard after expensive operations
        if self._preview_loading_session_id != session_id:
            return
            
        self.call_from_thread(preview.write, Text.from_markup(header))
        self.call_from_thread(preview.write, Text("-" * 50))
        self.call_from_thread(preview.write, Text(""))

        # Lazy loading: extract only first batch initially
        messages = extract_messages(session, limit=self._preview_batch_size)
        all_loaded = len(messages) < self._preview_batch_size

        # Final guard before updating shared state
        if self._preview_loading_session_id != session_id:
            return
        
        # Update shared state on main thread to avoid race conditions
        def update_preview_state():
            if self._preview_loading_session_id != session_id:
                return
            # Don't overwrite if all messages already loaded (e.g. by search)
            # Also don't overwrite if search is in progress
            if not self._preview_all_loaded and not self._preview_search_query:
                self._preview_messages = messages
                self._preview_all_loaded = all_loaded
        self.call_from_thread(update_preview_state)

        if not messages:
            self.call_from_thread(preview.write, Text("(no conversation data)"))
            return

        # Render first batch
        self.call_from_thread(self._render_messages, messages)

        # Show "load more" hint if there might be more messages
        total_msgs = session.get("msg_count", 0)
        if not all_loaded and total_msgs > len(messages):
            remaining = total_msgs - len(messages)
            self.call_from_thread(preview.write, Text.from_markup(
                f"[dim]--- ~{remaining} more messages. Press [bold]m[/bold] or [bold]space[/bold] to load more ---[/dim]"
            ))

    def _render_messages(self, messages: list) -> None:
        """Render a list of messages to preview (incremental append).
        
        Skipped if search has already done a full re-render (_preview_search_executed).
        """
        # If search is active (query entered or executed), don't append raw
        # unhighlighted messages on top of the re-rendered view
        if self._preview_search_query or self._preview_search_executed:
            return
        preview = self.query_one("#preview", RichLog)
        for msg in messages:
            role = msg["role"]
            txt = msg["text"]
            if role == "you":
                label = Text.from_markup("[bold cyan][YOU]:[/bold cyan]")
            else:
                label = Text.from_markup("[bold green][KIRO]:[/bold green]")
            preview.write(label)
            if role == "kiro":
                try:
                    preview.write(Markdown(txt))
                except Exception:
                    preview.write(Text(txt))
            else:
                preview.write(Text(txt))
            preview.write(Text(""))

    # --- Actions ---

    def _refresh_sessions(self) -> None:
        """Refresh session list with current filter settings."""
        filtered = self._get_filtered_base()
        self.filtered_sessions = filtered
        search = self.query_one("#search-input", Input)
        if search.value:
            # Apply search with proper search_id for debounce
            self._search_id += 1
            self._do_search(search.value, self._search_id)
        else:
            self._populate_list(self.filtered_sessions)

    def _get_filtered_base(self) -> list:
        """Return sessions after applying single-turn and untitled filters."""
        filtered = self.all_sessions

        # Filter single-turn sessions (subagent sessions or very few messages)
        if not self._show_single_turn:
            filtered = [s for s in filtered if not self._is_single_turn(s)]

        # Filter untitled sessions
        if not self._show_untitled:
            filtered = [
                s for s in filtered
                if s.get("title") not in [None, "", "(untitled)"]
            ]

        return filtered

    def _is_single_turn(self, session: dict) -> bool:
        """Check if a session has only a single exchange (one prompt, one response).

        Uses msg_count with source-aware thresholds:
        - JSONL: msg_count counts individual Prompt + AssistantMessage lines
                 so 1-turn = 2. Single-turn threshold: <= 2.
                 Also catches subagents via parent_session_id.
        - SQLite: msg_count = len(history), 1-turn = 1.
                  Single-turn threshold: <= 1.
        """
        source = session.get("source", "")
        msg_count = session.get("msg_count", 0)

        if source == "jsonl":
            # JSONL: parent_session_id is the reliable subagent indicator
            if session.get("parent_session_id"):
                return True
            # 1-turn JSONL = Prompt(1) + AssistantMessage(1) = 2
            return msg_count <= 2
        else:
            # SQLite v2: is_subagent derived from history content
            # (catches multi-turn subagents that msg_count<=1 would miss)
            if session.get("is_subagent"):
                return True
            # SQLite: 1 history entry = 1 full exchange
            return msg_count <= 1

    def action_rename_session(self) -> None:
        """Rename the selected session (F2)."""
        if not self.selected_session:
            self.notify("No session selected", severity="warning")
            return
        
        current_title = self.selected_session.get("title") or ""
        
        def handle_rename(new_title):
            if new_title:
                if self._update_session_title(self.selected_session, new_title):
                    self.selected_session["title"] = new_title
                    display = new_title[:50] + ("..." if len(new_title) > 50 else "")
                    self.notify(f"Renamed to: {display}")
                    # Refresh the list to show new title
                    self._populate_list(self.filtered_sessions)
                else:
                    self.notify("Failed to rename session", severity="error")
        
        self.push_screen(RenameScreen(current_title), handle_rename)

    def action_resume(self) -> None:
        if not self.selected_session:
            return
        session_id = self.selected_session.get("session_id", "")
        if not session_id:
            log_warn("resume_no_id", title=self.selected_session.get("title", ""))
            self.notify("Cannot resume: session has no ID", severity="error")
            return
        cwd = self.selected_session.get("cwd", "")
        if not cwd or not os.path.isdir(cwd):
            log_warn("resume_dir_not_found", session_id=session_id, cwd=cwd)
            self.notify(f"Directory not found: {cwd}", severity="error")
            return
        log_perf("resume", session_id=session_id)
        self.exit(result=("resume", self.selected_session, self._trust_all_tools))

    def action_new_session(self) -> None:
        """Start a new kiro-cli session in the current directory."""
        log_perf("new_session")
        self.exit(result=("new", None, self._trust_all_tools))

    def action_focus_search(self) -> None:
        self.query_one("#search-input", Input).focus()

    def action_clear_or_quit(self) -> None:
        # Close preview search first if active
        if self._preview_search_active:
            self._close_preview_search()
            return
        search = self.query_one("#search-input", Input)
        if search.value:
            search.value = ""
            search.focus()
        else:
            self.exit()

    def action_cursor_down(self) -> None:
        self.query_one("#session-list", ListView).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#session-list", ListView).action_cursor_up()

    def action_focus_preview(self) -> None:
        """Focus the preview pane for scrolling."""
        self.query_one("#preview", RichLog).focus()

    def action_focus_list(self) -> None:
        """Focus back to the session list."""
        self.query_one("#session-list", ListView).focus()

    def action_load_more(self) -> None:
        """Load more messages in preview (lazy loading)."""
        if not self.selected_session:
            return
        if self._preview_all_loaded:
            self.notify("All messages loaded", severity="information")
            return
        # Don't manually load more while search is loading all messages
        if self._preview_search_query and not self._preview_search_executed:
            return
        self._load_more_messages()

    @work(thread=True)
    def _load_more_messages(self) -> None:
        """Load next batch of messages from the session file."""
        session = self.selected_session
        if not session:
            return

        # Guard: if another session was selected, abort
        session_id = session.get("session_id")
        if self._preview_loading_session_id != session_id:
            return

        # Calculate how many we need to skip (offset)
        skip = len(self._preview_messages)

        # Use offset parameter to skip already-loaded messages
        new_msgs = extract_messages(session, limit=self._preview_batch_size, offset=skip)

        # Recheck guard after file I/O
        if self._preview_loading_session_id != session_id:
            return

        if not new_msgs:
            def mark_all_loaded():
                self._preview_all_loaded = True
            self.call_from_thread(mark_all_loaded)
            self.call_from_thread(self.notify, "All messages loaded", severity="information")
            return

        # Check if this is the last batch
        is_last_batch = len(new_msgs) < self._preview_batch_size
        
        # Update shared state on main thread
        def update_state():
            if self._preview_loading_session_id != session_id:
                return
            self._preview_messages.extend(new_msgs)
            self._preview_all_loaded = is_last_batch
            # Re-run preview search to include newly loaded messages
            if self._preview_search_active and self._preview_search_query:
                self._execute_preview_search(self._preview_search_query)
        self.call_from_thread(update_state)

        # Render new messages
        self.call_from_thread(self._render_messages, new_msgs)

        # Show hint if more remain (based on batch size comparison)
        if not is_last_batch:
            preview = self.query_one("#preview", RichLog)
            self.call_from_thread(preview.write, Text.from_markup(
                f"[dim]--- More messages available. Press [bold]m[/bold] or [bold]space[/bold] to load more ---[/dim]"
            ))

    def action_search_content(self) -> None:
        self.query_one("#search-input", Input).focus()

    def action_open_preview_search(self) -> None:
        """Open the in-preview search bar (Ctrl+F).

        If preview has focus → open preview search with current session-list
        query pre-filled.  Otherwise → focus the session search input.
        """
        preview = self.query_one("#preview", RichLog)
        ps = self.query_one("#preview-search", Input)
        if preview.has_focus or self._preview_search_active:
            # Open / re-focus preview search bar
            self._preview_search_active = True
            ps.display = True
            self.query_one("#preview-search-info", Static).display = True
            # Pre-fill with the current session-list search query
            if not ps.value:
                left_query = self.query_one("#search-input", Input).value
                ps.value = left_query
                ps.cursor_position = len(ps.value)
            ps.focus()
        else:
            # Not in preview — fall back to session search
            self.query_one("#search-input", Input).focus()

    def _close_preview_search(self) -> None:
        """Hide the preview search bar and restore preview focus."""
        self._preview_search_active = False
        self._preview_search_query = ""
        self._preview_search_executed = ""
        self._preview_search_matches = []
        self._preview_search_current = -1
        ps = self.query_one("#preview-search", Input)
        ps.value = ""
        ps.display = False
        self.query_one("#preview-search-info", Static).display = False
        # Re-render without highlights
        self._rerender_preview(highlight_query="")
        self.query_one("#preview", RichLog).focus()

    @on(Input.Changed, "#preview-search")
    def on_preview_search_changed(self, event: Input.Changed) -> None:
        query = event.value.strip()
        self._preview_search_query = query
        # Don't search on every keystroke — wait for Enter
        # Just update info bar to indicate search is pending
        if query:
            info = self.query_one("#preview-search-info", Static)
            info.update(f" Type and press Enter to search for '{query}'")
        else:
            self._clear_search_highlights()

    @on(Input.Submitted, "#preview-search")
    def on_preview_search_submitted(self, event: Input.Submitted) -> None:
        """Enter in preview search → execute search or jump to next match."""
        query = self._preview_search_query
        if not query:
            self._clear_search_highlights()
            return
        
        # Same query already searched? → jump to next match
        if query.lower() == self._preview_search_executed.lower() and self._preview_search_matches:
            self._preview_search_next()
        else:
            # New query or no results yet → execute search
            self._run_preview_search(query)

    def on_preview_search_input_prev_match_requested(
        self, event: PreviewSearchInput.PrevMatchRequested
    ) -> None:
        """Shift+Tab in preview search → jump to previous match."""
        self._preview_search_prev()

    def _clear_search_highlights(self) -> None:
        """Clear search state and re-render without highlights."""
        self._preview_search_executed = ""
        self._preview_search_matches = []
        self._preview_search_current = -1
        self._update_search_info("", 0, -1)
        # Only re-render if we had highlights before
        if self._preview_search_query:
            self._rerender_preview(highlight_query="")

    def _run_preview_search(self, query: str) -> None:
        """Find matching messages and re-render with highlights.
        
        If not all messages are loaded yet, loads them first (in background),
        then runs the search. This ensures preview search covers the entire
        conversation, not just the first batch.
        """
        if not query:
            self._preview_search_matches = []
            self._preview_search_current = -1
            self._rerender_preview(highlight_query="")
            self._update_search_info(query, 0, -1)
            return

        # If not all messages loaded, load them first then search
        if not self._preview_all_loaded:
            self._update_search_info(query, -1, -1)  # -1 signals "loading"
            self._load_all_for_search(query)
            return

        self._execute_preview_search(query)

    def _normalize_for_search(self, text: str) -> str:
        """Normalize text for search by removing markdown formatting."""
        import re
        # Remove backticks (code formatting)
        text = text.replace("`", "")
        # Remove bold/italic markers: **, *, __, _
        # But preserve underscores in identifiers (only remove when used as formatting)
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # **bold**
        text = re.sub(r'\*([^*]+)\*', r'\1', text)      # *italic*
        text = re.sub(r'__([^_]+)__', r'\1', text)      # __bold__
        text = re.sub(r'(?<![a-zA-Z0-9])_([^_]+)_(?![a-zA-Z0-9])', r'\1', text)  # _italic_ (not in identifiers)
        return text.lower()

    def _execute_preview_search(self, query: str) -> None:
        """Actually perform the search (called after all messages are loaded)."""
        q = self._normalize_for_search(query)
        matches = [
            i for i, msg in enumerate(self._preview_messages)
            if q in self._normalize_for_search(msg.get("text", ""))
        ]
        self._preview_search_executed = query  # Mark this query as searched
        self._preview_search_matches = matches
        self._preview_search_current = 0 if matches else -1
        self._rerender_preview(highlight_query=query)
        self._update_search_info(query, len(matches),
                                  self._preview_search_current)
        # Scroll to first match
        if matches:
            self._scroll_to_match(matches[0])

    @work(thread=True)
    def _load_all_then_scroll_end(self) -> None:
        """Load all remaining messages, then scroll to end."""
        session = self.selected_session
        if not session:
            return
        session_id = session.get("session_id")
        if self._preview_loading_session_id != session_id:
            return

        # Load all remaining messages
        while not self._preview_all_loaded:
            skip = len(self._preview_messages)
            new_msgs = extract_messages(session, limit=self._preview_batch_size, offset=skip)
            
            if self._preview_loading_session_id != session_id:
                return
            
            if not new_msgs:
                self._preview_all_loaded = True
                break
            
            is_last = len(new_msgs) < self._preview_batch_size
            def update(msgs=new_msgs, last=is_last):
                if self._preview_loading_session_id != session_id:
                    return
                self._preview_messages.extend(msgs)
                self._preview_all_loaded = last
            self.call_from_thread(update)
            self.call_from_thread(self._render_messages, new_msgs)
            
            if is_last:
                break

        # Scroll to end on main thread
        def scroll_end():
            if self._preview_loading_session_id != session_id:
                return
            preview = self.query_one("#preview", RichLog)
            preview.scroll_end()
        self.call_from_thread(scroll_end)

    @work(thread=True)
    def _load_all_for_search(self, query: str) -> None:
        """Load ALL messages from scratch, then execute search."""
        session = self.selected_session
        if not session:
            return
        session_id = session.get("session_id")
        if self._preview_loading_session_id != session_id:
            return

        # Load all messages from the beginning (avoids race with _preview_messages)
        all_msgs = []
        while True:
            new_msgs = extract_messages(session, limit=self._preview_batch_size, offset=len(all_msgs))
            if self._preview_loading_session_id != session_id:
                return
            if not new_msgs:
                break
            all_msgs.extend(new_msgs)
            if len(new_msgs) < self._preview_batch_size:
                break

        # Replace state and search in ONE call_from_thread (atomic)
        def update_and_search():
            if self._preview_loading_session_id != session_id:
                return
            # Replace entirely — avoids duplicates from concurrent _load_preview
            self._preview_messages = all_msgs
            self._preview_all_loaded = True
            # Only search if query hasn't changed
            if self._preview_search_query == query:
                self._execute_preview_search(query)
            else:
                self.notify(
                    f"Search skipped: query changed '{query}'→'{self._preview_search_query}'",
                    severity="warning", timeout=5
                )
        self.call_from_thread(update_and_search)

    def _preview_search_next(self) -> None:
        """Jump to next match (scroll only, no re-render)."""
        if not self._preview_search_executed or not self._preview_search_matches:
            # No search done yet or no matches — trigger search if query exists
            if self._preview_search_query:
                self._run_preview_search(self._preview_search_query)
            return
        n = len(self._preview_search_matches)
        self._preview_search_current = (self._preview_search_current + 1) % n
        idx = self._preview_search_matches[self._preview_search_current]
        self._update_search_info(self._preview_search_executed, n,
                                  self._preview_search_current)
        self._scroll_to_match(idx)

    def _preview_search_prev(self) -> None:
        """Jump to previous match (scroll only, no re-render)."""
        if not self._preview_search_executed or not self._preview_search_matches:
            return
        n = len(self._preview_search_matches)
        self._preview_search_current = (self._preview_search_current - 1) % n
        idx = self._preview_search_matches[self._preview_search_current]
        self._update_search_info(self._preview_search_executed, n,
                                  self._preview_search_current)
        self._scroll_to_match(idx)

    def _update_search_info(self, query: str, total: int, current: int) -> None:
        info = self.query_one("#preview-search-info", Static)
        if not query:
            info.update("")
            return
        
        # total == -1 means "loading all messages"
        if total == -1:
            info.update(f" Loading all messages to search for '{query}'...")
            return
        
        if total == 0:
            info.update(f" No matches for '{query}' | Esc to close")
        else:
            info.update(
                f" {current + 1}/{total} matches for '{query}'"
                " | Enter: next  Shift+Tab: prev  Esc: close"
            )

    def _rerender_preview(self, highlight_query: str = "") -> None:
        """Re-render _preview_messages with optional inline highlight."""
        from rich.text import Text as RichText
        from rich.markdown import Markdown

        preview = self.query_one("#preview", RichLog)
        preview.clear()

        # Re-render session header (same as _load_preview)
        session = self.selected_session
        if not session:
            return
        title = (session.get("title") or "(untitled)").replace("[", "\\[").replace("]", "\\]")
        cwd   = (session.get("cwd") or "").replace("[", "\\[").replace("]", "\\]")
        created = (session.get("created_at") or "")[:19].replace("T", " ")
        updated = (session.get("updated_at") or "")[:19].replace("T", " ")
        msgs = session.get("msg_count", 0)
        dur = session.get("duration_min", 0)
        dur_str = "-" if dur == 0 else (f"{dur}m" if dur < 60 else f"{dur // 60}h {dur % 60}m")
        preview.write(RichText.from_markup(
            f"[bold]SESSION:[/bold] {title}\n"
            f"[bold]DIRECTORY:[/bold] {cwd}\n"
            f"[bold]CREATED:[/bold] {created}\n"
            f"[bold]UPDATED:[/bold] {updated}\n"
            f"[bold]MESSAGES:[/bold] {msgs}\n"
            f"[bold]DURATION:[/bold] {dur_str}\n"
            f"[bold]ID:[/bold] {session.get('session_id', '')}\n"
        ))
        preview.write(RichText("-" * 50))
        preview.write(RichText(""))

        q = highlight_query.lower() if highlight_query else ""
        match_indices = set(self._preview_search_matches)

        # Get theme color for highlighting — accent is most visible
        theme = self.current_theme
        highlight_bg = theme.accent if theme else "#ffa62b"

        # Track line offsets for accurate _scroll_to_match
        msg_line_offsets: dict[int, int] = {}

        for i, msg in enumerate(self._preview_messages):
            role = msg["role"]
            txt  = msg["text"]
            # Record line offset before writing this message
            msg_line_offsets[i] = len(preview.lines)
            label = (RichText.from_markup("[bold cyan][YOU]:[/bold cyan]")
                     if role == "you"
                     else RichText.from_markup("[bold green][KIRO]:[/bold green]"))
            preview.write(label)

            if q and i in match_indices:
                # Matching message: highlight only lines containing the match
                rendered = RichText(txt)
                
                # Find line boundaries and apply background only to matching lines
                line_start = 0
                for line in txt.split('\n'):
                    line_end = line_start + len(line)
                    if q in line.lower():
                        # Dark text on accent background for readability
                        rendered.stylize(f"black on {highlight_bg}", line_start, line_end)
                    line_start = line_end + 1  # +1 for the newline character
                
                # Bold the matched words within highlighted lines
                lower_txt = txt.lower()
                start = 0
                while True:
                    pos = lower_txt.find(q, start)
                    if pos == -1:
                        break
                    rendered.stylize("bold", pos, pos + len(q))
                    start = pos + len(q)
                preview.write(rendered)
            elif role == "kiro":
                # Markdown for kiro messages (whether searching or not)
                try:
                    preview.write(Markdown(txt))
                except Exception:
                    preview.write(RichText(txt))
            else:
                preview.write(RichText(txt))

            preview.write(RichText(""))

        # Store line offsets for accurate scroll-to-match
        self._preview_msg_line_offsets = msg_line_offsets

        if not self._preview_all_loaded:
            total = session.get("msg_count", 0)
            remaining = total - len(self._preview_messages)
            if remaining > 0:
                preview.write(RichText.from_markup(
                    f"[dim]--- ~{remaining} more messages. "
                    "Press [bold]m[/bold] or [bold]space[/bold] to load more ---[/dim]"
                ))

    def _scroll_to_match(self, msg_index: int) -> None:
        """Scroll preview so the matched message is visible.

        Uses _preview_msg_line_offsets built during _rerender_preview for
        accurate positioning even with word-wrap.
        Falls back to scanning RichLog.lines for the first highlight.
        """
        preview = self.query_one("#preview", RichLog)

        def do_scroll():
            # Primary: use pre-computed line offsets from _rerender_preview
            offsets = getattr(self, '_preview_msg_line_offsets', {})
            if msg_index in offsets:
                preview.scroll_to(y=offsets[msg_index], animate=False)
                return
            # Fallback: scan RichLog.lines for first highlighted segment
            for line_num, strip in enumerate(preview.lines):
                for segment in strip:
                    if segment.style and segment.style.bgcolor:
                        preview.scroll_to(y=line_num, animate=False)
                        return

        self.call_later(do_scroll)

    def action_copy_conversation(self) -> None:
        if not self.selected_session:
            return
        # Run in background to avoid blocking UI
        self._copy_conversation_async()

    @work(thread=True)
    def _copy_conversation_async(self) -> None:
        """Copy conversation to clipboard in background thread."""
        session = self.selected_session
        if not session:
            return
        messages = extract_messages(session)
        if not messages:
            self.call_from_thread(self.notify, "No messages to copy", severity="warning")
            return
        text = ""
        for msg in messages:
            label = "[YOU]" if msg["role"] == "you" else "[KIRO]"
            text += f"{label}:\n{msg['text']}\n\n"
        try:
            if sys.platform == "win32":
                process = subprocess.Popen(["clip"], stdin=subprocess.PIPE)
                # clip expects UTF-16 LE with BOM for Unicode support
                bom = b'\xff\xfe'
                process.communicate(bom + text.encode("utf-16-le"))
            elif sys.platform == "darwin":
                process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
                process.communicate(text.encode("utf-8"))
            else:
                # Linux: try xclip then xsel
                process = None
                for cmd in (["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]):
                    try:
                        process = subprocess.Popen(cmd, stdin=subprocess.PIPE)
                        process.communicate(text.encode("utf-8"))
                        break
                    except FileNotFoundError:
                        continue
                if process is None:
                    self.call_from_thread(self.notify, "No clipboard tool found (install xclip or xsel)", severity="error")
                    return
            # Check return code
            if process.returncode != 0:
                self.call_from_thread(self.notify, "Clipboard copy failed", severity="error")
                return
            self.call_from_thread(self.notify, f"Copied {len(messages)} messages to clipboard")
        except FileNotFoundError:
            self.call_from_thread(self.notify, "Clipboard tool not found", severity="error")


# --- Entry Point ---

def main():
    import atexit
    atexit.register(close_logging)
    
    app = KiroHistory()
    result = app.run()

    if result and isinstance(result, tuple) and result[0] == "resume":
        session = result[1]
        trust_all_tools = result[2] if len(result) > 2 else True
        cwd = session.get("cwd", "")
        session_id = session.get("session_id", "")
        print(f"\nResuming session: {session.get('title', '(untitled)')}")
        print(f"Session ID: {session_id}")
        print(f"Directory: {cwd}\n")
        os.chdir(cwd)
        cmd = ["kiro-cli", "chat", "--resume-id", session_id]
        if trust_all_tools:
            cmd.append("--trust-all-tools")
        if sys.platform == "win32":
            subprocess.run(cmd, cwd=cwd)
        else:
            try:
                os.execvp("kiro-cli", cmd)
            except FileNotFoundError:
                print("ERROR: kiro-cli not found. Is it installed and in your PATH?", file=sys.stderr)
                sys.exit(1)

    elif result and isinstance(result, tuple) and result[0] == "new":
        trust_all_tools = result[2] if len(result) > 2 else True
        print("\nStarting new kiro-cli session...\n")
        cmd = ["kiro-cli", "chat"]
        if trust_all_tools:
            cmd.append("--trust-all-tools")
        if sys.platform == "win32":
            subprocess.run(cmd)
        else:
            try:
                os.execvp("kiro-cli", cmd)
            except FileNotFoundError:
                print("ERROR: kiro-cli not found. Is it installed and in your PATH?", file=sys.stderr)
                sys.exit(1)


if __name__ == "__main__":
    main()
