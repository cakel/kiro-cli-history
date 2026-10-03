# Debug Logging

## Why it exists

kiro-cli-history loads sessions from disk, searches across them, and renders
previews lazily — all in the background. In practice, performance varies a lot
depending on how many sessions you have, which storage format they use
(JSONL vs SQLite), and whether the search cache is warm or cold.

Debug logging was added to make these dynamics observable. The log records
**what happened, how long it took, and what the data looked like** at the time.
Over time, collected logs can reveal where the real bottlenecks are, which
storage formats are slowest, and whether tuning batch sizes or cache behaviour
would make a meaningful difference.

No session content (titles, messages, paths) is written to the log.
Only structural metadata is recorded.

---

## How to enable

Open the Command Palette (`Ctrl+P`) → **Toggle Debug Logging (currently OFF)** → Enter.

The setting is saved to your config file and takes effect on the **next app start**.
Log files are written to:

- **Windows**: `C:\ProgramData\kiro-cli-history\data\kiro-cli-history.log`
- **macOS / Linux**: `~/.local/share/kiro-cli-history/data/kiro-cli-history.log`

Log files are rotated automatically (up to 10 compressed backups kept) and old
files are cleaned up on startup (files older than 60 days are deleted).

To disable, open the Command Palette again and toggle it back off.

---

## What gets logged

Each line has the format:

```
<ISO timestamp> [PERF|WARN|ERROR] <event>  key=value  key=value ...
```

### App lifecycle

| Event | Key fields | Notes |
|-------|-----------|-------|
| `app_start` | `version`, `sessions`, `load_time`, `total_time` | Recorded once after sessions finish loading |

### Session list search

| Event | Key fields | Notes |
|-------|-----------|-------|
| `search` | `query_len`, `elapsed_ms`, `cache`, `total`, `results`, `src_jsonl`, `src_sqlite_v1`, `src_sqlite_v2` | `cache=cold` means no pre-built index; `src_*` shows session count per storage format |

### Preview

| Event | Key fields | Notes |
|-------|-----------|-------|
| `session_selected` | `session_id`, `title` (truncated to 40 chars) | Fired when a session is highlighted in the list |
| `preview_load` | `source`, `msg_count_meta`, `batch_size`, `loaded`, `all_loaded`, `elapsed_ms` | Time to read the first message batch from disk |
| `load_more` | `source`, `offset`, `loaded`, `all_loaded`, `elapsed_ms` | Each subsequent batch load |
| `preview_search_open` | — | Ctrl+F pressed |
| `preview_search` | `query_len`, `matches`, `total_messages`, `all_loaded`, `elapsed_ms` | In-preview full-text search |

### Session actions

| Event | Key fields | Notes |
|-------|-----------|-------|
| `esc_key` | `action` | Values: `clear_inputs`, `close_preview_search`, `close_keys_help`, `idle_1st`, `idle_2nd_notify`, `quit` |
| `resume` | `session_id` | Kiro CLI resume launched |
| `new_session` | `cwd` | New session started |
| `resume_new_dir` | `session_id`, `new_cwd` | Resume in a different directory |
| `rename_jsonl_failed` / `rename_sqlite_failed` | `session_id`, `error` | Rename errors |
| `delete_session_confirm` | `session_id`, `title` | Confirmation screen opened |
| `delete_session` | `session_id`, `source` | Deletion completed |
| `export_session` | `session_id`, `path`, `size_kb` | Single session exported |
| `export_transcripts` | `sessions`, `path`, `size_mb` | Bulk export |
| `copy_conversation` | `session_id`, `messages` | Clipboard copy succeeded |
| `copy_conversation_failed` | `reason` | Clipboard tool not found |
| `keys_help` | `action` (`open` / `close`) | Help panel toggled |

### Warnings and errors

| Event | Level | Meaning |
|-------|-------|---------|
| `resume_no_id` | WARN | Selected session has no ID |
| `resume_dir_not_found` | WARN | Session's original directory no longer exists |
| `worker_crash` | ERROR | Background loading thread crashed unexpectedly |
| `load_sessions_failed` | ERROR | Sessions could not be loaded |
| `config_save_failed` | ERROR | Settings could not be written to disk |
| `export_session_failed` | ERROR | Session export failed |

---

## How logs are used for improvement

**Storage format comparison** — `preview_load.elapsed_ms` broken down by
`source` (jsonl / sqlite_v1 / sqlite_v2) shows which formats are slower to
read. If JSONL is consistently slower for large sessions, the batch size or
read strategy can be tuned.

**Cache effectiveness** — Comparing `search.elapsed_ms` where `cache=cold` vs
`cache=warm` quantifies how much the pre-built search index helps, and whether
the background prebuild is completing before the first search.

**Batch size tuning** — The frequency of `load_more` events relative to the
initial `preview_load.loaded` count indicates whether the default batch size
(currently 50) causes too many round-trips for typical sessions.

**Bottleneck identification** — `total_time` in `app_start` vs `load_time`
separates I/O cost from UI startup cost. Large gaps suggest the UI is blocking
on something other than disk reads.

**Error patterns** — Repeated `resume_dir_not_found` warns indicate that many
sessions are from directories that no longer exist, which could motivate a
"stale session" cleanup feature.
