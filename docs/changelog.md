# Changelog (cakel fork vs upstream)

Upstream: https://github.com/prabhugr/kiro-cli-history  
This fork: https://github.com/cakel/kiro-cli-history

## v0.1.0-cakel.1

### New features

**Session filtering**
- Single-turn sessions hidden by default (was: all sessions shown)
- Untitled sessions hidden by default
- Toggle via Ctrl+P command palette
- "Single-turn" = sessions with only one exchange (msg_count <= 1 for SQLite,
  <= 2 for JSONL due to counting semantics, or has parent_session_id for JSONL)

**Rename (F2)**
- Dialog resized: 80% width, 40% height, centered
- Enter key now saves (previously only Save button worked)
- Atomic write: tempfile + os.replace to prevent corruption on failure
- SQLite V1: uses cwd as lookup key (correct; was using session_id, silently failed)
- SQLite V2: updates value JSON (was attempting title column which may not exist)
- SQL table names from allowlist dict (injection prevention)

**Version in title bar**
- Displays: `kiro-cli-history (v0.1.0-cakel.1-<git-hash>)`
- Auto-reads tag from git describe; falls back to VERSION constant if no git

**JSONL sessions**
- Also loads .jsonl-only files (missing .json sidecar)
- 13x faster loading: byte-level `b'"kind":"Prompt"'` scan vs full JSON parse
- extract_messages() has offset parameter for efficient pagination

**Platform**
- Windows: installs to `C:\ProgramData\kiro-cli-history` (fixed ASCII path;
  upstream used %LOCALAPPDATA% which can contain Korean/CJK on Korean Windows)
- Windows: BAT launcher UTF-8 without BOM (BOM caused garbled `癤?echo off`)
- Linux/macOS: install wrapper is atomic (mktemp + mv)
- macOS: sed -i.bak for BSD sed compatibility (upstream used GNU-only -i "")
- All: uninstall stops running processes before removing files

### Bug fixes

**Race conditions**
- _load_preview: session_id guard prevents mixing content from rapid session switching
- _load_more_messages: same guard
- _do_search: results applied on main thread; search_id discards stale results
- _refresh_sessions: passes search_id when triggering _do_search

**Shared state**
- _preview_messages updated on main thread only (was modified from worker threads)
- filtered_sessions updated on main thread only

**Error handling**
- SQLite connection: catches PermissionError, OSError (DB locked by Kiro)
- SQLite connection: finally block ensures conn.close() (was missing)
- SQLite timestamp None/0: TypeError caught, duration clamped >= 0
- Session load failure: shows error notification instead of infinite "Loading..."
- execvp: FileNotFoundError caught, shows "kiro-cli not found" message

**Path handling**
- Path.with_suffix() replaces str.replace(".json", ".jsonl") to avoid
  corrupting paths that contain ".json" in directory names

**UI**
- Rich markup characters in session titles/cwd escaped (`[` -> `\[`)
- duration 0 shown as '-' instead of '0m' (SQLite V1 has no timestamps)
- _is_single_turn filter: source-aware thresholds (JSONL vs SQLite semantics differ)

### Upstream-only features removed
- "Generate titles for N untitled sessions" batch command (removed in PR #6)

### Code quality
- All non-ASCII characters removed from source files (.py, .sh, .ps1, .bat)
- 30 unit tests added (pytest) in tests/
- pyproject.toml with pytest config
