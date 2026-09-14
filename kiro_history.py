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
from textual.containers import Horizontal, Vertical, Center
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input, Static, ListView, ListItem, RichLog, Button
from rich.text import Text
from rich.markdown import Markdown


# --- Data Layer (read-only) ---

# Paths — override with KIRO_DEMO_DIR env var for demo/recording
_DEMO_DIR = os.environ.get("KIRO_DEMO_DIR", "")
SESSIONS_DIR = Path(_DEMO_DIR) / "kiro" / "sessions" / "cli" if _DEMO_DIR else Path.home() / ".kiro" / "sessions" / "cli"

def _sqlite_db_path() -> Path:
    """Return the platform-appropriate SQLite DB path."""
    if _DEMO_DIR:
        return Path(_DEMO_DIR) / "kiro-cli" / "data.sqlite3"
    if sys.platform == "win32":
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        if local_appdata:
            return Path(local_appdata) / "kiro-cli" / "data.sqlite3"
        # Fallback: %USERPROFILE%\AppData\Local
        return Path.home() / "AppData" / "Local" / "kiro-cli" / "data.sqlite3"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "kiro-cli" / "data.sqlite3"
    else:
        # Linux: XDG_DATA_HOME or ~/.local/share
        xdg = os.environ.get("XDG_DATA_HOME", "")
        base = Path(xdg) if xdg else Path.home() / ".local" / "share"
        return base / "kiro-cli" / "data.sqlite3"

SQLITE_DB = _sqlite_db_path()
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB guard


def _extract_messages_from_history(history, limit=None):
    """Extract messages from a SQLite v1/v2 history array."""
    messages = []
    for entry in history:
        # User message
        user = entry.get("user", {})
        content = user.get("content", {})
        if "Prompt" in content:
            prompt_text = content["Prompt"].get("prompt", "")
            if prompt_text:
                messages.append({"role": "you", "text": prompt_text})
                if limit and len(messages) >= limit:
                    return messages
        # Assistant message — structure varies:
        #   assistant.content.Text (older format)
        #   assistant.Response.content (text reply)
        #   assistant.ToolUse.content (thinking before tool) + .tool_uses (tools called)
        assistant = entry.get("assistant", {})
        if isinstance(assistant, dict):
            a_content = assistant.get("content", {})
            if "Text" in a_content:
                messages.append({"role": "kiro", "text": a_content["Text"]})
                if limit and len(messages) >= limit:
                    return messages
            elif "Response" in assistant:
                resp = assistant["Response"]
                if isinstance(resp, dict) and resp.get("content"):
                    messages.append({"role": "kiro", "text": resp["content"]})
                    if limit and len(messages) >= limit:
                        return messages
            elif "ToolUse" in assistant:
                tu = assistant["ToolUse"]
                if isinstance(tu, dict):
                    txt = tu.get("content", "")
                    tools = tu.get("tool_uses", [])
                    tool_names = ", ".join(t.get("name", "?") for t in tools[:3]) if tools else ""
                    display = txt if txt else ""
                    if tool_names:
                        display = f"{display}\n[tools: {tool_names}]" if display else f"[tools: {tool_names}]"
                    if display:
                        messages.append({"role": "kiro", "text": display})
                        if limit and len(messages) >= limit:
                            return messages
    return messages


def _get_first_prompt_from_history(history):
    """Get the first user prompt from a history array for use as title."""
    for entry in history:
        user = entry.get("user", {})
        content = user.get("content", {})
        if "Prompt" in content:
            txt = content["Prompt"].get("prompt", "").strip()
            if txt:
                return txt[:60]
    return "(untitled)"


