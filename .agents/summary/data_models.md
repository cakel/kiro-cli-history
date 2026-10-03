# Data Models

## Session Dict

The primary data structure passed throughout the application. Created by `get_sessions()` and passed to `search_sessions()` and `extract_messages()`.

```python
{
    # Identity
    "session_id": str,          # UUID string, unique across all stores
    "title": str,               # Display title; "(untitled)" if none
    "cwd": str,                 # Working directory when session was created

    # Timestamps (ISO 8601 string)
    "created_at": str,
    "updated_at": str,

    # Source tracking
    "source": str,              # "jsonl" | "sqlite_v1" | "sqlite_v2" | "archive"

    # Session metadata
    "msg_count": int,           # Number of messages
    "duration_min": int | float, # Duration in minutes
    "is_subagent": bool,        # True if this is a sub-agent session
    "parent_session_id": str | None,  # Parent session ID for sub-agents

    # JSONL-specific
    "jsonl_path": str,          # (jsonl only) Path to .jsonl file
    "json_path": str,           # (jsonl only) Path to .json metadata sidecar

    # Archive-specific
    "archive_path": str,        # (archive only) Path to .json or .json.gz
    "archive_compressed": bool, # (archive only) Whether file is gzipped

    # Internal cache (session_store only)
    "_search_text": str,        # (jsonl, warm cache) Pre-built searchable text
    "_history": list | None,    # (archive, lazy) Raw history, None = not loaded
}
```

---

## Message Dict

Returned by `extract_messages()`. The unit of display in the preview pane.

```python
{
    "role": str,    # "you" (user) | "kiro" (assistant)
    "text": str,    # Message content (plain text or markdown)
}
```

---

## Config File Schema

Stored at `<data_dir>/kiro-cli-history.json`.

```json
{
  "schema_version": 1,
  "app_version": "v0.1.0-cakel.9",
  "settings": {
    "trust_all_tools": true,
    "show_single_turn": false,
    "show_untitled": false,
    "theme": "textual-dark",
    "debug": false,
    "retention_days": 90
  }
}
```

**Settings reference**:

| Key | Type | Default | Effect |
|-----|------|---------|--------|
| `trust_all_tools` | bool | `true` | Passes `--trust-all-tools` to `kiro chat --resume` |
| `show_single_turn` | bool | `false` | Show/hide single-exchange sessions in the list |
| `show_untitled` | bool | `false` | Show/hide sessions with no title |
| `theme` | str | `"textual-dark"` | Textual CSS theme name |
| `debug` | bool | `false` | Enable PERF/WARN log entries |
| `retention_days` | int | `90` | Days before archive `.json` → `.json.gz` (0 = unlimited) |

---

## JSONL Session Files (v3 format)

Kiro CLI writes two files per session in `~/.kiro/sessions/cli/`:

### Metadata sidecar (`.json`)
```json
{
  "session_id": "uuid-string",
  "title": "session title",
  "cwd": "/path/to/project",
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T01:00:00Z",
  "msg_count": 10,
  "duration_min": 15
}
```

### History file (`.jsonl`)
One JSON object per line. Each line is a history entry:

```json
{
  "user": {
    "content": {
      "Prompt": {
        "prompt": "user message text"
      }
    }
  },
  "assistant": {
    "content": {
      "Text": "assistant response text"
    }
  }
}
```

Alternative assistant content shapes:
```json
// Tool use response
{ "assistant": { "ToolUse": { "content": "text", "tool_uses": [{"name": "tool_name"}] } } }

// Response object
{ "assistant": { "Response": { "content": "text" } } }
```

---

## SQLite Schema

Database at platform path (e.g. `%LOCALAPPDATA%\kiro-cli\data.sqlite3`).

### v1 table: `conversations`

| Column | Type | Notes |
|--------|------|-------|
| `key` | TEXT | Working directory path (used as lookup key) |
| `value` | TEXT | JSON blob: `{"history": [...]}` |

### v2 table: `conversations_v2`

| Column | Type | Notes |
|--------|------|-------|
| `conversation_id` | TEXT | Session UUID |
| `value` | TEXT | JSON blob: `{"history": [...]}` |

The `value` JSON blob in both tables follows the same history entry format as JSONL.

---

## Archive File Schema

Files in `<data_dir>/archive/`. Either `.json` (recent) or `.json.gz` (compressed after retention cutoff).

```json
{
  "session_id": "uuid-string",
  "title": "session title",
  "cwd": "/path/to/project",
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T01:00:00Z",
  "msg_count": 10,
  "duration_min": 15,
  "is_subagent": false,
  "parent_session_id": null,
  "history": [
    // same history entry format as JSONL
  ]
}
```

---

## Log Entry Format

Written to `<data_dir>/kiro-cli-history.log`.

```
2026-10-02T21:22:44.123+09:00 [LEVEL] event_name key1=val1 key2=val2
```

**ERROR entries** include `ts=<epoch_ms>` for correlation:
```
2026-10-02T21:22:44.123+09:00 [ERROR] worker_crash ts=1759456964123 error="..." traceback="..."
```

**PERF example**:
```
2026-10-02T21:22:44.456+09:00 [PERF] app_start sessions=352 load_time=0.734 spanning_days=84
```
