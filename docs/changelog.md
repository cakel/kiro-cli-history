# Changelog (cakel fork vs upstream)

Upstream: https://github.com/prabhugr/kiro-cli-history  
This fork: https://github.com/cakel/kiro-cli-history

## v0.1.0-cakel.10 (2026-10-08)

### UX changes

**Keybinding label rename**
- `Ctrl+R` label: "Resume" → "Resume+ChangeDir" — makes clear it resumes in the session's original directory
- `Alt+N` label: "Resume+Dir" → "Resume+SelectDir" — makes clear you pick the directory

**Alt+N default directory**
- `DirConfirmScreen` now pre-fills with the **current working directory** (where `kiro-cli-history` is running), not the session's original `cwd`

**Date format**
- Session list timestamps changed from `7 Oct 2026` → `2026-10-06 20:10:00` (local time, `yyyy-mm-dd hh:mm:ss`)

**`⌥ N` display**
- Added space between `⌥` and `N` in the shortcut bar

### Bug fixes

| Bug | Fix |
|-----|-----|
| Search highlight invisible when ANSI theme active | `theme.accent` ANSI color names (e.g. `ansi_magenta`) are not valid in Rich style strings — fall back to `#ffa62b` for any non-hex accent |

### Refactor

**Keybinding label single source of truth**
- `_L_RESUME`, `_L_NEW`, `_L_RESUME_DIR` class constants in `KiroHistory`
- `_HELP_ROWS` list defined in `kiro_history.py` and passed to `KeysHelpScreen`
- `KeysHelpScreen.__init__` accepts optional `rows` parameter (falls back to class `SHORTCUT_ROWS`)
- `_shortcut_bar_text` changed from `@staticmethod` to `@classmethod` to reference constants via `cls`
- Previously: three independent hardcoded strings (BINDINGS, shortcut bar, SHORTCUT_ROWS) required manual sync on every label change

---

## v0.1.0-cakel.9 (2026-10-03)

### New features

**ESC 3-press exit**
- 1st Esc: idle (clears search/path inputs)
- 2nd Esc: notification warning
- 3rd Esc: quit

**Debug logging enhancements**
- Added `elapsed_ms`, source distribution to perf logs
- `_initialized` flag fixes lazy-ERROR race condition

### Bug fixes

| Bug | Fix |
|-----|-----|
| `_reset_to_saved_defaults` missing `retention_days` | Added field |
| `_load_all_then_scroll_end` thread-safety | Wrapped in `call_from_thread` |
| `Path('')` bug in `KIRO_HISTORY_DATA_DIR` handling | Empty string guard |

### Installer
- Auto-installs `uv` via pip if missing; removed venv fallback

### Tests
- `test_config.py`, `test_applog_extended.py`, `test_esc_behavior.py` added

---

## v0.1.0-cakel.8 (2026-10-02)

### Bug fixes (adversarial review of cakel.7)

| Bug | Fix |
|-----|-----|
| `retention_days=0` caused immediate compression of all files | Added guard for `days == 0` (unlimited) |
| `_rg_find_in_dir` error path returned `None` instead of empty set | Returns `set()` on error |
| `KeysHelpScreen` docstring said "Left-side" | Corrected to "Right-side" |
| `DirConfirmScreen` title markup not escaped | Fixed markup escape |
| Export filename contained spaces | Replaced spaces with underscores |
| `_write_log` lazy-open race condition | Double-checked locking |
| `_calc_span_days` timezone-aware vs naive comparison | UTC conversion before strip |
| `_do_delete_session` subprocess returncode unchecked | Added returncode check |
| `_export_transcripts` duplicate filename collision | Added dedup handling |

### Cleanup
- Removed dead `NewSessionScreen` class (~130 lines)
- Removed dead `_ko_to_qwerty` code (~50 lines)

---

## v0.1.0-cakel.7 (2026-10-02)

### New features

**Dual search inputs**
- Text search (`#search-input`) and path filter (`#path-input`) now separate
- `kiro-cli-history .` pre-fills path filter with current directory absolute path
- Path filter: case-insensitive substring match on session `cwd`

**Keyboard shortcuts panel (`?`)**
- `?` toggles a right-side help panel listing all shortcuts
- `KeysHelpScreen` ModalScreen, dismiss with `?` or `Esc`

**Korean IME navigation**
- 두벌식 key positions recognized when session list has focus
- `ㅔ`→p, `ㅓ`→j, `ㅏ`→k, `ㅡ`→m, `ㅗ`→h, `ㅣ`→l

**Preview scroll keys**
- `m`: preview page down (replaces old load_more binding)
- `M`: preview page up
- Both work regardless of which pane has focus

**New session workflows**
- `Ctrl+N`: immediately starts new `kiro-cli chat` in current directory (no dialog)
- `Alt+N`: resume selected session in a different directory (`DirConfirmScreen`)
  - Pre-filled with selected session's original cwd
  - Directory auto-created if missing

