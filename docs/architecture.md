# Architecture

## File structure

```
kiro_history.py          Main application (single-file TUI)
install.sh               Linux/macOS installer
install.ps1              Windows installer (PowerShell)
install.bat              Windows entry point (delegates to install.ps1)
uninstall.sh             Linux/macOS uninstaller
uninstall.ps1            Windows uninstaller
uninstall.bat            Windows entry point
bin/kiro-cli-history     Dev launcher (repo root only, uses system python)
tests/                   pytest unit tests
docs/                    Documentation
pyproject.toml           Build/test config
```

## Data flow

```
get_sessions()
  |- _load_jsonl_sessions()    reads ~/.kiro/sessions/cli/*.json + *.jsonl
  |- _load_sqlite_sessions()   reads platform SQLite DB (read-only URI)
  |- dedup by session_id (prefer JSONL) or cwd (for empty session_id)
  |- sort by updated_at descending
  v
KiroHistory.all_sessions

on filter toggle / load:
  _refresh_sessions()
    |- _get_filtered_base()    apply _show_single_turn, _show_untitled
    |- if search query -> _do_search(query, search_id)  [background worker]
    |- else -> _populate_list()  [main thread]

on session select:
  _load_preview(session)  [background worker]
    |- extract_messages(session, limit=30)
    |- update _preview_messages on main thread (guard: _preview_loading_session_id)
    |- _render_messages()

on load more:
  _load_more_messages()  [background worker]
    |- extract_messages(session, limit=30, offset=len(_preview_messages))
    |- extend _preview_messages on main thread
```

## Key design decisions

### Single-file architecture
All code in `kiro_history.py`. Intentional: simplifies installation
(copy one file), reduces import complexity, matches upstream convention.

### msg_count semantics differ by source
- JSONL: counts individual `"kind":"Prompt"` and `"kind":"AssistantMessage"`
  lines via byte search. 1 full exchange = 2 lines.
- SQLite: `len(history)` where each entry is a full user+assistant pair.
  1 full exchange = 1 entry.
So the single-turn filter uses `<= 2` for JSONL and `<= 1` for SQLite.

### Thread safety model
- `all_sessions`: written once by _load_sessions_async, read-only after
- `filtered_sessions`: written only on main thread (via call_from_thread)
- `_preview_messages`: list written only on main thread (via call_from_thread)
- `_preview_loading_session_id`: read/written on main thread; worker threads
  read it as a guard before applying results
- `_search_id`: incremented on main thread; workers compare before applying

### Atomic file write (JSONL rename)
```python
temp_path = None
with tempfile.NamedTemporaryFile(..., dir=dir_path, delete=False) as tf:
    json.dump(metadata, tf, ...)
    temp_path = tf.name
os.replace(temp_path, json_path)  # atomic on POSIX; near-atomic on Windows
```
If os.replace fails, temp_path is cleaned up in except block.

### SQLite rename approach
Both V1 and V2 update the `value` JSON blob rather than a `title` column,
because the title is derived from history content, not stored separately.
- V1: key = cwd (the table's primary key)
- V2: key = conversation_id

### install.sh wrapper generation
Uses `mktemp` + `sed -i.bak` + `mv` pattern (not heredoc with variable
expansion) to avoid quoting issues with paths containing spaces and to ensure
atomic write. `sed -i.bak` works on both GNU (Linux) and BSD (macOS) sed.

### Windows path choice (C:\ProgramData)
%LOCALAPPDATA% can contain Korean/CJK characters on Korean Windows installs
(e.g., `C:\Users\홍길동\AppData\Local`). This causes encoding failures in
BAT files even with UTF-8. `C:\ProgramData` is always ASCII.

## Search implementation

`search_sessions(query, sessions)` uses fuzzy token matching:
- Splits query into tokens by whitespace
- Each token must appear as substring in title+cwd or message content
- JSONL: opens file and scans line by line
- SQLite: searches inline `_history` list

The `_do_search` worker uses `_search_id` to discard stale results when
the user types faster than searches complete.

## Session filtering

`_is_single_turn(session)` checks:
1. JSONL: `parent_session_id` present -> True (reliable subagent indicator)
2. JSONL: `msg_count <= 2` -> True
3. SQLite: `msg_count <= 1` -> True

`_show_untitled` filters sessions where title is None, "", or "(untitled)".

Both filters default to False (hidden). Toggle via Ctrl+P.
