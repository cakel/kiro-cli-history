# Architecture

## Overview

kiro-cli-history follows a strict two-layer architecture: a pure data/search layer (`session_store.py`) and a UI layer (`kiro_history.py` + `widgets.py`). The data layer has no Textual imports and is safe to use in tests and CLI tools independently.

## High-Level Architecture

```mermaid
graph TB
    subgraph "Kiro CLI (external)"
        KC_JSONL["~/.kiro/sessions/cli/*.jsonl (v3)"]
        KC_SQLITE["kiro-cli/data.sqlite3 (v1/v2)"]
    end

    subgraph "kiro-cli-history"
        subgraph "Data Layer (session_store.py)"
            SS_GET["get_sessions()"]
            SS_SEARCH["search_sessions()"]
            SS_EXTRACT["extract_messages()"]
            SS_ARCHIVE["sync_sqlite_to_archive()"]
            SS_CACHE["prebuild_cache()"]
            RG["ripgrep subprocess"]
        end

        subgraph "UI Layer"
            APP["KiroHistory (kiro_history.py)"]
            WIDGETS["widgets.py"]
        end

        subgraph "Support Modules"
            CONFIG["config.py"]
            APPLOG["app_log.py"]
            VERSION["_version.py"]
        end

        subgraph "App Data (read/write)"
            ARCHIVE["archive/*.json[.gz]"]
            CFG_FILE["kiro-cli-history.json"]
            LOG_FILE["kiro-cli-history.log"]
        end
    end

    KC_JSONL --> SS_GET
    KC_SQLITE --> SS_GET
    ARCHIVE --> SS_GET
    SS_GET --> APP
    SS_SEARCH --> APP
    SS_EXTRACT --> APP
    SS_CACHE --> SS_SEARCH
    RG --> SS_SEARCH
    SS_ARCHIVE --> ARCHIVE
    APP --> WIDGETS
    CONFIG --> APP
    CONFIG --> CFG_FILE
    APPLOG --> LOG_FILE
    VERSION --> APP
    VERSION --> CONFIG
    VERSION --> APPLOG
```

## Layer Responsibilities

### Data Layer (`session_store.py`)
- Reads session data from all three Kiro CLI storage formats
- Performs fuzzy search with optional ripgrep acceleration
- Manages the archive (SQLite-to-JSON backup system)
- Exposes a clean public API — no Textual dependencies
- Thread-safe: cache prebuild runs in a background thread

### UI Layer (`kiro_history.py`, `widgets.py`)
- `KiroHistory` is a Textual `App` subclass orchestrating the full UI
- Delegates all data access to `session_store`
- Uses Textual workers (`@work`) for non-blocking background operations
- Inline CSS defines the two-pane layout

### Support Layer
- `config.py` — atomic JSON config read/write with schema versioning
- `app_log.py` — optional debug log with rotation/compression
- `_version.py` — single source of truth for version string, injected at install time

## UI Layout

```mermaid
graph LR
    subgraph "KiroHistory App"
        subgraph "Left Pane (#left-pane, 2fr)"
            PATH["#path-input (filter by dir)"]
            SEARCH["#search-input (fuzzy search)"]
            LIST["#session-list (ListView)"]
        end
        subgraph "Right Pane (#right-pane, 3fr)"
            PS_INFO["#preview-search-info (match count)"]
            PS_INPUT["#preview-search (PreviewSearchInput)"]
            PREVIEW["#preview (RichLog)"]
        end
        STATUS["#status-bar (dock=bottom)"]
        SHORTCUT["#shortcut-bar (dock=bottom)"]
        HEADER["EasterEggHeader (dock=top)"]
    end
```

## Session Source Priority

When the same session exists in multiple stores, the deduplication priority is:

```mermaid
graph LR
    A["v3 JSONL\n(highest priority)"] --> B["v2 SQLite"] --> C["v1 SQLite"] --> D["Archive\n(lowest priority)"]
```

## Search Architecture

```mermaid
flowchart TD
    Q["search_sessions(query, sessions)"]
    Q --> TM["Title / CWD match\n(always in-memory)"]
    Q --> RGA{"rg available?"}
    RGA -- Yes --> RG_JSONL["rg --files-with-matches\n-F -i *.jsonl"]
    RGA -- Yes --> RG_GZ["rg -z --files-with-matches\n-F -i *.json.gz"]
    RGA -- No --> PY["Python _fuzzy_match\n(warm cache _search_text)"]
    TM --> RESULTS["Merged results\n(deduplicated)"]
    RG_JSONL --> RESULTS
    RG_GZ --> RESULTS
    PY --> RESULTS
```

## Concurrency Model

```mermaid
sequenceDiagram
    participant UI as KiroHistory (main thread)
    participant W1 as Worker: _load_sessions_async
    participant W2 as Worker: _load_preview
    participant W3 as Worker: prebuild_cache

    UI->>W1: on_mount() → @work _load_sessions_async
    W1-->>UI: post_message(update_sessions)
    W1->>W3: start_cache_prebuild() (background thread)
    UI->>W2: on_session_highlighted() → @work _load_preview
    W2-->>UI: post_message(update_preview_state)
    W3-->>W1: cache ready (search_text built)
```

## Key Design Decisions

- **No circular imports**: `session_store`, `config`, `app_log`, `_version` have no cross-dependencies except `_version` being imported by all three support modules.
- **Graceful degradation**: `config` and `app_log` imports in `kiro_history.py` are wrapped in try/except; app runs without them.
- **Read-only by default**: SQLite opened with `?mode=ro` URI flag; JSONL files read-only. Writes only to app-owned data (archive, config, log).
- **Atomic writes**: Config and archive files use tempfile + `os.replace()` to prevent corruption.
- **Test isolation**: `KIRO_DEMO_DIR` env var redirects all data paths to a temp directory, making tests fully isolated without mocking.
