"""session_store.py — Pure data/search layer for kiro-cli-history.

All I/O, parsing, and search logic lives here.
No Textual or UI imports — safe to import in tests and CLI tools.

Public API:
    get_sessions()             -> list[dict]
    search_sessions(q, sess)   -> list[dict]
    extract_messages(sess, ...) -> list[dict]
    prebuild_cache(sessions)   -> None  (blocks; call in a thread)
    start_cache_prebuild(sessions) -> threading.Thread  (non-blocking)
    sync_sqlite_to_archive(sessions, retention_days) -> None
"""

import gzip
import json
import os
import sqlite3
import subprocess
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_DEMO_DIR = os.environ.get("KIRO_DEMO_DIR", "")
if _DEMO_DIR:
    _DEMO_DIR = str(Path(_DEMO_DIR).resolve())

SESSIONS_DIR: Path = (
    Path(_DEMO_DIR) / "kiro" / "sessions" / "cli"
    if _DEMO_DIR
    else Path.home() / ".kiro" / "sessions" / "cli"
)

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB guard


def _get_archive_dir() -> Path:
    """Archive directory — respects KIRO_DEMO_DIR for test isolation."""
    # Demo/test mode: keep archive inside demo dir to avoid polluting real data
    if _DEMO_DIR:
        return Path(_DEMO_DIR) / "kiro-cli-history" / "archive"
    try:
        from config import get_data_dir
        return get_data_dir() / "archive"
    except ImportError:
        env = os.environ.get("KIRO_HISTORY_DATA_DIR", "")
        if env:
            return Path(env) / "archive"
        if os.name == "nt":
            return Path(r"C:\ProgramData\kiro-cli-history\data\archive")
        return Path.home() / ".local" / "share" / "kiro-cli-history" / "data" / "archive"


# ---------------------------------------------------------------------------
# Archive helpers
# ---------------------------------------------------------------------------

def _read_archive_file(path: Path) -> dict | None:
    """Read a .json or .json.gz archive file, return parsed dict or None."""
    try:
        if path.name.endswith(".json.gz"):
            with gzip.open(path, "rb") as f:
                return json.loads(f.read().decode("utf-8"))
        else:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        return None


def _archive_id_from_path(path: Path) -> str:
    """Extract session_id from archive filename (strips .json or .json.gz)."""
    name = path.name
    if name.endswith(".json.gz"):
        return name[: -len(".json.gz")]
    if name.endswith(".json"):
        return name[: -len(".json")]
    return name


def _load_archive_sessions() -> list:
    """Load session metadata from archive dir. History is lazy-loaded on search."""
    archive_dir = _get_archive_dir()
    if not archive_dir.exists():
        return []
    sessions = []
    for path in archive_dir.iterdir():
        compressed = path.name.endswith(".json.gz")
        if not compressed and not path.name.endswith(".json"):
            continue
        data = _read_archive_file(path)
        if not data:
            continue
        session_id = data.get("session_id", "") or _archive_id_from_path(path)
        if not session_id:
            continue
        sessions.append({
            "session_id": session_id,
            "title": data.get("title") or "(untitled)",
            "cwd": data.get("cwd") or "",
            "created_at": data.get("created_at") or "",
            "updated_at": data.get("updated_at") or "",
            "source": "archive",
            "msg_count": data.get("msg_count", 0),
            "duration_min": data.get("duration_min", 0),
            "is_subagent": data.get("is_subagent", False),
            "parent_session_id": data.get("parent_session_id"),
            "archive_path": str(path),
            "archive_compressed": compressed,
            "_history": None,  # lazy-loaded on first search
        })
    return sessions


def _load_archive_history(session: dict) -> list:
    """Decompress and return history for an archive session (lazy)."""
    path = session.get("archive_path", "")
    if not path:
        return []
    data = _read_archive_file(Path(path))
    return data.get("history", []) if data else []


