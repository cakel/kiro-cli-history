# How it works

## Session storage formats

Kiro CLI stores conversations in three formats:

| Format | Location | Used by |
|--------|----------|---------|
| v3 (JSONL) | `~/.kiro/sessions/cli/*.json` + `*.jsonl` | Current kiro-cli |
| v2 (SQLite) | platform path, `conversations_v2` table | Older kiro-cli |
| v1 (SQLite) | same database, `conversations` table | Legacy |
| Archive | `<data_dir>/archive/*.json[.gz]` | kiro-cli-history backup |

SQLite database paths:
- macOS: `~/Library/Application Support/kiro-cli/data.sqlite3`
- Windows: `%LOCALAPPDATA%\kiro-cli\data.sqlite3`
- Linux: `~/.local/share/kiro-cli/data.sqlite3`

kiro-cli-history reads all sources and presents a unified deduplicated view (JSONL > SQLite > Archive priority).

## Archive sync

On every startup, SQLite sessions are automatically backed up:
1. New SQLite sessions → `<data_dir>/archive/<session_id>.json`
2. `.json` files older than `retention_days` → compressed to `.json.gz`, original deleted
3. Archive sessions appear in the list if not already covered by JSONL/SQLite

This preserves SQLite sessions that would otherwise disappear on kiro-cli reinstall.

## Search architecture

```
search_sessions(query, sessions)
        │
        ├─ title / cwd match          (always in-memory, fast)
        │
        ├─ rg available?
        │   ├─ JSONL cold-cache   → rg --files-with-matches -F -i *.jsonl
        │   └─ archive .json.gz   → rg -z --files-with-matches -F -i *.json.gz
        │
        ├─ SQLite / archive warm  → lazy Python (per-session)
        └─ JSONL warm cache       → _fuzzy_match on _search_text
```

ripgrep runs one subprocess call per token per directory — much faster than per-file Python I/O on cold cache. Falls back to Python when rg is not available.

## ripgrep bundled binaries

Pre-downloaded to `bin/` in the repo (rg 14.1.1):

| Platform | File |
|----------|------|
| Windows x64 | `bin/windows-x64/rg.exe` |
| macOS Apple Silicon | `bin/macos-arm64/rg` |
| macOS Intel | `bin/macos-x64/rg` |
| Linux x64 | `bin/linux-x64/rg` |
| Linux arm64 | `bin/linux-arm64/rg` |

Install scripts copy the appropriate binary to `<install_dir>/bin/rg[.exe]`. No runtime download needed.

## Read-only guarantee (mostly)

This tool **never writes to** Kiro CLI session data:
- SQLite opened with `?mode=ro` URI flag
- JSONL files read-only
- Exception: `F2` rename writes the `.json` metadata sidecar (atomic tempfile+rename)
- Exception: `Ctrl+Del` calls `kiro-cli chat --delete-session <id>` (delegated to kiro-cli)

Archive files are written by kiro-cli-history itself (not kiro-cli data).

## Performance

- **Lazy loading**: UI appears immediately; sessions load in background thread
- **Incremental preview**: first 30 messages; more on demand via offset-based reading
- **Debounced search**: `search_id` counter cancels stale results from fast typing
- **ripgrep acceleration**: parallel SIMD search on cold-cache JSONL and archive .gz
- **Prebuild cache**: `start_cache_prebuild()` builds `_search_text` for all JSONL sessions in background

## Configuration

Settings stored in `<data_dir>/kiro-cli-history.json`:

```json
{
  "trust_all_tools": true,
  "show_single_turn": false,
  "show_untitled": false,
  "theme": "textual-dark",
  "debug": false,
  "retention_days": 90
}
```

## Logging

Logs always written to `<data_dir>/kiro-cli-history.log`:

- **Always on**: ERROR level always recorded (regardless of debug mode)
- **Debug mode**: PERF + WARN levels added when debug=True
- **Rotation**: 2MB limit → compressed `.gz`
- **Retention**: 60 days
- **Precision**: millisecond timestamps
- **ERROR format**: includes `ts=<epoch_ms>` for correlation

Example:
```
2026-10-02T21:22:44.123+09:00 [ERROR] worker_crash ts=1759456964123 event=_load_sessions_async error="..." traceback="..."
2026-10-02T21:22:44.456+09:00 [PERF] app_start sessions=352 load_time=0.734 spanning_days=84
```

## How this complements Kiro CLI native tools

| | `--resume-picker` (native) | kiro-cli-history |
|---|---|---|
| Scope | Current directory only | All directories |
| Search | Browse by title | Full-text across all messages + ripgrep |
| Preview | Title + message count | Full conversation with markdown |
| Resume | By title in current dir | By session ID |
| Resume in new dir | ✗ | `Alt+N` |
| Export | ✗ | `Ctrl+X` (single), `Ctrl+P` (all) |
| Archive SQLite | ✗ | Auto-sync on startup |
