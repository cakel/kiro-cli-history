# How it works

## Session storage formats

Kiro CLI stores conversations in three formats depending on version and mode:

| Format | Location | Used by |
|--------|----------|---------|
| v3 (JSONL) | `~/.kiro/sessions/cli/*.json` + `*.jsonl` | `kiro-cli --classic` |
| v2 (SQLite) | platform path (see below), `conversations_v2` table | New TUI mode (`kiro-cli`) |
| v1 (SQLite) | same database, `conversations` table | Legacy |

SQLite database paths:
- macOS: `~/Library/Application Support/kiro-cli/data.sqlite3`
- Windows: `%LOCALAPPDATA%\kiro-cli\data.sqlite3`
- Linux: `~/.local/share/kiro-cli/data.sqlite3`

kiro-cli-history reads all three and presents them in a unified view.

## What each session shows

- **Title** - first user message (extracted from session content)
- **Directory** - where the session was started
- **Date** - last activity
- **Message count** - total exchanges
- **Duration** - time from first to last message ('-' if unavailable)

## Read-only guarantee

This tool **never writes to** Kiro CLI session data. SQLite is opened with
`?mode=ro` URI flag. JSONL files are read-only. Only the `.json` metadata
sidecar (session title) is written when using `F2` rename, and only via
atomic tempfile+rename to prevent corruption.

## Performance

- **13x faster** initial session loading: byte-level pattern scan instead of
  full JSON parsing for message counting
- **Lazy loading**: UI appears immediately; sessions load in background
- **Incremental preview**: first 30 messages loaded; more on demand with
  offset-based file reading (no re-scan on each page)
- **Debounced search**: search_id prevents stale results from fast typing

## How this complements Kiro CLI native tools

| | `--resume-picker` (native) | kiro-cli-history |
|---|---|---|
| Scope | Current directory only | All directories |
| Search | Browse by title | Full-text across all messages |
| Preview | Title + message count | Full conversation with markdown |
| Resume | By title | By session ID (reliable) |

Kiro CLI's native `--resume-picker` is the right tool when you know which
directory a session was started in. kiro-cli-history is for when you need to
find a conversation across all projects.