def _load_sqlite_sessions():
    """Load sessions from the SQLite database (v1 + v2 tables)."""
    sessions = []
    if not SQLITE_DB.exists():
        return sessions

    try:
        conn = sqlite3.connect(f"file:{SQLITE_DB}?mode=ro", uri=True)
    except sqlite3.OperationalError:
        return sessions

    # V2 sessions (Dec 2025 - Mar 2026) — have timestamps and session IDs
    try:
        rows = conn.execute(
            "SELECT key, conversation_id, value, created_at, updated_at "
            "FROM conversations_v2 ORDER BY updated_at DESC"
        ).fetchall()
        for cwd, conv_id, value, created_ms, updated_ms in rows:
            try:
                d = json.loads(value)
                history = d.get("history", [])
                title = _get_first_prompt_from_history(history)
                created = datetime.fromtimestamp(created_ms / 1000).strftime("%Y-%m-%dT%H:%M:%S")
                updated = datetime.fromtimestamp(updated_ms / 1000).strftime("%Y-%m-%dT%H:%M:%S")
                msg_count = len(history)
                duration_min = int((updated_ms - created_ms) / 1000 / 60)
                sessions.append({
                    "session_id": conv_id,
                    "title": title,
                    "cwd": cwd,
                    "created_at": created,
                    "updated_at": updated,
                    "source": "sqlite_v2",
                    "msg_count": msg_count,
                    "duration_min": duration_min,
                    "_history": history,
                    "is_subagent": False,  # SQLite sessions predate subagent feature
                    "parent_session_id": None,
                })
            except (json.JSONDecodeError, KeyError, ValueError):
                pass
    except sqlite3.OperationalError:
        pass

    # V1 sessions (Nov 2025 - Dec 2025) — keyed by directory, no timestamps
    try:
        rows = conn.execute("SELECT key, value FROM conversations").fetchall()
        for cwd, value in rows:
            try:
                d = json.loads(value)
                history = d.get("history", [])
                title = _get_first_prompt_from_history(history)
                conv_id = d.get("conversation_id", "")
                sessions.append({
                    "session_id": conv_id,
                    "title": title,
                    "cwd": cwd,
                    "created_at": "",
                    "updated_at": "",
                    "source": "sqlite_v1",
                    "msg_count": len(history),
                    "duration_min": 0,
                    "_history": history,
                    "is_subagent": False,  # SQLite sessions predate subagent feature
                    "parent_session_id": None,
                })
            except (json.JSONDecodeError, KeyError, ValueError):
                pass
    except sqlite3.OperationalError:
        pass

    conn.close()
    return sessions


def _load_jsonl_sessions():
    """Load sessions from ~/.kiro/sessions/cli/*.json (v3: current format)."""
    sessions = []
    if not SESSIONS_DIR.exists():
        return sessions

    for json_file in SESSIONS_DIR.glob("*.json"):
        try:
            if json_file.stat().st_size > MAX_FILE_SIZE:
                continue
            with open(json_file, encoding="utf-8") as f:
                meta = json.load(f)
            created = meta.get("created_at") or ""
            updated = meta.get("updated_at") or ""
            # Count messages in JSONL
            jsonl_path = str(json_file).replace(".json", ".jsonl")
            msg_count = 0
            jp = Path(jsonl_path)
            if jp.exists():
                with open(jp, encoding="utf-8") as jf:
                    for line in jf:
                        try:
                            ld = json.loads(line)
                            if ld.get("kind") in ("Prompt", "AssistantMessage"):
                                msg_count += 1
                        except (json.JSONDecodeError, ValueError):
                            pass
            # Compute duration
            duration_min = 0
            if created and updated:
                try:
                    c = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    u = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                    duration_min = int((u - c).total_seconds() / 60)
                except (ValueError, TypeError):
                    pass
            sessions.append({
                "session_id": meta.get("session_id", ""),
                "title": meta.get("title") or "(untitled)",
                "cwd": meta.get("cwd") or "",
                "created_at": created,
                "updated_at": updated,
                "source": "jsonl",
                "msg_count": msg_count,
                "duration_min": duration_min,
                "jsonl_path": jsonl_path,
                "is_subagent": meta.get("session_created_reason") == "subagent",
                "parent_session_id": meta.get("parent_session_id"),
            })
        except (json.JSONDecodeError, KeyError, ValueError, OSError):
            pass
    return sessions


