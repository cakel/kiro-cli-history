# Dependencies

## Runtime Dependencies

### textual ≥ 0.40.0

[Textualize/textual](https://github.com/Textualize/textual) — Python TUI framework.

**Used for**:
- `App` base class (`KiroHistory` subclasses it)
- `@work` decorator for non-blocking background workers
- `RichLog` widget for markdown-rendered preview pane
- `ListView` / `ListItem` for session list
- `Input` for search and path filter
- `ModalScreen` for all dialog screens
- `Binding` for keyboard shortcut declarations
- CSS-in-Python for layout (inline `CSS` class attribute)
- Built-in `CommandPalette` (Ctrl+P)

**Install**: `pip install textual` (auto-installed by install scripts)

**Version constraint**: `>=0.40.0` — required for `@work` decorator and `asyncio_mode="auto"` compatibility.

---

## Bundled Dependencies

### ripgrep 14.1.1

[BurntSushi/ripgrep](https://github.com/BurntSushi/ripgrep) — fast regex search tool.

**Used for**: Cold-cache search across JSONL files and compressed archive `.json.gz` files. Runs as a subprocess via `_rg_find_in_dir()`.

**Bundled at**: `bin/<platform>/rg[.exe]`

| Platform | Path |
|----------|------|
| Windows x64 | `bin/windows-x64/rg.exe` |
| macOS Apple Silicon | `bin/macos-arm64/rg` |
| macOS Intel | `bin/macos-x64/rg` |
| Linux x64 | `bin/linux-x64/rg` |
| Linux arm64 | `bin/linux-arm64/rg` |

Install scripts copy the appropriate binary to `<install_dir>/bin/rg[.exe]` and make it executable.

**Fallback**: When ripgrep is unavailable or not found, `session_store.py` falls back to Python-based `_fuzzy_match()` on the warm `_search_text` cache. All features remain functional without it.

---

## Development Dependencies

Declared in `pyproject.toml` under `[project.optional-dependencies] dev`:

### pytest ≥ 7.0

Standard Python test runner.

### pytest-asyncio ≥ 0.21

Adds `asyncio_mode = "auto"` support — required for testing Textual app methods and workers that use `async/await`.

### pytest-timeout

Prevents test hangs. Used in CI (`--timeout` flag).

**Not in pyproject.toml** but used in CI: installed directly via `pip install pytest-timeout` in the test workflow.

---

## Python Standard Library Usage

Key stdlib modules used throughout the project:

| Module | Used in | Purpose |
|--------|---------|---------|
| `sqlite3` | `session_store.py` | Read Kiro CLI v1/v2 session database |
| `json` | everywhere | Parse/write JSON data |
| `gzip` | `session_store.py`, `app_log.py` | Read/write compressed archive files and log rotation |
| `subprocess` | `kiro_history.py`, `session_store.py` | Launch ripgrep and `kiro chat --resume` |
| `threading` | `session_store.py`, `app_log.py` | Background cache prebuild, log write lock |
| `pathlib.Path` | everywhere | Cross-platform path handling |
| `os` | everywhere | Env vars, path operations, atomic file replace |
| `tempfile` | `config.py` | Atomic config write via temp file |
| `datetime` | `session_store.py`, `app_log.py` | Timestamp parsing, retention cutoff |
| `sys` | `session_store.py`, `config.py` | Platform detection (`sys.platform`) |

---

## External Process Dependencies

### kiro CLI

The application depends on the `kiro` command being available on `PATH` for:
- `kiro chat --resume <session_id>` — resume a session
- `kiro chat --delete-session <session_id>` — delete a session

kiro-cli-history does **not** install or manage the Kiro CLI binary.

---

## CI Environment

From `.github/workflows/test.yml`:

- **Runner**: `ubuntu-latest`
- **Python**: `3.10` (exact version pinned)
- **Installed**: `textual`, `pytest`, `pytest-asyncio`, `pytest-timeout`
- **Test command**: `python -m pytest tests/ --ignore=tests/integration -q`
- **Integration tests**: run separately in the same job

---

## No External Network Calls at Runtime

All dependencies are either:
- Installed via pip at setup time
- Bundled in `bin/` (ripgrep)
- Part of Python stdlib

The app makes no outbound network requests during normal operation.