def sync_sqlite_to_archive(sqlite_sessions: list, retention_days: int = 90) -> None:
    """Export new SQLite sessions to archive, compress entries older than retention_days.

    - New SQLite sessions → <archive_dir>/<session_id>.json
    - .json files with mtime older than retention_days → compressed to .json.gz, original deleted
    """
    archive_dir = _get_archive_dir()
    archive_dir.mkdir(parents=True, exist_ok=True)

    # Collect existing archive IDs (both compressed and plain)
    existing_ids = {
        _archive_id_from_path(p)
        for p in archive_dir.iterdir()
        if p.name.endswith(".json") or p.name.endswith(".json.gz")
    }

    # Export new SQLite sessions
    for session in sqlite_sessions:
        session_id = session.get("session_id", "")
        if not session_id or session_id in existing_ids:
            continue
        history = _load_sqlite_history(session) or []
        export = {
            "session_id": session_id,
            "title": session.get("title") or "",
            "cwd": session.get("cwd") or "",
            "created_at": session.get("created_at") or "",
            "updated_at": session.get("updated_at") or "",
            "msg_count": session.get("msg_count", 0),
            "duration_min": session.get("duration_min", 0),
            "is_subagent": session.get("is_subagent", False),
            "parent_session_id": session.get("parent_session_id"),
            "history": history,
        }
        out_path = archive_dir / f"{session_id}.json"
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(export, f, ensure_ascii=False)
            existing_ids.add(session_id)
        except OSError:
            pass

    # Compress .json files older than retention_days (0 = unlimited, skip compression)
    if not retention_days:
        return
    cutoff = datetime.now() - timedelta(days=retention_days)
    for json_path in list(archive_dir.glob("*.json")):
        try:
            mtime = datetime.fromtimestamp(json_path.stat().st_mtime)
            if mtime < cutoff:
                gz_path = json_path.parent / (json_path.name + ".gz")
                with open(json_path, "rb") as f_in:
                    with gzip.open(gz_path, "wb", compresslevel=6) as f_out:
                        f_out.write(f_in.read())
                json_path.unlink()
        except OSError:
            pass


def _sqlite_db_path() -> Path:
    if _DEMO_DIR:
        return Path(_DEMO_DIR) / "kiro-cli" / "data.sqlite3"
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        base = Path(local) if local else Path.home() / "AppData" / "Local"
        return base / "kiro-cli" / "data.sqlite3"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "kiro-cli" / "data.sqlite3"
    xdg = os.environ.get("XDG_DATA_HOME", "")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "kiro-cli" / "data.sqlite3"


SQLITE_DB: Path = _sqlite_db_path()

# ---------------------------------------------------------------------------
# SQLite helpers
# ---------------------------------------------------------------------------

def _load_sqlite_history(session: dict) -> list | None:
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
                    (session_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT value FROM conversations WHERE key = ?",
                    (cwd,),
                ).fetchone()
            if row:
                d = json.loads(row[0])
                return d.get("history", [])
        finally:
            conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError, json.JSONDecodeError, OSError):
        pass
    return None


def _extract_messages_from_history(history, limit=None, offset=0):
    messages = []
    skipped = 0
    for entry in history:
        # Some SQLite v2 sessions store history as a list of lists rather than
        # a list of dicts. Skip non-dict entries instead of crashing.
        if not isinstance(entry, dict):
            continue
        user = entry.get("user", {})
        content = user.get("content", {})
        if "Prompt" in content:
            prompt_text = content["Prompt"].get("prompt", "")
            if prompt_text:
                if skipped < offset:
                    skipped += 1
                else:
                    messages.append({"role": "you", "text": prompt_text})
                    if limit and len(messages) >= limit:
                        return messages
        assistant = entry.get("assistant", {})
        if isinstance(assistant, dict):
            a_content = assistant.get("content", {})
            if "Text" in a_content:
                if skipped < offset:
                    skipped += 1
                else:
                    messages.append({"role": "kiro", "text": a_content["Text"]})
                    if limit and len(messages) >= limit:
                        return messages
            elif "Response" in assistant:
                resp = assistant["Response"]
                if isinstance(resp, dict) and resp.get("content"):
                    if skipped < offset:
                        skipped += 1
                    else:
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
                        if skipped < offset:
                            skipped += 1
                        else:
                            messages.append({"role": "kiro", "text": display})
                            if limit and len(messages) >= limit:
                                return messages
    return messages