def get_sessions():
    """Load all sessions from all stores, deduplicated, sorted by recency."""
    jsonl = _load_jsonl_sessions()
    sqlite = _load_sqlite_sessions()

    # Deduplicate: if same session_id exists in both, prefer JSONL (newer format)
    seen_ids = {s["session_id"] for s in jsonl if s["session_id"]}
    for s in sqlite:
        if s["session_id"] and s["session_id"] not in seen_ids:
            jsonl.append(s)
            seen_ids.add(s["session_id"])

    # Sort: sessions with timestamps first (descending), then untimed ones at the end
    jsonl.sort(key=lambda s: s.get("updated_at") or s.get("created_at") or "0", reverse=True)
    return jsonl


def extract_messages(session, limit=None):
    """Extract conversation messages from any session format."""
    # SQLite sessions carry _history inline
    if "_history" in session:
        return _extract_messages_from_history(session["_history"], limit)

    # JSONL sessions read from file
    jsonl_path = session.get("jsonl_path", "")
    if not jsonl_path:
        return []
    path = Path(jsonl_path)
    if not path.exists() or path.stat().st_size == 0:
        return []
    if path.stat().st_size > MAX_FILE_SIZE:
        return [{"role": "system", "text": "(File too large to preview)"}]

    messages = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
                kind = d.get("kind", "")
                if kind not in ("Prompt", "AssistantMessage"):
                    continue
                data = d.get("data", {})
                content = data.get("content", [])
                txt = ""
                for block in (content if isinstance(content, list) else []):
                    if isinstance(block, dict) and block.get("kind") == "text":
                        txt = block.get("data", "")
                        break
                if txt:
                    role = "you" if kind == "Prompt" else "kiro"
                    messages.append({"role": role, "text": txt})
                    if limit and len(messages) >= limit:
                        break
            except (json.JSONDecodeError, KeyError, ValueError):
                pass
    return messages


def _fuzzy_match(query, text):
    """Fuzzy match: all query tokens must appear in text, in any order.
    Supports multi-word queries ('mem leak' matches 'Debug memory leak')
    and tolerates partial words ('depl' matches 'deployment').
    """
    text_lower = text.lower()
    tokens = query.lower().split()
    return all(token in text_lower for token in tokens)


def search_sessions(query, sessions):
    """Fuzzy-search sessions by title, cwd, and conversation content across all stores."""
    if not query:
        return sessions

    results = []

    for session in sessions:
        # Check title and cwd first (fast)
        title = (session.get("title") or "")
        cwd = (session.get("cwd") or "")
        if _fuzzy_match(query, title) or _fuzzy_match(query, cwd):
            results.append(session)
            continue

        # Search conversation content
        if "_history" in session:
            # SQLite sessions — search inline history
            found = False
            for entry in session["_history"]:
                user = entry.get("user", {})
                content = user.get("content", {})
                if "Prompt" in content:
                    if _fuzzy_match(query, content["Prompt"].get("prompt", "")):
                        found = True
                        break
                assistant = entry.get("assistant", {})
                if isinstance(assistant, dict):
                    a_content = assistant.get("content", {})
                    if "Text" in a_content and _fuzzy_match(query, a_content["Text"]):
                        found = True
                        break
                    if "Response" in assistant:
                        resp = assistant["Response"]
                        if isinstance(resp, dict) and _fuzzy_match(query, resp.get("content", "")):
                            found = True
                            break
                    if "ToolUse" in assistant:
                        tu = assistant["ToolUse"]
                        if isinstance(tu, dict) and _fuzzy_match(query, tu.get("content", "")):
                            found = True
                            break
            if found:
                results.append(session)
        elif session.get("jsonl_path"):
            # JSONL sessions — search file
            jsonl_path = Path(session["jsonl_path"])
            if not jsonl_path.exists() or jsonl_path.stat().st_size == 0:
                continue
            if jsonl_path.stat().st_size > MAX_FILE_SIZE:
                continue
            found = False
            with open(jsonl_path, encoding="utf-8") as f:
                for line in f:
                    try:
                        d = json.loads(line)
                        kind = d.get("kind", "")
                        if kind not in ("Prompt", "AssistantMessage"):
                            continue
                        content = d.get("data", {}).get("content", [])
                        for block in (content if isinstance(content, list) else []):
                            if isinstance(block, dict) and block.get("kind") == "text":
                                if _fuzzy_match(query, block.get("data", "")):
                                    found = True
                                    break
                        if found:
                            break
                    except (json.JSONDecodeError, KeyError, ValueError):
                        pass
            if found:
                results.append(session)

    return results


