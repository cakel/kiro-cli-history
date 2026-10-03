# Interfaces

## session_store.py Public API

This is the primary interface for all data operations. It is safe to import in tests and external tools (no Textual dependency).

### `get_sessions() -> list[dict]`

Returns a merged, deduplicated, recency-sorted list of all sessions from all stores.

**Returns**: List of session dicts (see [Data Models](data_models.md) for session dict schema)

**Source priority (deduplication)**: JSONL > SQLite v2 > SQLite v1 > Archive

---

### `search_sessions(query: str, sessions: list[dict]) -> list[dict]`

Fuzzy search across session title, CWD, and message content.

**Parameters**:
- `query` — search string; empty string returns all sessions
- `sessions` — list from `get_sessions()` (passed in to allow filtered subsets)

**Returns**: Filtered list of session dicts that match the query

**Search strategy** (in order):
1. Title and CWD match (always in-memory)
2. ripgrep subprocess on JSONL dir (cold cache, fast)
3. ripgrep subprocess on archive `.json.gz` files
4. Python `_fuzzy_match` on warm `_search_text` cache

---

### `extract_messages(session: dict, limit: int | None = None, offset: int = 0) -> list[dict]`

Extracts conversation messages from a session.

**Parameters**:
- `session` — session dict from `get_sessions()`
- `limit` — max number of messages to return (default: all)
- `offset` — number of messages to skip (for pagination/lazy loading)

**Returns**: List of message dicts `{"role": "you" | "kiro", "text": str}`

---

### `prebuild_cache(sessions: list[dict]) -> None`

Blocks until `_search_text` is built for all JSONL sessions. Call from a background thread.

---

### `start_cache_prebuild(sessions: list[dict]) -> threading.Thread`

Non-blocking. Launches `prebuild_cache` in a daemon thread and returns it.

---

### `sync_sqlite_to_archive(sessions: list[dict], retention_days: int = 90) -> None`

Exports new SQLite sessions to archive directory as JSON. Compresses `.json` files older than `retention_days` to `.json.gz`.

---

## config.py Public API

### `load_config() -> dict`

Reads config from disk and merges with defaults. Returns a dict guaranteed to have all keys.

**Returns**: Dict with keys: `trust_all_tools`, `show_single_turn`, `show_untitled`, `theme`, `debug`, `retention_days`

---

### `save_config(settings: dict) -> tuple[bool, str]`

Saves settings atomically. Filters out unknown keys.

**Returns**: `(True, "")` on success, `(False, error_message)` on failure

---

### `get_setting(key: str, default=None) -> Any`

Convenience wrapper: loads config and returns a single key.

---

### `get_data_dir() -> Path`

Returns the app data directory, creating it if necessary.

---

### `get_install_dir() -> Path`

Returns the directory where `kiro_history.py` is located.

---

## app_log.py Public API

### `init_logging(debug: bool = False) -> None`

Must be called once at app start. Idempotent (second call is a no-op).

---

### `log_perf(event: str, **kwargs) -> None`

Writes a `[PERF]` entry. Only written when `debug=True`.

---

### `log_warn(event: str, **kwargs) -> None`

Writes a `[WARN]` entry. Only written when `debug=True`.

---

### `log_error(event: str, **kwargs) -> None`

Writes an `[ERROR]` entry. **Always written** regardless of debug mode.

---

### `close_logging() -> None`

Flushes and closes the log file. Call on app exit.

---

## KiroHistory Textual Bindings (Keyboard Interface)

| Key | Action | Description |
|-----|--------|-------------|
| `/` | `focus_search` | Focus the search input |
| `p` | `focus_path` | Focus the path filter input |
| `Ctrl+R` | `resume` | Resume selected session in Kiro CLI |
| `Ctrl+N` | `new_session` | Start a new Kiro CLI session |
| `Alt+N` | `new_session_history` | Resume session, choose a different directory |
| `Ctrl+F` | `open_preview_search` | Open in-preview search bar |
| `Ctrl+Y` | `copy_conversation` | Copy full conversation to clipboard |
| `Ctrl+X` | `export_session` | Export session as markdown |
| `F2` | `rename_session` | Rename selected session |
| `Ctrl+Del` | `delete_session` | Delete selected session |
| `Escape` | `clear_or_quit` | Clear search / close dialogs / quit (triple ESC) |
| `Ctrl+Q` | `quit_app` | Exit |
| `Right` / `l` | `focus_preview` | Focus preview pane |
| `Left` / `h` | `focus_list` | Focus session list |
| `j` / `k` | cursor down / up | Navigate session list (handled in `on_key`) |
| `Space` / `m` / `M` | page scroll | Scroll preview (handled in `on_key`) |
| `?` | `toggle_keys_help` | Show/hide keyboard shortcuts screen |
| `Ctrl+P` | Command Palette | Textual built-in (theme, export, settings) |

## Widget Message Interface

### `PreviewSearchInput.PrevMatchRequested`

Posted when `Shift+Tab` is pressed in the preview search input. Consumed by `KiroHistory.on_preview_search_input_prev_match_requested()`.

### Modal Screen Return Values

All modal screens return a value via `self.dismiss(value)`:

| Screen | Return type | Meaning |
|--------|-------------|---------|
| `DeleteConfirmScreen` | `bool` | `True` = confirmed delete |
| `DirConfirmScreen` | `str \| None` | Chosen directory path, or None = cancel |
| `RenameScreen` | `str \| None` | New name string, or None = cancel |
| `ThemePickerScreen` | `str \| None` | Theme name, or None = cancel |
| `RetentionPickerScreen` | `int \| None` | Retention days, or None = cancel |
| `MissingDirScreen` | `str \| None` | Alternative directory, or None = cancel |

## External Process Interface

### Resuming a session

```python
subprocess.run(
    ["kiro", "chat", "--resume", session_id, "--trust-all-tools"],
    cwd=session_cwd,
)
```

`--trust-all-tools` is added when `trust_all_tools` setting is `True`.

### Deleting a session

```python
subprocess.run(["kiro", "chat", "--delete-session", session_id])
```

Delegated to Kiro CLI rather than deleting files directly.

### ripgrep subprocess

```bash
# Cold-cache JSONL search
rg --files-with-matches -F -i --max-filesize 100M <query> <jsonl_dir>

# Archive .json.gz search
rg -z --files-with-matches -F -i <query> <archive_dir>
```
