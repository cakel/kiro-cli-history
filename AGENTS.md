# AGENTS.md

Agent navigation guide for kiro-cli-history — a Python/Textual terminal UI for fuzzy-searching, browsing, and resuming Kiro CLI conversation sessions globally across all directories.

## Repo Layout

```
kiro-cli-history/
├── kiro_history.py      ← App entry point (KiroHistory class, main())
├── session_store.py     ← Data layer: session loading, search, archive
├── widgets.py           ← Textual UI components (modals, list item, inputs)
├── config.py            ← Settings read/write (JSON, atomic)
├── app_log.py           ← Debug logging with rotation
├── _version.py          ← Version string (injected by install scripts)
├── pyproject.toml       ← Dependencies: textual>=0.40.0, pytest, pytest-asyncio
├── bin/                 ← Bundled ripgrep binaries (5 platforms, no runtime download)
├── docs/                ← Usage, how-it-works, changelog docs
├── tests/               ← Unit tests (default), slow GUI tests, integration tests
│   ├── fixtures/        ← Synthetic session fixture builders
│   └── integration/     ← Tests requiring real ~/.kiro data
└── .agents/summary/     ← Full documentation knowledge base (see index.md)
```

## Subsystems

### session_store.py — Data Layer (no Textual imports)

Public API: `get_sessions()`, `search_sessions()`, `extract_messages()`, `prebuild_cache()`, `start_cache_prebuild()`, `sync_sqlite_to_archive()`

Reads three Kiro CLI session formats, priority order:
1. JSONL v3: `~/.kiro/sessions/cli/*.jsonl`
2. SQLite v2: `conversations_v2` table
3. SQLite v1: `conversations` table
4. Archive: `<data_dir>/archive/*.json[.gz]`

SQLite always opened read-only (`?mode=ro` URI). Search uses bundled ripgrep subprocess for cold-cache JSONL/archive; falls back to Python `_fuzzy_match()` on warm `_search_text` cache.

### kiro_history.py — UI Controller

`KiroHistory(App)` owns all UI state and worker dispatch. Key patterns:
- `@work` decorator for all background I/O (session load, preview, search)
- `_search_id` counter for search debounce (increment cancels stale workers)
- `PREVIEW_BATCH_SIZE = 30` — preview loads incrementally, `action_load_more()` fetches next batch
- Preview search: `_preview_search_matches` holds message indices, `_rerender_preview()` applies highlights

### widgets.py — UI Components

All modal screens (`DeleteConfirmScreen`, `DirConfirmScreen`, `RenameScreen`, `ThemePickerScreen`, `RetentionPickerScreen`, `MissingDirScreen`, `KeysHelpScreen`) live here. No dependency on `kiro_history.py` — importable independently.

### config.py — Settings

Config at `<data_dir>/kiro-cli-history.json`. Keys: `trust_all_tools`, `show_single_turn`, `show_untitled`, `theme`, `debug`, `retention_days`. All writes are atomic (tempfile + `os.replace()`). Unknown keys filtered on save.

## Key Paths (runtime)

| Resource | Windows | macOS/Linux |
|----------|---------|-------------|
| Kiro sessions (JSONL) | `~\.kiro\sessions\cli\` | `~/.kiro/sessions/cli/` |
| Kiro SQLite DB | `%LOCALAPPDATA%\kiro-cli\data.sqlite3` | platform-specific |
| App data dir | `C:\ProgramData\kiro-cli-history\data\` | `~/.local/share/kiro-cli-history/data/` |
| Config file | `<data_dir>\kiro-cli-history.json` | same |
| Archive | `<data_dir>\archive\*.json[.gz]` | same |

Override data dir with `KIRO_HISTORY_DATA_DIR` env var. Use `KIRO_DEMO_DIR` to redirect all paths for test isolation.

## Non-Obvious Patterns

**Test isolation**: Set `KIRO_DEMO_DIR` to a temp directory — all data paths (sessions, SQLite, archive) redirect to it. The `fixture_dir` pytest fixture in `tests/conftest.py` does this automatically.

**Test tiers**: Default `pytest tests/` runs only fast unit tests. `@pytest.mark.slow` covers full headless Textual app tests (2–5s each). `tests/integration/` requires real `~/.kiro` data. CI runs both unit and integration on every push.

**ripgrep**: Bundled in `bin/<platform>/rg[.exe]`. Install scripts copy it to `<install_dir>/bin/`. `_rg_path()` in `session_store.py` locates it relative to the script. No download at runtime.

**Rename writes**: Only JSONL sessions support rename (F2). Writes to the `.json` metadata sidecar, not the `.jsonl` history file.

**Archive auto-sync**: On every startup, `sync_sqlite_to_archive()` exports new SQLite sessions to archive. Files older than `retention_days` are compressed to `.json.gz`. This preserves sessions that would disappear on Kiro CLI reinstall.

**Circular import avoidance**: `_version.py` exists specifically to avoid circular imports — `config.py` and `app_log.py` both import `VERSION` from it instead of from `kiro_history.py`.

**Graceful degradation**: `config` and `app_log` imports in `kiro_history.py` are in try/except blocks. The app runs (with defaults and no logging) even if those modules are missing.

## Documentation Knowledge Base

Full detailed documentation is in `.agents/summary/`. Start with `index.md` for routing:

| Question type | File |
|--------------|------|
| Architecture diagrams, design decisions | `architecture.md` |
| Module details, method descriptions | `components.md` |
| Public API reference, key bindings | `interfaces.md` |
| Session dict, config schema, JSONL format | `data_models.md` |
| Startup, search, preview, resume flows | `workflows.md` |
| Dependencies, CI setup | `dependencies.md` |
| Directory structure, env vars, test markers | `codebase_info.md` |

## Custom Instructions

<!-- This section is for human and agent-maintained operational knowledge.
     Add repo-specific conventions, gotchas, and workflow rules here.
     This section is preserved exactly as-is when re-running codebase-summary. -->