def _get_first_prompt_from_history(history):
    for entry in history:
        if not isinstance(entry, dict):
            continue
        user = entry.get("user", {})
        content = user.get("content", {})
        if "Prompt" in content:
            txt = content["Prompt"].get("prompt", "").strip()
            if txt:
                return txt[:60]
    return "(untitled)"


def _is_sqlite_subagent(history: list) -> bool:
    prompt_turns = 0
    tool_result_turns = 0
    for entry in history:
        if not isinstance(entry, dict):
            continue
        content = entry.get("user", {}).get("content", {})
        if "Prompt" in content:
            prompt_turns += 1
        if "ToolUseResults" in content:
            tool_result_turns += 1
    return prompt_turns == 1 and tool_result_turns >= 1


def _load_sqlite_sessions() -> list:
    sessions = []
    if not SQLITE_DB.exists():
        return sessions
    try:
        conn = sqlite3.connect(f"file:{SQLITE_DB}?mode=ro", uri=True)
    except (sqlite3.OperationalError, sqlite3.DatabaseError, PermissionError, OSError):
        return sessions
    try:
        # V2
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
                    try:
                        created = datetime.fromtimestamp((created_ms or 0) / 1000).strftime("%Y-%m-%dT%H:%M:%S")
                        updated = datetime.fromtimestamp((updated_ms or 0) / 1000).strftime("%Y-%m-%dT%H:%M:%S")
                        duration_min = max(0, int(((updated_ms or 0) - (created_ms or 0)) / 1000 / 60))
                    except (TypeError, ValueError, OSError):
                        created = updated = ""
                        duration_min = 0
                    sessions.append({
                        "session_id": conv_id,
                        "title": title,
                        "cwd": cwd,
                        "created_at": created,
                        "updated_at": updated,
                        "source": "sqlite_v2",
                        "msg_count": len(history),
                        "duration_min": duration_min,
                        "is_subagent": _is_sqlite_subagent(history),
                        "parent_session_id": None,
                    })
                except (json.JSONDecodeError, KeyError, ValueError, TypeError):
                    pass
        except sqlite3.OperationalError:
            pass

        # V1
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
                        "is_subagent": False,
                        "parent_session_id": None,
                    })
                except (json.JSONDecodeError, KeyError, ValueError, TypeError):
                    pass
        except sqlite3.OperationalError:
            pass
    finally:
        conn.close()
    return sessions


def _load_jsonl_sessions() -> list:
    sessions = []
    if not SESSIONS_DIR.exists():
        return sessions

    seen_session_ids: set = set()

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
                "_search_text": None,
            })
        except (json.JSONDecodeError, KeyError, ValueError, OSError):
            pass

    for jsonl_file in SESSIONS_DIR.glob("*.jsonl"):
        json_file = jsonl_file.with_suffix(".json")
        if json_file.exists():
            continue
        try:
            if jsonl_file.stat().st_size > MAX_FILE_SIZE:
                continue
            session_id = jsonl_file.stem
            if session_id in seen_session_ids:
                continue
            data = jsonl_file.read_bytes()
            msg_count = data.count(b'"kind":"Prompt"') + data.count(b'"kind":"AssistantMessage"')
            stat = jsonl_file.stat()
            created = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%dT%H:%M:%S")
            updated = created
            sessions.append({
                "session_id": session_id,
                "title": "(untitled)",
                "cwd": "",
                "created_at": created,
                "updated_at": updated,
                "source": "jsonl",
                "msg_count": msg_count,
                "duration_min": 0,
                "jsonl_path": str(jsonl_file),
                "is_subagent": False,
                "parent_session_id": None,
            })
        except (OSError, ValueError):
            pass

    return sessions


