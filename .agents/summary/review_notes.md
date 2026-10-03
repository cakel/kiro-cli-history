# Review Notes

## Consistency Check

### ✅ Consistent across documents

- **Session dict schema**: `data_models.md` defines the authoritative schema; `interfaces.md` references `extract_messages()` return type; `components.md` lists state attributes — all consistent.
- **Three storage formats**: JSONL v3 / SQLite v2 / SQLite v1 / Archive consistently named across all documents.
- **Env vars**: `KIRO_DEMO_DIR` and `KIRO_HISTORY_DATA_DIR` described consistently in `codebase_info.md` and `architecture.md`.
- **Data dir paths**: Windows `C:\ProgramData\kiro-cli-history\data\` and Unix `~/.local/share/kiro-cli-history/data/` consistent between `codebase_info.md` and `data_models.md`.
- **PREVIEW_BATCH_SIZE=30**: Named consistently in `components.md` (state attributes) and `workflows.md` (preview load sequence).
- **`_search_id` debounce**: Described consistently in `components.md` (state attributes) and `workflows.md` (filtering workflow).
- **Atomic writes**: tempfile + `os.replace()` pattern described consistently in `components.md` (config) and `workflows.md` (rename).
- **ripgrep fallback behavior**: Consistently described as "falls back to Python `_fuzzy_match`" in `architecture.md`, `interfaces.md`, and `dependencies.md`.

### ⚠️ Minor inconsistencies

1. **`kiro_history.py` imports `DEFAULT_SETTINGS` as `_CONFIG_DEFAULTS`**: In `components.md`, the attribute is documented as coming from `config.py`'s `DEFAULT_SETTINGS`. The alias `_CONFIG_DEFAULTS` is not mentioned. Low impact but could confuse someone searching for `_CONFIG_DEFAULTS`.
   - **Recommendation**: Note the alias in `components.md`'s `KiroHistory.__init__` description.

2. **`_history` field in session dict**: `data_models.md` lists `_history: list | None` as an archive-specific field. However, this field is also transiently used during JSONL loading for the warm search cache. Currently documented as archive-only.
   - **Recommendation**: Clarify in `data_models.md` that `_history` is used by archive sessions; JSONL uses `_search_text` instead.

3. **`sync_sqlite_to_archive` called in `on_mount` vs as a background thread**: `workflows.md` (startup sequence) shows this running as a "background thread" but the actual call in `kiro_history.py` may be synchronous in `on_mount`. This could not be verified from the overview alone.
   - **Recommendation**: Verify the actual call site in `kiro_history.py` and update `workflows.md` if needed.

---

## Completeness Check

### ✅ Well-documented areas

- Session loading, search, and preview workflows — complete with sequence diagrams
- All public APIs in `session_store.py` and `config.py`
- Data structures for all four session sources
- Keyboard bindings — complete table
- Test tier structure and how to run each tier
- Environment variable effects
- Archive lifecycle (export, compression, retention)

### ⚠️ Gaps from overview-only analysis

The following areas could not be fully documented from the codebase overview alone, as they require reading source code:

1. **`_render_messages()` highlight implementation**: The preview search highlight mechanism (how matches are visually marked in RichLog) is described at a high level in `workflows.md` but the exact highlighting approach (RichLog styles, background colors) is not detailed. `test_highlight_rendering.py` tests `_richlog_collect_bg_colors()` suggesting color-based highlighting.
   - **Recommendation**: Read `kiro_history.py` `_render_messages()` and `_rerender_preview()` for exact implementation details; add to `components.md`.

2. **`get_system_commands()` (Command Palette)**: `kiro_history.py` defines `get_system_commands()` for the Textual `CommandPalette`. The commands exposed (theme picker, export transcripts, retention picker, toggles) are partially inferred from method names but not explicitly listed in any document.
   - **Recommendation**: Read `get_system_commands()` and document the full command list in `interfaces.md`.

3. **`perf_lazy_loading.py`**: This file in `tests/` is a standalone performance script (not a test). Its exact purpose and usage is not documented.
   - **Recommendation**: Add a brief description to `codebase_info.md` or `components.md`.

4. **`kiro-cli-history` launcher script in `bin/`**: `bin/kiro-cli-history` (no extension) is a shell wrapper for the app. Its contents and the `install.bat` → launcher chain are not documented.
   - **Recommendation**: Add to `codebase_info.md`'s directory structure notes.

5. **`_is_sqlite_subagent()` heuristic**: The function that determines whether a SQLite session is a sub-agent session. The heuristic used is not documented.
   - **Recommendation**: Add to `components.md` (session_store section) or `data_models.md`.

6. **Korean encoding support (`test_korean_encoding.py`)**: The test file exists suggesting special handling of non-ASCII filenames and content. The specific encoding handling in `session_store.py` (likely `_make_jsonl_line` or file read calls) is not documented.
   - **Recommendation**: Add a note to `components.md` (session_store section) about encoding handling.

7. **`Alt+N` "Resume in different directory" flow**: The `action_new_session_history` / `on_dir_chosen` flow is mentioned in interfaces but the exact user experience (does it open a dir picker? use `DirConfirmScreen`?) is not fully described in `workflows.md`.
   - **Recommendation**: Add a workflow diagram for Alt+N in `workflows.md`.

### ℹ️ Intentionally excluded

- Volatile metrics (line counts, file sizes) — excluded per documentation guidelines
- Generic Python/Textual best practices — not repo-specific
- Specific build commands that are standard (e.g., `pip install`, `pytest`)

---

## Language Support Limitations

The codebase is pure Python. No limitations from language support tools (LSP, type stubs) were encountered that would affect documentation quality. However:

- **No type annotations on session dicts**: The session dict and message dict are plain `dict` objects, not typed dataclasses or TypedDicts. This means type information must be inferred from usage, which was done for `data_models.md`.
- **Dynamic Textual CSS**: Layout described in `architecture.md` was derived from the inline `CSS` class attribute, which is reliable but not statically analyzable.

---

## Recommendations Summary

| Priority | Action |
|----------|--------|
| Low | Clarify `_CONFIG_DEFAULTS` alias in `components.md` |
| Low | Clarify `_history` field usage in `data_models.md` |
| Medium | Verify `sync_sqlite_to_archive` call site (sync vs async) in `workflows.md` |
| Medium | Document Command Palette commands in `interfaces.md` |
| Low | Add `_is_sqlite_subagent` heuristic to `components.md` |
| Low | Add Korean/encoding note to `components.md` |
| Low | Add Alt+N workflow diagram to `workflows.md` |
| Low | Document `perf_lazy_loading.py` purpose in `codebase_info.md` |