**Export & Delete**
- `Ctrl+X`: export selected session → `kiro-YYYYMMDD_HHMMSS-<title>.json.gz`
- `Ctrl+Del`: delete session with `DeleteConfirmScreen` (Cancel default focus)
  - JSONL: file deletion; SQLite: `kiro-cli --delete-session`; Archive: file deletion

**SQLite archive sync**
- On startup, new SQLite sessions copied to `<data_dir>/archive/<id>.json`
- Files older than `retention_days` → `.json.gz` (gzip, compresslevel=6)
- Archive sessions included in search (lazy history load)
- ripgrep searches `.json.gz` with `-z` flag

**ripgrep integration (optional, bundled)**
- 5 platform binaries in `bin/` (rg 14.1.1): Windows x64, macOS arm64/x64, Linux x64/arm64
- `install.ps1` / `install.sh` copy from `bin/` (no runtime download)
- Bundled binary takes priority over system `rg`
- Cold-cache JSONL search and `.json.gz` archive search accelerated
- Falls back to Python if rg not available

**Command palette additions**
- `Set Retention Days…`: 90 / 180 / 365 / ∞
- `Export All Transcripts…`: all sessions → `.tar.gz` in current directory
- Built-in Textual `Keys` command filtered out (conflicts with `?`)

**Custom shortcut bar**
- Replaced Textual `Footer()` with custom `#shortcut-bar` Static
- Yellow key highlights; shows all primary shortcuts on one line

### Bug fixes

| Bug | Fix |
|-----|-----|
| `TypeError: can't compare offset-naive and offset-aware datetimes` in `_calc_span_days` | Normalize all datetimes to naive UTC via `.replace(tzinfo=None)` |
| crash logs not written (debug=False) | `init_logging` always opens log file; ERROR level always written |
| exceptions after `get_sessions()` not caught | Split into `_load_sessions_body()`, wrapped in try/except with `log_error` |
| resume crash when directory missing | `os.makedirs(cwd, exist_ok=True)` before `os.chdir` |
| `#path-input` hidden behind `#search-input` | Removed `dock: top` from both inputs |
| timestamp precision in logs | Changed `timespec="seconds"` → `timespec="milliseconds"` |
| ERROR logs missing epoch timestamp | Auto-inject `ts=<epoch_ms>` for ERROR entries |

### Breaking / behavior changes

- `Esc`: no longer quits — clears both search inputs simultaneously
- `Ctrl+Q`: new quit shortcut (Ctrl+C still works as fallback)
- `m` key: changed from `load_more` to preview page-down (load_more still via `Space`)
- `Ctrl+N`: no longer shows dialog, immediately starts new session

### .gitignore additions

```
kiro-*.json.gz
kiro-sessions-*.tar.gz
*.log
```

---

## v0.1.0-cakel.6

### Theme setting
- Theme saved to `kiro-cli-history.json` (default: `textual-dark`)
- `ThemePickerScreen` modal for selecting themes via Command Palette ("Set Theme…")
- Textual's built-in "Theme" command filtered out to avoid duplicate

### Fixed data directory
- Development and installed environments now use the same path:
  - Windows: `C:\ProgramData\kiro-cli-history\data`
  - Unix: `~/.local/share/kiro-cli-history/data`
- Override with `KIRO_HISTORY_DATA_DIR` environment variable

### Debug logging toggle
- Default: OFF (no log file created)
- Toggle via Settings menu ("Toggle Debug Logging")
- Takes effect on next app start
- Ready popup shows debug status: `"150 sessions loaded (Debug: ON)"`
- Log file: `kiro-cli-history.log` in data directory
- Retention: 2MB gz rotation, 60-day cleanup

### UI/UX improvements
- Session list: PageUp/Down/Home/End now moves selection index (not just scroll)
- Modal screen key handling: main app no longer intercepts keys when modal is active
- Easter egg: `EasterEggHeader` shows GitHub link when header is expanded (click to toggle)

### Code quality
- Exception handling: `except Exception` → `except NoMatches` (specific)
- e2e tests: 4 new theme picker tests added

---

## v0.1.0-cakel.5

### Auto-save settings
- Settings saved to `kiro-cli-history.json` immediately on toggle (no separate save step)
- `Reset to Default Settings` menu: applies defaults + refreshes UI + persists
- App start log now includes current settings state

### Command Palette UX improvements
- Notify messages now have title + 4-5s timeout (better visibility)
- Status bar shows loading state ("Loading sessions...") + notify on load complete
- **Enter works immediately when session list is focused** (fixed ListView key interception)

### Test infrastructure
- `slow` marker separates GUI tests
  - `pytest tests/` = 63 tests (~1s)
  - `pytest tests/ -m slow` = 27 GUI tests (~50s)