def get_sessions() -> list:
    """Load all sessions from all stores, deduplicated, sorted by recency."""
    jsonl = _load_jsonl_sessions()
    sqlite = _load_sqlite_sessions()
    archive = _load_archive_sessions()

    seen_ids = {s["session_id"] for s in jsonl if s["session_id"]}
    seen_cwds = {s["cwd"] for s in jsonl if not s["session_id"] and s.get("cwd")}

    for s in sqlite:
        if s["session_id"]:
            if s["session_id"] not in seen_ids:
                jsonl.append(s)
                seen_ids.add(s["session_id"])
        else:
            cwd = s.get("cwd", "")
            if cwd and cwd not in seen_cwds:
                jsonl.append(s)
                seen_cwds.add(cwd)

    # Archive: only add sessions not already covered by live sources
    for s in archive:
        sid = s["session_id"]
        if sid and sid not in seen_ids:
            jsonl.append(s)
            seen_ids.add(sid)

    jsonl.sort(
        key=lambda s: s.get("updated_at") or s.get("created_at") or "0",
        reverse=True,
    )
    return jsonl


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
# ripgrep acceleration (optional — falls back to Python when rg not found)
# ---------------------------------------------------------------------------

_RG_AVAILABLE: bool | None = None


def _rg_path() -> str:
    """Return path to ripgrep: bundled binary first, then system PATH fallback."""
    exe = "rg.exe" if os.name == "nt" else "rg"
    try:
        from config import get_install_dir
        bundled = get_install_dir() / "bin" / exe
        if bundled.exists():
            return str(bundled)
    except Exception:
        pass
    return "rg"  # system PATH fallback


def _rg_available() -> bool:
    """Check once whether ripgrep is usable (bundled or on PATH); cache result."""
    global _RG_AVAILABLE
    if _RG_AVAILABLE is None:
        try:
            r = subprocess.run([_rg_path(), "--version"], capture_output=True, timeout=3)
            _RG_AVAILABLE = r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            _RG_AVAILABLE = False
    return _RG_AVAILABLE


def _rg_find_in_dir(tokens: list[str], search_dir: Path,
                    glob: str = "*.jsonl", compressed: bool = False) -> "set[str] | None":
    """Return set of file paths where ALL tokens match (rg per-token + intersect).

    Args:
        tokens:      Query tokens (all must match — same semantics as _fuzzy_match).
        search_dir:  Directory to search.
        glob:        File glob filter (e.g. '*.jsonl', '*.json').
        compressed:  Pass -z to rg for .gz files.

    Returns:
        set of matching file paths, empty set if rg ran but found nothing,
        or None if rg encountered an error (caller should fall back to Python).
    """
    if not tokens or not search_dir.exists():
        return set()

    rg = _rg_path()
    matching: "set[str] | None" = None
    for token in tokens:
        cmd = [rg, "--files-with-matches", "--fixed-strings", "--ignore-case",
               f"--glob={glob}"]
        if compressed:
            cmd.append("-z")
        cmd += ["--", token, str(search_dir)]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if result.returncode not in (0, 1):  # 0=match, 1=no match, others=error
                return None  # rg error — let caller fall back to Python
            found = set(result.stdout.splitlines())
            matching = found if matching is None else matching & found
            if not matching:
                break
        except (subprocess.TimeoutExpired, OSError):
            return None  # rg unavailable/timed out — let caller fall back to Python
    return matching if matching is not None else set()


# ---------------------------------------------------------------------------

def _fuzzy_match(query: str, text: str) -> bool:
    """All query tokens must appear in text (case-insensitive substring match)."""
    text_lower = text.lower()
    return all(token in text_lower for token in query.lower().split())


def _build_search_text(session: dict) -> str:
    """Build and cache the full-text search string for a JSONL session.

    Thread-safe: uses a per-session lock so concurrent calls (prebuild thread
    + on-demand search thread) never double-read the same file.  The lock is
    stored in session['_lock'] and created lazily on first use.

    Returns the cached string (empty string on error / oversized file).
    """
    # Fast path: already built (no lock needed for a read of a set value)
    cached = session.get("_search_text")
    if cached is not None:
        return cached

    # Acquire per-session lock (create lazily; two threads may both try to
    # create it — use setdefault which is atomic under the GIL)
    lock = session.setdefault("_lock", threading.Lock())

    with lock:
        # Re-check inside lock in case another thread just finished
        cached = session.get("_search_text")
        if cached is not None:
            return cached

        jsonl_path = Path(session.get("jsonl_path", ""))
        if not jsonl_path.exists() or jsonl_path.stat().st_size == 0:
            session["_search_text"] = ""
            return ""
        if jsonl_path.stat().st_size > MAX_FILE_SIZE:
            session["_search_text"] = ""
            return ""

        parts = []
        try:
            with open(jsonl_path, encoding="utf-8") as f:
                for line in f:
                    try:
                        d = json.loads(line)
                        if d.get("kind") not in ("Prompt", "AssistantMessage"):
                            continue
                        for block in d.get("data", {}).get("content", []):
                            if isinstance(block, dict) and block.get("kind") == "text":
                                parts.append(block.get("data", ""))
                    except (json.JSONDecodeError, KeyError):
                        pass
        except OSError:
            pass

        text = " ".join(parts)
        session["_search_text"] = text
        return text


