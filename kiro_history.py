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

# --- Version ---

# Fallback version when git is not available
VERSION = "v0.1.0-cakel.1"

def _get_version_string() -> str:
    """Return version string: tag + short hash, always.

    Examples:
      tagged commit:    v0.1.0-cakel.1-abc1234
      untagged commit:  abc1234
      no git:           v0.1.0-cakel.1  (fallback constant)
    """
    try:
        script_dir = Path(__file__).parent
        # Get short hash (always shown)
        hash_result = subprocess.run(
            ["git", "-C", str(script_dir), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=2
        )
        if hash_result.returncode != 0:
            return VERSION
        short_hash = hash_result.stdout.strip()

        # Try to get latest tag
        tag_result = subprocess.run(
            ["git", "-C", str(script_dir), "describe", "--tags", "--abbrev=0"],
            capture_output=True, text=True, timeout=2
        )
        if tag_result.returncode == 0:
            tag = tag_result.stdout.strip()
            return f"{tag}-{short_hash}"
        return short_hash
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return VERSION

from textual.containers import Horizontal, Vertical, Center
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input, Static, ListView, ListItem, RichLog, Button
from rich.text import Text
from rich.markdown import Markdown


# --- Data Layer (read-only) ---

# Paths - override with KIRO_DEMO_DIR env var for demo/recording
_DEMO_DIR = os.environ.get("KIRO_DEMO_DIR", "")
if _DEMO_DIR:
    # Normalize to absolute path to prevent path traversal
    _DEMO_DIR = str(Path(_DEMO_DIR).resolve())
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


def _load_sqlite_history(session: dict) -> list | None:
    """Load history on demand from SQLite DB (lazy loading).
    
    Returns history list, or None on error.
    """
    db_path = _sqlite_db_path()
    if not db_path or not Path(db_path).exists():
        return None
    source = session.get("source", "")
    session_id = session.get("session_id", "")
    cwd = session.get("cwd", "")
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            if source == "sqlite_v2":
                row = conn.execute(
                    "SELECT value FROM conversations_v2 WHERE conversation_id = ?",
                    (session_id,)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT value FROM conversations WHERE key = ?",
                    (cwd,)
                ).fetchone()
            if row:
                d = json.loads(row[0])
                return d.get("history", [])
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError, json.JSONDecodeError, OSError):
        pass
    return None


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
        # Assistant message - structure varies:
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


def _is_sqlite_subagent(history: list) -> bool:
    """Detect subagent sessions in SQLite v2 history.

    Subagent pattern: exactly 1 Prompt turn (the instruction) + at least 1
    ToolUseResults turn.  A real 1-turn conversation has a Prompt but no
    ToolUseResults, so it is kept as interactive.
    """
    prompt_turns = 0
    tool_result_turns = 0
    for entry in history:
        content = entry.get("user", {}).get("content", {})
        if "Prompt" in content:
            prompt_turns += 1
        if "ToolUseResults" in content:
            tool_result_turns += 1
    return prompt_turns == 1 and tool_result_turns >= 1