### Code Hardening
- Thread safety: `call_from_thread` wrapping, session_id guards
- Import optimization: CommandPalette moved to top-level (removes per-keystroke overhead)
- Constant extraction: PREVIEW_BATCH_SIZE
- Error logging: log_error on rename failure (JSONL/SQLite)
- Defensive access: `.get()` pattern throughout
- Dead code removal: Center import, highlight_query param

### Known Issues
- Command Palette has 0.25s delay on first open (Textual internal batching) — documented in README

---

## v0.1.0-cakel.4

### Module restructuring
- `_version.py`: VERSION constant single source of truth (fixes circular import)
- `widgets.py`: UI widgets extracted (PreviewSearchInput, RenameScreen, SessionItem)
- `config.py`: Settings persistence (`kiro-cli-history.json`)
- `app_log.py`: Thread-safe logging with rotation (2MB gz, 60-day retention)

### Installer updates
- install.sh / install.ps1: new modules now copied

---

## v0.1.0-cakel.3

### Config & Logging system (#14)
- `config.py`: get_data_dir(), load_config(), save_config()
- `app_log.py`: init_logging(), log_perf(), log_warn(), log_error()
- Schema versioning (SCHEMA_VERSION = 1)
- Atomic write (tempfile + os.replace)
- Log rotation: 2MB limit, gzip compression, 60-day retention

### Settings persistence
- trust_all_tools, show_single_turn, show_untitled saved/loaded
- Auto-save on toggle via command palette

---

## v0.1.0-cakel.2

### New features

**Preview in-pane search (Ctrl+F)**
- Press Ctrl+F while preview has focus → search bar appears above preview
- Pre-fills with current session-list query automatically
- Matching text highlighted with `bold reverse yellow` inline
- Info bar shows `N/M matches | Enter: next  Shift+Enter: prev  Esc: close`
- `n`/`N` keys jump next/prev match from preview pane
- Esc closes search bar, restores preview focus
- Search resets on session change

**Backend / data layer separation**
- `session_store.py` extracted as pure data layer (no Textual imports)
- `kiro_history.py` imports from `session_store`; duplicate code removed (−211 lines)
- `start_cache_prebuild()`: background daemon thread pre-builds JSONL search cache
  immediately after session load, so first search is instant rather than 4–6s
- Per-session `threading.Lock` (double-checked locking) prevents concurrent
  prebuild + on-demand search from double-reading the same JSONL file

**Search performance**
- Cold search (first query): 4–6 s → instant (cache pre-built in background)
- Warm search: < 0.1 s (unchanged)
- SQLite session history now cached in `session["_history"]` after first search;
  subsequent searches skip DB round-trip

### Test infrastructure overhaul

- `tests/fixtures/` — 9 tiny in-memory sessions (JSONL + SQLite), total < 5 KB
- `tests/conftest.py` — `fixture_env` patches `session_store` globals to fixture dir
  (NOT autouse — integration tests are unaffected)
- `tests/integration/conftest.py` — restores real `~/.kiro` paths for integration tests
- Unit tests: **90 tests in ~35 s** (was 58 tests in 256 s — 7× faster)
- E2E tests: 11 preview search tests covering state management, navigation, markdown handling
- Integration tests: `pytest tests/integration/` for real-session verification
- `pyproject.toml`: `norecursedirs = integration` excludes integration from default run

### Bug fixes / cleanups

- **Session switch state leak**: `on_session_highlighted` now resets `_preview_messages`
  and `_preview_all_loaded` — previously stale messages from previous session remained,
  causing search to find matches in wrong session's data
- **Search state not cleared**: all search state variables (`_preview_search_active`,
  `_preview_search_query`, `_preview_search_executed`, `_preview_search_matches`,
  `_preview_search_current`) now cleared on session switch, even when search bar is closed
- **Race condition in preview render**: `_render_messages` and `update_preview_state`
  now block when search is active, preventing raw message append from overwriting
  highlighted re-render
- **Scroll position wrong**: `_scroll_to_match` now uses pre-computed line offsets
  from RichLog rendering instead of counting `\n` characters (word-wrap was causing 3x error)
- **Markdown-insensitive search**: search now ignores backticks, bold (`**`, `__`),
  and italic (`*`, `_`) markers so users can find text without markdown syntax

- `install.ps1` / `install.sh`: `session_store.py` now copied alongside `kiro_history.py`
  (was missing — `kiro-cli-history` crashed with `ModuleNotFoundError` after install)
- `tests/test_korean_encoding.py`, `tests/test_platform_compat.py`: imports updated
  to import from `session_store` (functions moved there)
- Internal project term redacted from all source files

---

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

### Upstream-only features removed
- "Generate titles for N untitled sessions" batch command (removed in PR #6)

### Code quality
- All non-ASCII characters removed from source files (.py, .sh, .ps1, .bat)
- 30 unit tests added (pytest) in tests/
- pyproject.toml with pytest config