def prebuild_cache(sessions: list, *, on_progress=None) -> None:
    """Synchronously build _search_text for all JSONL sessions that lack it.

    Args:
        sessions: list of session dicts (mutated in-place).
        on_progress: optional callable(done, total) called after each file.
    """
    targets = [
        s for s in sessions
        if s.get("source") == "jsonl" and s.get("_search_text") is None
    ]
    total = len(targets)
    for i, s in enumerate(targets, 1):
        _build_search_text(s)
        if on_progress:
            on_progress(i, total)


def start_cache_prebuild(sessions: list, *, on_progress=None) -> threading.Thread:
    """Start background thread that calls prebuild_cache().

    Returns the Thread so the caller can join() if needed.
    The thread is daemon so it won't block process exit.
    """
    t = threading.Thread(
        target=prebuild_cache,
        args=(sessions,),
        kwargs={"on_progress": on_progress},
        daemon=True,
        name="cache-prebuild",
    )
    t.start()
    return t


def _search_history(query: str, history: list) -> bool:
    """Return True if query matches any text in a SQLite/archive history list."""
    for entry in history:
        if not isinstance(entry, dict):
            continue
        user = entry.get("user", {})
        content = user.get("content", {})
        if "Prompt" in content and _fuzzy_match(query, content["Prompt"].get("prompt", "")):
            return True
        assistant = entry.get("assistant", {})
        if isinstance(assistant, dict):
            a_content = assistant.get("content", {})
            if "Text" in a_content and _fuzzy_match(query, a_content["Text"]):
                return True
            if "Response" in assistant:
                resp = assistant["Response"]
                if isinstance(resp, dict) and _fuzzy_match(query, resp.get("content", "")):
                    return True
            if "ToolUse" in assistant:
                tu = assistant["ToolUse"]
                if isinstance(tu, dict) and _fuzzy_match(query, tu.get("content", "")):
                    return True
    return False


def search_sessions(query: str, sessions: list) -> list:
    """Fuzzy-search sessions by title, cwd, and conversation content.

    JSONL sessions: uses _search_text cache (warm) or ripgrep / Python (cold).
    Archive sessions: uses ripgrep -z for .gz when available, Python fallback.
    SQLite sessions: lazy Python (binary DB, rg can't help).
    """
    if not query:
        return sessions

    tokens = query.lower().split()

    # --- Pre-build rg match sets (one subprocess call per directory) ---
    rg_jsonl_matched: set[str] | None = None   # set of jsonl_path strings
    rg_archive_matched: set[str] | None = None  # set of archive_path strings

    if _rg_available():
        # Only run rg for JSONL if there are cold-cache sessions
        if any(s.get("source") == "jsonl" and s.get("_search_text") is None
               for s in sessions):
            rg_jsonl_matched = _rg_find_in_dir(tokens, SESSIONS_DIR, glob="*.jsonl")

        # Archive: run for both plain and compressed
        if any(s.get("source") == "archive" for s in sessions):
            archive_dir = _get_archive_dir()
            plain = _rg_find_in_dir(tokens, archive_dir, glob="*.json")
            gz = _rg_find_in_dir(tokens, archive_dir, glob="*.json.gz", compressed=True)
            rg_archive_matched = plain | gz

    # --- Per-session matching ---
    results = []
    for session in sessions:
        title = session.get("title") or ""
        cwd = session.get("cwd") or ""
        # Fast path: title / cwd match (always in-memory)
        if _fuzzy_match(query, title) or _fuzzy_match(query, cwd):
            results.append(session)
            continue

        source = session.get("source", "")

        if source in ("sqlite_v1", "sqlite_v2"):
            # Binary DB — rg can't help; lazy-load history
            history = session.get("_history")
            if history is None:
                history = _load_sqlite_history(session) or []
                session["_history"] = history
            if _search_history(query, history):
                results.append(session)

        elif source == "archive":
            archive_path = session.get("archive_path", "")
            if rg_archive_matched is not None:
                # rg result is authoritative for this search round
                if archive_path in rg_archive_matched:
                    results.append(session)
            else:
                # Python fallback
                history = session.get("_history")
                if history is None:
                    history = _load_archive_history(session) or []
                    session["_history"] = history
                if _search_history(query, history):
                    results.append(session)

        elif source == "jsonl":
            search_text = session.get("_search_text")
            if search_text is not None:
                # Warm cache — fast Python match
                if _fuzzy_match(query, search_text):
                    results.append(session)
            elif rg_jsonl_matched is not None:
                # Cold cache — use rg result; leave _search_text=None for prebuild
                if session.get("jsonl_path", "") in rg_jsonl_matched:
                    results.append(session)
            else:
                # rg not available — Python fallback, populates cache
                search_text = _build_search_text(session)
                if _fuzzy_match(query, search_text):
                    results.append(session)

    return results