def _load_sqlite_sessions():
    """Load sessions from the SQLite database (v1 + v2 tables)."""
    sessions = []
    if not SQLITE_DB.exists():
        return sessions

    try:
        conn = sqlite3.connect(f"file:{SQLITE_DB}?mode=ro", uri=True)
    except (sqlite3.OperationalError, sqlite3.DatabaseError, PermissionError, OSError):
        # DB locked by Kiro, corrupted, or permission denied
        return sessions

    try:
        # V2 sessions (Dec 2025 - Mar 2026) - have timestamps and session IDs
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
                    # Handle None/0 timestamps gracefully
                    try:
                        created = datetime.fromtimestamp((created_ms or 0) / 1000).strftime("%Y-%m-%dT%H:%M:%S")
                        updated = datetime.fromtimestamp((updated_ms or 0) / 1000).strftime("%Y-%m-%dT%H:%M:%S")
                        duration_min = max(0, int(((updated_ms or 0) - (created_ms or 0)) / 1000 / 60))
                    except (TypeError, ValueError, OSError):
                        created = ""
                        updated = ""
                        duration_min = 0
                    msg_count = len(history)
                    sessions.append({
                        "session_id": conv_id,
                        "title": title,
                        "cwd": cwd,
                        "created_at": created,
                        "updated_at": updated,
                        "source": "sqlite_v2",
                        "msg_count": msg_count,
                        "duration_min": duration_min,
                        "is_subagent": _is_sqlite_subagent(history),
                        "parent_session_id": None,
                    })
                except (json.JSONDecodeError, KeyError, ValueError, TypeError):
                    pass
        except sqlite3.OperationalError:
            pass

        # V1 sessions (Nov 2025 - Dec 2025) - keyed by directory, no timestamps
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
                        "is_subagent": False,  # SQLite sessions predate subagent feature
                        "parent_session_id": None,
                    })
                except (json.JSONDecodeError, KeyError, ValueError):
                    pass
        except sqlite3.OperationalError:
            pass
    finally:
        conn.close()

    return sessions


def _load_jsonl_sessions():
    """Load sessions from ~/.kiro/sessions/cli/*.json (v3: current format).
    
    Also loads .jsonl-only sessions (missing metadata file).
    """
    sessions = []
    if not SESSIONS_DIR.exists():
        return sessions

    seen_session_ids = set()
    
    # First pass: load sessions with .json metadata
    for json_file in SESSIONS_DIR.glob("*.json"):
        try:
            if json_file.stat().st_size > MAX_FILE_SIZE:
                continue
            with open(json_file, encoding="utf-8") as f:
                meta = json.load(f)
            created = meta.get("created_at") or ""
            updated = meta.get("updated_at") or ""
            jsonl_path = str(Path(json_file).with_suffix(".jsonl"))
            msg_count = 0
            # Compute duration
            duration_min = 0
            if created and updated:
                try:
                    c = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    u = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                    duration_min = int((u - c).total_seconds() / 60)
                except (ValueError, TypeError):
                    pass
            session_id = meta.get("session_id", "")
            if session_id:
                seen_session_ids.add(session_id)
            # Count messages via fast byte search
            jp = Path(jsonl_path)
            if jp.exists():
                try:
                    raw = jp.read_bytes()
                    msg_count = raw.count(b'"kind":"Prompt"') + raw.count(b'"kind":"AssistantMessage"')
                except OSError:
                    pass
            sessions.append({
                "session_id": session_id,
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
                "_search_text": None,  # Lazily populated on first search
            })
        except (json.JSONDecodeError, KeyError, ValueError, OSError):
            pass

    # Second pass: load .jsonl files without .json metadata
    for jsonl_file in SESSIONS_DIR.glob("*.jsonl"):
        json_file = jsonl_file.with_suffix(".json")
        if json_file.exists():
            continue  # Already processed above
        try:
            if jsonl_file.stat().st_size > MAX_FILE_SIZE:
                continue
            # Extract session_id from filename (UUID format)
            session_id = jsonl_file.stem
            if session_id in seen_session_ids:
                continue
            data = jsonl_file.read_bytes()
            msg_count = data.count(b'"kind":"Prompt"') + data.count(b'"kind":"AssistantMessage"')
            # Get file times as fallback
            stat = jsonl_file.stat()
            # Use st_mtime for both created/updated - st_ctime is not reliable
            # on Windows (it's metadata change time, not creation time)
            created = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%dT%H:%M:%S")
            updated = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%dT%H:%M:%S")
            duration_min = 0  # Cannot determine from file timestamps alone
            sessions.append({
                "session_id": session_id,
                "title": "(untitled)",
                "cwd": "",
                "created_at": created,
                "updated_at": updated,
                "source": "jsonl",
                "msg_count": msg_count,
                "duration_min": max(0, duration_min),
                "jsonl_path": str(jsonl_file),
                "is_subagent": False,
                "parent_session_id": None,
            })
        except (OSError, ValueError):
            pass

    return sessions


