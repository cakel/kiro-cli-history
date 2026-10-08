# Workflows

## App Startup

```mermaid
sequenceDiagram
    participant User
    participant App as KiroHistory.on_mount()
    participant SS as session_store
    participant Arch as archive/
    participant Cache as prebuild_cache

    User->>App: Launch kiro-cli-history
    App->>App: load_config() → apply settings/theme
    App->>App: init_logging(debug)
    App->>SS: sync_sqlite_to_archive() [background thread]
    SS->>Arch: Export new SQLite sessions as .json
    SS->>Arch: Compress old .json → .json.gz
    App->>SS: get_sessions() [background worker]
    SS-->>App: all_sessions list
    App->>App: _populate_list() → render SessionItems
    App->>Cache: start_cache_prebuild(sessions) [daemon thread]
    Cache-->>App: _search_text built (silent)
    App->>App: Update status bar "N sessions loaded"
```

---

## Session List Filtering

Applies when the user types in the path filter or search box.

```mermaid
flowchart TD
    INPUT["User types in path or search input"]
    FILTER["_get_filtered_base()\n• Apply path prefix filter\n• Hide single-turn (if setting)\n• Hide untitled (if setting)"]
    Q{"Query empty?"}
    ALL["Return filtered_sessions as-is"]
    SEARCH["search_sessions(query, filtered)\n(debounced via _search_id)"]
    POPULATE["_populate_list(results)\nRender SessionItem rows"]

    INPUT --> FILTER --> Q
    Q -- Yes --> ALL --> POPULATE
    Q -- No --> SEARCH --> POPULATE
```

---

## Preview Load (Lazy)

Triggered when the user highlights a session in the list.

```mermaid
sequenceDiagram
    participant List as session-list
    participant App as KiroHistory
    participant Worker as Worker: _load_preview
    participant SS as session_store
    participant RichLog as #preview (RichLog)

    List->>App: on_session_highlighted(session)
    App->>App: Clear RichLog, reset preview state
    App->>Worker: @work _load_preview(session)
    Worker->>SS: extract_messages(session, limit=30, offset=0)
    SS-->>Worker: first 30 messages
    Worker-->>App: post_message(update_preview_state)
    App->>RichLog: _render_messages() → RichLog.write()
    App->>App: Show "Load more (Ctrl+M)" if incomplete
```

---

## Load More Messages

Triggered by `Ctrl+M` when preview is not fully loaded.

```mermaid
sequenceDiagram
    participant App as KiroHistory
    participant Worker as Worker: _load_more_messages
    participant SS as session_store
    participant RichLog as #preview

    App->>Worker: action_load_more() → @work _load_more_messages
    Worker->>SS: extract_messages(session, limit=30, offset=current_count)
    SS-->>Worker: next batch
    Worker-->>App: post_message(update_preview_state, append=True)
    App->>RichLog: Append new messages to RichLog
```

---

## In-Preview Search

Triggered by `Ctrl+F`.

```mermaid
sequenceDiagram
    participant User
    participant App as KiroHistory
    participant Worker as Worker: _execute_preview_search
    participant RichLog as #preview

    User->>App: Ctrl+F
    App->>App: action_open_preview_search() → show #preview-search
    User->>App: Type query → on_preview_search_changed()
    App->>App: Load all messages if not fully loaded
    App->>Worker: _execute_preview_search(query)
    Worker->>Worker: _normalize_for_search() → strip markdown
    Worker->>Worker: Scan _preview_messages for matches → build index list
    Worker-->>App: _preview_search_matches, count
    App->>RichLog: _rerender_preview() with highlights applied
    App->>App: Show match count in #preview-search-info
    User->>App: Enter / Shift+Tab
    App->>RichLog: _scroll_to_match(next/prev index)
```

---

## Session Resume

```mermaid
flowchart TD
    A["User presses Ctrl+R"]
    B{"session.cwd exists?"}
    C["action_resume()\nos.chdir(cwd)\nkiro-cli chat --resume-id &lt;id&gt; [--trust-all-tools]"]
    D["handle_missing_dir()\nOpen MissingDirScreen modal"]
    E{"User picks alt dir\nor cancel"}
    F["Resume with chosen dir as cwd"]
    G["Cancel — do nothing"]

    A --> B
    B -- Yes --> C
    B -- No --> D
    D --> E
    E -- dir chosen --> F
    E -- cancel --> G
```

---

## Session Rename (F2)

```mermaid
sequenceDiagram
    participant User
    participant App as KiroHistory
    participant RenameScreen
    participant SS as session_store (JSONL)

    User->>App: Press F2
    App->>RenameScreen: push_screen(RenameScreen, current_title)
    User->>RenameScreen: Enter new name → Submit
    RenameScreen-->>App: handle_rename(new_name)
    App->>SS: Write new title to .json metadata sidecar\n(atomic tempfile + os.replace)
    App->>App: Refresh session list
```

Only JSONL sessions support rename (SQLite sessions are read-only).

---

## Archive Sync (on startup)

```mermaid
flowchart TD
    A["sync_sqlite_to_archive(sqlite_sessions, retention_days)"]
    B["Collect existing archive IDs"]
    C{"session_id in archive?"}
    D["Skip"]
    E["Load full history from SQLite"]
    F["Write <session_id>.json to archive/"]
    G["Scan all .json files in archive/"]
    H{"mtime > retention_days?"}
    I["Compress to .json.gz, delete .json"]
    J["Leave as-is"]

    A --> B --> C
    C -- Yes --> D
    C -- No --> E --> F --> G
    G --> H
    H -- Yes --> I
    H -- No --> J
```

---

## Export Session (`Ctrl+X`)

Exports the selected session as a markdown file.

```mermaid
sequenceDiagram
    participant User
    participant App as KiroHistory
    participant Worker as Worker: _export_single_session_worker
    participant SS as session_store
    participant FS as Filesystem

    User->>App: Ctrl+X
    App->>Worker: @work _export_single_session_worker(session)
    Worker->>SS: extract_messages(session) [all messages]
    Worker->>FS: Write <session_id>.md to export dir
    Worker-->>App: notify("Exported to ...")
```

---

## ESC Behavior (triple-ESC to quit)

```mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> Count1 : ESC pressed (search cleared)
    Count1 --> Idle : input changed (counter reset)
    Count1 --> Count2 : ESC pressed again → notify "Press ESC once more to quit"
    Count2 --> Idle : input changed (counter reset)
    Count2 --> Quit : ESC pressed third time
    Quit --> [*]
```

The counter auto-resets after a timer expires (to prevent accidental quit from slow presses).