# ---------------------------------------------------------------------------
# Message extraction
# ---------------------------------------------------------------------------

def extract_messages(session: dict, limit=None, offset: int = 0) -> list:
    """Extract conversation messages from any session format.

    Args:
        session: Session dict.
        limit:   Max messages to return (None = all).
        offset:  Number of messages to skip from start.
    """
    if session.get("source") in ("sqlite_v1", "sqlite_v2") and "_history" not in session:
        history = _load_sqlite_history(session)
        if history is None:
            history = []
        session["_history"] = history  # cache (even if empty) to avoid repeated DB access
    elif "_history" in session:
        history = session["_history"]
    else:
        history = None

    if history is not None:
        return _extract_messages_from_history(history, limit=limit, offset=offset)

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
                # Collect ALL text blocks (not just the first one)
                txt_parts = []
                for block in data.get("content", []) if isinstance(data.get("content"), list) else []:
                    if isinstance(block, dict) and block.get("kind") == "text":
                        txt_parts.append(block.get("data", ""))
                txt = "\n".join(txt_parts)
                # Include message even if text is empty (to keep indices aligned)
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


# ---------------------------------------------------------------------------
# CLI self-check (ponytail: smallest runnable check)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import time

    print("=== session_store self-check ===\n")

    t0 = time.perf_counter()
    sessions = get_sessions()
    t1 = time.perf_counter()
    print(f"get_sessions(): {len(sessions)} sessions in {t1-t0:.3f}s")

    from collections import Counter
    print("Sources:", dict(Counter(s["source"] for s in sessions)))

    # Cold search (no cache)
    query = sys.argv[1] if len(sys.argv) > 1 else "에이스플레이어"
    t0 = time.perf_counter()
    results = search_sessions(query, sessions)
    t1 = time.perf_counter()
    print(f'\nCold search "{query}": {len(results)} results in {t1-t0:.3f}s')

    # Warm search (cache populated by first search)
    t0 = time.perf_counter()
    results2 = search_sessions(query, sessions)
    t1 = time.perf_counter()
    print(f'Warm search "{query}": {len(results2)} results in {t1-t0:.3f}s')

    cached = sum(1 for s in sessions if s.get("_search_text") is not None)
    print(f"Cache built: {cached}/{len(sessions)} sessions")

    # Prebuild remaining cache in background
    print("\nStarting background prebuild...")
    t0 = time.perf_counter()
    thread = start_cache_prebuild(sessions)
    thread.join()
    t1 = time.perf_counter()
    cached_after = sum(1 for s in sessions if s.get("_search_text") is not None)
    print(f"Background prebuild done: {cached_after}/{len(sessions)} cached in {t1-t0:.3f}s")

    # Search again after full prebuild
    t0 = time.perf_counter()
    results3 = search_sessions(query, sessions)
    t1 = time.perf_counter()
    print(f'Post-prebuild search "{query}": {len(results3)} results in {t1-t0:.3f}s')

    print("\n=== OK ===")