def get_sessions():
    """Load all sessions from all stores, deduplicated, sorted by recency."""
    jsonl = _load_jsonl_sessions()
    sqlite = _load_sqlite_sessions()

    # Deduplicate: if same session_id exists in both, prefer JSONL (newer format)
    # For sessions without session_id, use cwd as fallback dedup key
    seen_ids = {s["session_id"] for s in jsonl if s["session_id"]}
    seen_cwds = {s["cwd"] for s in jsonl if not s["session_id"] and s.get("cwd")}
    
    for s in sqlite:
        if s["session_id"]:
            if s["session_id"] not in seen_ids:
                jsonl.append(s)
                seen_ids.add(s["session_id"])
        else:
            # For sessions without ID, dedupe by cwd
            cwd = s.get("cwd", "")
            if cwd and cwd not in seen_cwds:
                jsonl.append(s)
                seen_cwds.add(cwd)

    # Sort: sessions with timestamps first (descending), then untimed ones at the end
    jsonl.sort(key=lambda s: s.get("updated_at") or s.get("created_at") or "0", reverse=True)
    return jsonl


def extract_messages(session, limit=None, offset=0):
    """Extract conversation messages from any session format.
    
    Args:
        session: Session dict
        limit: Max messages to return (None = all)
        offset: Number of messages to skip from start
    """
    # SQLite sessions: load history on demand from DB (lazy)
    if session.get("source") in ("sqlite_v1", "sqlite_v2") and "_history" not in session:
        history = _load_sqlite_history(session)
        if history is None:
            return []
    elif "_history" in session:
        history = session["_history"]
    else:
        history = None

    if history is not None:
        msgs = _extract_messages_from_history(history, limit=None if offset else limit)
        if offset:
            msgs = msgs[offset:]
            if limit:
                msgs = msgs[:limit]
        return msgs

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
    skipped = 0
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
                    # Skip until we reach offset
                    if skipped < offset:
                        skipped += 1
                        continue
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
            # SQLite sessions - search inline history
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
            # JSONL sessions - use/build search cache lazily
            jsonl_path = Path(session["jsonl_path"])
            if not jsonl_path.exists() or jsonl_path.stat().st_size == 0:
                continue
            if jsonl_path.stat().st_size > MAX_FILE_SIZE:
                continue

            # Build cache on first search for this session
            if session.get("_search_text") is None:
                search_parts = []
                try:
                    with open(jsonl_path, encoding="utf-8") as f:
                        for line in f:
                            try:
                                d = json.loads(line)
                                if d.get("kind") not in ("Prompt", "AssistantMessage"):
                                    continue
                                for block in d.get("data", {}).get("content", []):
                                    if isinstance(block, dict) and block.get("kind") == "text":
                                        search_parts.append(block.get("data", ""))
                            except (json.JSONDecodeError, KeyError):
                                pass
                except OSError:
                    pass
                session["_search_text"] = " ".join(search_parts)

            if _fuzzy_match(query, session["_search_text"]):
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
        width: 80%;
        height: 40%;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
        align: center middle;
    }
    #rename-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    #rename-input {
        margin: 1 0;
        width: 100%;
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

    @on(Input.Submitted, "#rename-input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in rename input."""
        self.action_save()

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
        # Escape Rich markup characters to prevent rendering issues
        title = title.replace("[", "\\[").replace("]", "\\]")
        cwd = os.path.basename(self.session.get("cwd") or "")
        msgs = self.session.get("msg_count", 0)
        dur = self.session.get("duration_min", 0)
        dur_str = "-" if dur == 0 else (f"{dur}m" if dur < 60 else f"{dur // 60}h {dur % 60}m")
        yield Static(
            f"[bold]{title}[/bold]\n"
            f"[dim]{cwd}[/dim]  [dim italic]{ts}[/dim italic]  [dim cyan]{msgs} msgs[/dim cyan]  [dim green]{dur_str}[/dim green]",
            markup=True,
        )


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
        Binding("ctrl+f", "search_content", "Focus search"),
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
        # Settings
        self._trust_all_tools = True  # Default: enabled
        self._show_single_turn = False  # Default: hide single-turn sessions
        self._show_untitled = False  # Default: hide untitled sessions
        self._viewer_search_query = ""
        # Lazy loading state
        self._preview_messages = []  # Messages loaded so far
        self._preview_all_loaded = False  # Whether all messages are loaded
        self._preview_batch_size = 30  # Messages per batch
        self._preview_loading_session_id = None  # Guard for race condition
        self._sessions_loading = True  # Whether sessions are still loading
        self._search_id = 0  # Counter for search debounce

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

    def _toggle_trust_all_tools(self) -> None:
        self._trust_all_tools = not self._trust_all_tools
        status = "enabled" if self._trust_all_tools else "disabled"
        self.notify(f"--trust-all-tools {status}")

    def _toggle_single_turn(self) -> None:
        self._show_single_turn = not self._show_single_turn
        self._refresh_sessions()
        status = "shown" if self._show_single_turn else "hidden"
        self.notify(f"Single-turn sessions {status}")

    def _toggle_untitled(self) -> None:
        self._show_untitled = not self._show_untitled
        self._refresh_sessions()
        status = "shown" if self._show_untitled else "hidden"
        self.notify(f"Untitled sessions {status}")

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
            except Exception:
                # Clean up temp file if rename failed
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
                        if row:
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
                        if row:
                            data = json.loads(row[0])
                            data["title"] = new_title
                            conn.execute(
                                f"UPDATE {table} SET value = ? WHERE {id_col} = ?",
                                (json.dumps(data), lookup_key)
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
        try:
            sessions = get_sessions()
        except Exception as e:
            self._sessions_loading = False
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
            
        self.all_sessions = sessions
        self._sessions_loading = False
        # Apply filters and populate list
        self.call_from_thread(self._refresh_sessions)
        self.call_from_thread(
            self.query_one("#status-bar", Static).update,
            f" {len(sessions)} sessions | Ctrl+R resume | / search | Ctrl+P menu"
        )
        # If user typed search query while loading, apply it now
        def apply_search():
            search = self.query_one("#search-input", Input)
            if search.value:
                self._search_id += 1
                self._do_search(search.value, self._search_id)
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
        # Increment search ID to invalidate stale results
        self._search_id += 1
        self._do_search(event.value, self._search_id)

    def on_key(self, event) -> None:
        """Handle key events for navigation."""
        search_input = self.query_one("#search-input", Input)
        list_view = self.query_one("#session-list", ListView)
        preview = self.query_one("#preview", RichLog)

        # Skip special key handling when Input has focus (allow normal typing)
        if search_input.has_focus:
            # Only handle down/j to move to session list
            if event.key in ("down", "j"):
                event.prevent_default()
                event.stop()
                list_view.focus()
            return

        # Session list navigation: j/k for up/down
        if list_view.has_focus:
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

        # / to focus search (only when not in Input)
        if event.key == "slash":
            event.prevent_default()
            event.stop()
            search_input.focus()
            return

    @work(thread=True)
    def _do_search(self, query: str, search_id: int = 0) -> None:
        # Search within currently filtered base (respects single-turn/untitled toggles)
        base = self._get_filtered_base()
        results = search_sessions(query, base)
        
        # Check if this search is still current (not superseded by newer search)
        if search_id and self._search_id != search_id:
            return  # Stale result, discard
        
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
            self.notify("Cannot resume: session has no ID", severity="error")
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
