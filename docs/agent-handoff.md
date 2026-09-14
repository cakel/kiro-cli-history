# Agent Handoff Document

> For AI agents continuing work on this project.
> Last updated: 2026-09-14

## Project summary

`kiro-cli-history` is a terminal UI (TUI) tool for browsing, searching, and
resuming Kiro CLI conversation sessions. It is a fork of
https://github.com/prabhugr/kiro-cli-history with significant improvements.

Tech stack: Python 3.9+, Textual (TUI framework), SQLite, JSONL.
Single-file application: `kiro_history.py` (~1350 lines).

## Current state (v0.1.0-cakel.1)

- Branch: main
- All PRs merged. No open PRs.
- 30 unit tests passing (`python -m pytest tests/ -q`)
- No known Critical/High bugs (6 rounds of code review completed)

## What was done in this session

1. PRs #5-#11 merged (see docs/changelog.md for full list)
2. Code review rounds: 6 iterations, all Critical/High fixed
3. Key fixes: atomic rename, race conditions, SQLite timestamp, macOS sed compat
4. Non-Interactive renamed to Single-turn with simpler detection logic
5. Version string in title bar (git tag + hash)
6. Windows path changed to C:\ProgramData (Korean username safety)
7. All non-ASCII chars removed from source files
8. docs/ directory created with this handoff

## Known remaining issues (Medium/Low, not release blockers)

These were identified but deferred:

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| 1 | Medium | SQLite V2 fetchall() loads entire history into memory | _load_sqlite_sessions() |
| 2 | Medium | search_sessions re-reads JSONL files on every search (no content cache) | search_sessions() |
| 3 | Medium | _load_more_messages SQLite path: offset applies to list slice, not O(1) | extract_messages() |
| 4 | Low | st_ctime on Windows = metadata change time, not creation time | _load_jsonl_sessions() second pass |
| 5 | Low | Ctrl+F label says "Focus search bar" but actually calls action_search_content | BINDINGS |
| 6 | Low | `?` help mentioned in status bar but no BINDINGS entry | status bar text |

## Architecture overview

See `docs/architecture.md` for detailed data flow and design decisions.

## How to run tests

```bash
python -m pytest tests/ -v
```

Tests are in `tests/`:
- `test_rename.py` - rename functionality (7 tests)
- `test_textual_compat.py` - Textual widget compat, bindings, app init
- `test_platform_compat.py` - SQLite URI, datetime, path handling
- `test_korean_encoding.py` - Korean text handling

## How to install locally

**Windows:**
```powershell
.\install.ps1
```
Installs to `C:\ProgramData\kiro-cli-history`.

**Linux/macOS:**
```bash
bash install.sh
```
Installs to `~/.local/share/kiro-cli-history`.

## Code conventions

- Single-file: all logic in `kiro_history.py`
- No non-ASCII characters in source files (enforced)
- Thread safety: all shared state mutations via `call_from_thread`
- Error handling: specific exception types, never bare `except:` in new code
- SQL: table names from `_SQL_TABLES` allowlist only (not f-string)
- File writes: atomic (tempfile + os.replace)

## Potential next improvements

Roughly in priority order:

1. **Content search cache**: pre-extract searchable text at load time to avoid
   re-reading JSONL files on every search keystroke

2. **Session title persistence**: when Kiro updates a title, kiro-cli-history
   picks it up on next launch but not live; a file watcher could help

3. **Pagination UI**: show "Page X of Y" in status bar instead of just message count

4. **Upstream sync**: periodically pull from prabhugr/kiro-cli-history for new
   features; main risk is conflict with our install path changes and filter logic

5. **SQLite memory**: `_history` field (full conversation) kept in memory per
   session; for large databases (1000+ sessions) this could be significant

6. **Kiro CLI version detection**: newer Kiro versions may change session format;
   add version detection and graceful degradation

## Important file paths (runtime)

| Path | Purpose |
|------|---------|
| `~/.kiro/sessions/cli/*.json` | JSONL session metadata |
| `~/.kiro/sessions/cli/*.jsonl` | JSONL session content |
| `~/Library/Application Support/kiro-cli/data.sqlite3` | SQLite (macOS) |
| `%LOCALAPPDATA%\kiro-cli\data.sqlite3` | SQLite (Windows, Kiro's own data) |
| `C:\ProgramData\kiro-cli-history\` | kiro-cli-history install (Windows) |
| `~/.local/share/kiro-cli-history/` | kiro-cli-history install (Linux) |

Note: `%LOCALAPPDATA%\kiro-cli\data.sqlite3` is where **Kiro** stores sessions
(read-only for us). `C:\ProgramData\kiro-cli-history\` is where **we** install.

## Environment variable

`KIRO_DEMO_DIR` - override all data paths to a demo directory (for recording GIFs).
Value is resolved to absolute path to prevent traversal attacks.