# --- UI Components ---

class RenameScreen(ModalScreen):
    """Dialog for renaming a session."""

    CSS = """
    RenameScreen {
        align: center middle;
    }
    #rename-dialog {
        width: 60;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    #rename-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    #rename-input {
        margin: 1 0;
    }
    #rename-buttons {
        margin-top: 1;
        align: center middle;
    }
    #rename-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "save", "Save", show=False),
    ]

    def __init__(self, current_title: str):
        super().__init__()
        self._current_title = current_title

    def compose(self) -> ComposeResult:
        with Vertical(id="rename-dialog"):
            yield Static("Rename Session", id="rename-title")
            yield Input(value=self._current_title, id="rename-input", placeholder="Enter new title...")
            with Horizontal(id="rename-buttons"):
                yield Button("Save", variant="primary", id="save-btn")
                yield Button("Cancel", id="cancel-btn")

    def on_mount(self) -> None:
        self.query_one("#rename-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            self.action_save()
        else:
            self.action_cancel()

    def action_save(self) -> None:
        new_title = self.query_one("#rename-input", Input).value.strip()
        self.dismiss(new_title if new_title else None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class SessionItem(ListItem):
    """A single session row in the list."""

    def __init__(self, session: dict) -> None:
        super().__init__()
        self.session = session

    def compose(self) -> ComposeResult:
        raw_ts = (self.session.get("updated_at") or "")[:10]
        try:
            dt = datetime.strptime(raw_ts, "%Y-%m-%d")
            # %-d is Linux/macOS only; strip leading zero manually for cross-platform
            ts = f"{dt.day} {dt.strftime('%b %Y')}"
        except (ValueError, TypeError):
            ts = raw_ts
        title = (self.session.get("title") or "(untitled)")[:60]
        cwd = os.path.basename(self.session.get("cwd") or "")
        msgs = self.session.get("msg_count", 0)
        dur = self.session.get("duration_min", 0)
        dur_str = f"{dur}m" if dur < 60 else f"{dur // 60}h {dur % 60}m"
        yield Static(
            f"[bold]{title}[/bold]\n"
            f"[dim]{cwd}[/dim]  [dim italic]{ts}[/dim italic]  [dim cyan]{msgs} msgs[/dim cyan]  [dim green]{dur_str}[/dim green]",
            markup=True,
        )


class KiroHistory(App):
    """Kiro CLI session browser and search."""

    TITLE = "kiro-cli-history"
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
        Binding("ctrl+f", "search_content", "Search in conversation"),
        Binding("f2", "rename_session", "Rename"),
        Binding("escape", "clear_or_quit", "Clear / Quit"),
        Binding("ctrl+c", "quit", "Quit"),
        Binding("/", "focus_search", "Search"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("right", "focus_preview", "Preview", show=False),
        Binding("l", "focus_preview", "Preview", show=False),
        Binding("left", "focus_list", "List", show=False),
        Binding("h", "focus_list", "List", show=False),
        Binding("m", "load_more", "More", show=False),
        Binding("space", "load_more", "More", show=False),
    ]

    def __init__(self):
        super().__init__()
        self.all_sessions = []
        self.filtered_sessions = []
        self.selected_session = None
        # Settings
        self._trust_all_tools = True  # Default: enabled
        self._show_non_interactive = True  # Default: show all sessions
        self._show_untitled = True  # Default: show untitled sessions
        self._viewer_search_query = ""
        # Lazy loading state
        self._preview_messages = []  # Messages loaded so far
        self._preview_all_loaded = False  # Whether all messages are loaded
        self._preview_batch_size = 30  # Messages per batch
        self._sessions_loading = True  # Whether sessions are still loading

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
        
        # Toggle non-interactive sessions visibility
        ni_status = "shown" if self._show_non_interactive else "hidden"
        yield SystemCommand(
            f"Toggle non-interactive sessions (currently {ni_status})",
            "Show/hide sessions with no user messages",
            self._toggle_non_interactive
        )
        
        # Toggle untitled sessions visibility
        untitled_status = "shown" if self._show_untitled else "hidden"
        untitled_count = sum(1 for s in self.all_sessions if s.get("title") in [None, "", "(untitled)"])
        yield SystemCommand(
            f"Toggle untitled sessions (currently {untitled_status}, {untitled_count} sessions)",
            "Show/hide sessions without a title",
            self._toggle_untitled
        )

    def _toggle_trust_all_tools(self) -> None:
        self._trust_all_tools = not self._trust_all_tools
        status = "enabled" if self._trust_all_tools else "disabled"
        self.notify(f"--trust-all-tools {status}")

    def _toggle_non_interactive(self) -> None:
        self._show_non_interactive = not self._show_non_interactive
        self._refresh_sessions()
        status = "shown" if self._show_non_interactive else "hidden"
        self.notify(f"Non-interactive sessions {status}")

    def _toggle_untitled(self) -> None:
        self._show_untitled = not self._show_untitled
        self._refresh_sessions()
        status = "shown" if self._show_untitled else "hidden"
        self.notify(f"Untitled sessions {status}")

    def _update_session_title(self, session: dict, new_title: str) -> bool:
        """Update session title in the source file."""
        source = session.get("source")
        
        if source == "jsonl":
            # Update JSONL metadata file
            jsonl_path = session.get("jsonl_path")
            if not jsonl_path:
                return False
            json_path = jsonl_path.replace(".jsonl", ".json")
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                metadata["title"] = new_title
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(metadata, f, ensure_ascii=False, indent=2)
                return True
            except Exception:
                return False
        
        elif source in ("sqlite_v2", "sqlite_v1"):
            # Update SQLite database
            db_path = _sqlite_db_path()
            if not db_path or not os.path.exists(db_path):
                return False
            try:
                table = "conversations_v2" if source == "sqlite_v2" else "conversations"
                with sqlite3.connect(db_path) as conn:
                    conn.execute(
                        f"UPDATE {table} SET title = ? WHERE session_id = ?",
                        (new_title, session["session_id"])
                    )
                    conn.commit()
                return True
            except Exception:
                return False
        
        return False

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="left-pane"):
                yield Input(placeholder="Search sessions...", id="search-input")
                yield ListView(id="session-list")
            with Vertical(id="right-pane"):
                yield RichLog(id="preview", wrap=True, highlight=True, markup=True)
        yield Static("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        # Show loading indicator in the list area
        list_view = self.query_one("#session-list", ListView)
        list_view.append(ListItem(Static("Loading sessions...", classes="loading-hint")))
        # Load sessions in background
        self._load_sessions_async()

    @work(thread=True)
    def _load_sessions_async(self) -> None:
        """Load sessions in background thread."""
        sessions = get_sessions()
        self.all_sessions = sessions
        self.filtered_sessions = sessions
        self._sessions_loading = False
        self.call_from_thread(self._populate_list, sessions)
        self.call_from_thread(
            self.query_one("#status-bar", Static).update,
            f" {len(sessions)} sessions | Ctrl+R resume | / search | ? help"
        )
        # If user typed search query while loading, apply it now
        def apply_search():
            search = self.query_one("#search-input", Input)
            if search.value:
                self._do_search(search.value)
        self.call_from_thread(apply_search)

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
        self._do_search(event.value)

    def on_key(self, event) -> None:
        """Handle key events for navigation."""
        # Search input: down/j moves to session list
        search_input = self.query_one("#search-input", Input)
        if search_input.has_focus and event.key in ("down", "j"):
            event.prevent_default()
            event.stop()
            self.query_one("#session-list", ListView).focus()
            return

        # Session list: up/k at first item moves to search input
        list_view = self.query_one("#session-list", ListView)
        if list_view.has_focus and event.key in ("up", "k"):
            if list_view.index == 0 or len(list_view.children) == 0:
                event.prevent_default()
                event.stop()
                search_input.focus()
                return

        # Preview pane: left/h moves back to session list
        preview = self.query_one("#preview", RichLog)
        if preview.has_focus and event.key in ("left", "h"):
            event.prevent_default()
            event.stop()
            self.query_one("#session-list", ListView).focus()
            return

    @work(thread=True)
    def _do_search(self, query: str) -> None:
        results = search_sessions(query, self.all_sessions)
        self.filtered_sessions = results
        self.call_from_thread(self._populate_list, results)
        status_text = f" {len(results)}/{len(self.all_sessions)} sessions"
        if query:
            status_text += f" matching '{query}'"
        status_text += " | Ctrl+R resume | / search"
        self.call_from_thread(
            self.query_one("#status-bar", Static).update, status_text
        )

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
        self._load_preview(session)

    @work(thread=True)
    def _load_preview(self, session: dict) -> None:
        preview = self.query_one("#preview", RichLog)
        self.call_from_thread(preview.clear)

        # Header
        title = session.get("title") or "(untitled)"
        cwd = session.get("cwd") or ""
        created = (session.get("created_at") or "")[:19].replace("T", " ")
        updated = (session.get("updated_at") or "")[:19].replace("T", " ")
        msgs = session.get("msg_count", 0)
        dur = session.get("duration_min", 0)
        dur_str = f"{dur}m" if dur < 60 else f"{dur // 60}h {dur % 60}m"

        header = (
            f"[bold]SESSION:[/bold] {title}\n"
            f"[bold]DIRECTORY:[/bold] {cwd}\n"
            f"[bold]CREATED:[/bold] {created}\n"
            f"[bold]UPDATED:[/bold] {updated}\n"
            f"[bold]MESSAGES:[/bold] {msgs}\n"
            f"[bold]DURATION:[/bold] {dur_str}\n"
            f"[bold]ID:[/bold] {session.get('session_id', '')}\n"
        )
        self.call_from_thread(preview.write, Text.from_markup(header))
        self.call_from_thread(preview.write, Text("─" * 50))
        self.call_from_thread(preview.write, Text(""))

        # Lazy loading: extract only first batch initially
        self._preview_messages = extract_messages(session, limit=self._preview_batch_size)
        self._preview_all_loaded = len(self._preview_messages) < self._preview_batch_size

        if not self._preview_messages:
            self.call_from_thread(preview.write, Text("(no conversation data)"))
            return

        # Render first batch
        self.call_from_thread(self._render_messages, self._preview_messages)

        # Show "load more" hint if there might be more messages
        total_msgs = session.get("msg_count", 0)
        if not self._preview_all_loaded and total_msgs > len(self._preview_messages):
            remaining = total_msgs - len(self._preview_messages)
            self.call_from_thread(preview.write, Text.from_markup(
                f"[dim]─── ~{remaining} more messages. Press [bold]m[/bold] or [bold]space[/bold] to load more ───[/dim]"
            ))

    def _render_messages(self, messages: list) -> None:
        """Render a list of messages to preview."""
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
        filtered = self.all_sessions
        
        # Filter non-interactive sessions (subagent sessions or very few messages)
        if not self._show_non_interactive:
            filtered = [
                s for s in filtered
                if not self._is_non_interactive(s)
            ]
        
        # Filter untitled sessions
        if not self._show_untitled:
            filtered = [
                s for s in filtered
                if s.get("title") not in [None, "", "(untitled)"]
            ]
        
        self.filtered_sessions = filtered
        self._populate_list(self.filtered_sessions)
        search = self.query_one("#search-input", Input)
        if search.value:
            self._do_search(search.value)

    def _is_non_interactive(self, session: dict) -> bool:
        """Check if a session is non-interactive (subagent or minimal messages).
        
        A session is non-interactive if:
        1. It's a subagent session WITH a parent (true subagent spawned by another session)
        2. It has very few messages (0 or 1)
        """
        # True subagent: has parent_session_id (spawned by another session)
        if session.get("parent_session_id"):
            return True
        # Sessions with very few messages (0 or 1) are non-interactive
        if session.get("msg_count", 0) <= 1:
            return True
        return False

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
                    self.notify(f"Renamed to: {new_title[:50]}...")
                    # Refresh the list to show new title
                    self._populate_list(self.filtered_sessions)
                else:
                    self.notify("Failed to rename session", severity="error")
        
        self.push_screen(RenameScreen(current_title), handle_rename)

    def action_resume(self) -> None:
        if not self.selected_session:
            return
        cwd = self.selected_session.get("cwd", "")
        if not cwd or not os.path.isdir(cwd):
            self.notify(f"Directory not found: {cwd}", severity="error")
            return
        self.exit(result=("resume", self.selected_session, self._trust_all_tools))

    def action_new_session(self) -> None:
        """Start a new kiro-cli session in the current directory."""
        self.exit(result=("new", None, self._trust_all_tools))

    def action_focus_search(self) -> None:
        self.query_one("#search-input", Input).focus()

    def action_clear_or_quit(self) -> None:
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
        self._load_more_messages()

    @work(thread=True)
    def _load_more_messages(self) -> None:
        """Load next batch of messages from the session file."""
        session = self.selected_session
        if not session:
            return

        # Calculate how many we need to skip
        skip = len(self._preview_messages)

        # Extract all messages (with no limit), then take the next batch
        # This is needed because extract_messages doesn't support offset
        all_msgs = extract_messages(session)
        new_msgs = all_msgs[skip:skip + self._preview_batch_size]

        if not new_msgs:
            self._preview_all_loaded = True
            self.call_from_thread(self.notify, "All messages loaded", severity="information")
            return

        self._preview_messages.extend(new_msgs)
        self._preview_all_loaded = len(all_msgs) <= len(self._preview_messages)

        # Render new messages
        self.call_from_thread(self._render_messages, new_msgs)

        # Show hint if more remain
        remaining = len(all_msgs) - len(self._preview_messages)
        if remaining > 0:
            preview = self.query_one("#preview", RichLog)
            self.call_from_thread(preview.write, Text.from_markup(
                f"[dim]─── {remaining} more messages. Press [bold]m[/bold] or [bold]space[/bold] to load more ───[/dim]"
            ))

    def action_search_content(self) -> None:
        self.query_one("#search-input", Input).focus()

    def action_copy_conversation(self) -> None:
        if not self.selected_session:
            return
        messages = extract_messages(self.selected_session)
        if not messages:
            self.notify("No messages to copy", severity="warning")
            return
        text = ""
        for msg in messages:
            label = "[YOU]" if msg["role"] == "you" else "[KIRO]"
            text += f"{label}:\n{msg['text']}\n\n"
        try:
            if sys.platform == "win32":
                process = subprocess.Popen(["clip"], stdin=subprocess.PIPE)
                process.communicate(text.encode("utf-16-le"))
            elif sys.platform == "darwin":
                process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
                process.communicate(text.encode("utf-8"))
            else:
                # Linux: try xclip then xsel
                for cmd in (["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]):
                    try:
                        process = subprocess.Popen(cmd, stdin=subprocess.PIPE)
                        process.communicate(text.encode("utf-8"))
                        break
                    except FileNotFoundError:
                        continue
                else:
                    self.notify("No clipboard tool found (install xclip or xsel)", severity="error")
                    return
            self.notify(f"Copied {len(messages)} messages to clipboard")
        except FileNotFoundError:
            self.notify("Clipboard tool not found", severity="error")


# --- Entry Point ---

def main():
    app = KiroHistory()
    result = app.run()

    if result and isinstance(result, tuple) and result[0] == "resume":
        session = result[1]
        trust_all_tools = result[2] if len(result) > 2 else True
        cwd = session["cwd"]
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
            os.execvp("kiro-cli", cmd)

    elif result and isinstance(result, tuple) and result[0] == "new":
        trust_all_tools = result[2] if len(result) > 2 else True
        print("\nStarting new kiro-cli session...\n")
        cmd = ["kiro-cli", "chat"]
        if trust_all_tools:
            cmd.append("--trust-all-tools")
        if sys.platform == "win32":
            subprocess.run(cmd)
        else:
            os.execvp("kiro-cli", cmd)


if __name__ == "__main__":
    main()
