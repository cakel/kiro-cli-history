# Changelog (cakel fork vs upstream)

Upstream: https://github.com/prabhugr/kiro-cli-history  
This fork: https://github.com/cakel/kiro-cli-history

## v0.1.0-cakel.5

### Auto-save settings
- Toggle 시 `kiro-cli-history.json`에 즉시 저장 (별도 저장 단계 불필요)
- `Reset to Default Settings` 메뉴: 기본값 적용 + UI 갱신 + 저장
- 앱 시작 로그에 현재 설정 상태 포함

### Command Palette UX improvements
- Notify에 title + 4-5초 timeout 추가 (가시성 향상)
- Status bar에 로딩 상태 표시 ("Loading sessions...") + 로드 완료 notify
- **Session list 포커스 상태에서 Enter 즉시 동작** (ListView 키 가로채기 수정)

### Test infrastructure
- `slow` 마커로 GUI 테스트 분리
  - `pytest tests/` = 63 tests (~1s)
  - `pytest tests/ -m slow` = 27 GUI tests (~50s)

### Code Hardening
- Thread safety: `call_from_thread` 래핑, session_id 가드
- Import 최적화: CommandPalette 상단 이동 (매 키 입력 오버헤드 제거)
- 상수 추출: PREVIEW_BATCH_SIZE
- Error logging: rename 실패 시 log_error (JSONL/SQLite)
- 방어적 접근: `.get()` 패턴
- 미사용 코드 제거: Center import, highlight_query param

### Known Issues
- Command Palette 첫 열기 시 0.25초 지연 (Textual 내부 batch 처리) — README에 문서화

---

## v0.1.0-cakel.4

### Module restructuring
- `_version.py`: VERSION 상수 단일 소스 (순환 import 해결)
- `widgets.py`: UI 위젯 분리 (PreviewSearchInput, RenameScreen, SessionItem)
- `config.py`: 설정 영속화 (`kiro-cli-history.json`)
- `app_log.py`: 스레드 안전 로깅 + 로테이션 (2MB gz, 60일 보관)

### Installer updates
- install.sh / install.ps1: 새 모듈들 복사 추가

---

## v0.1.0-cakel.3

### Config & Logging system (#14)
- `config.py`: get_data_dir(), load_config(), save_config()
- `app_log.py`: init_logging(), log_perf(), log_warn(), log_error()
- Schema versioning (SCHEMA_VERSION = 1)
- Atomic write (tempfile + os.replace)
- Log rotation: 2MB limit, gzip compression, 60일 보관

### Settings persistence
- trust_all_tools, show_single_turn, show_untitled 설정 저장/로드
- Command palette에서 토글 시 자동 저장

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
