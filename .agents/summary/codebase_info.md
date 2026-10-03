# Codebase Information

## Project Identity

- **Name**: kiro-cli-history
- **Purpose**: Terminal UI for fuzzy-searching, browsing, and resuming Kiro CLI conversation sessions globally across all directories
- **Language**: Python 3.10+
- **License**: MIT
- **Repository**: https://github.com/cakel/kiro-cli-history
- **Upstream fork**: prabhugr/kiro-cli-history

## Directory Structure

```
kiro-cli-history/
├── kiro_history.py          # Main Textual app — entry point and UI controller
├── session_store.py         # Data layer — session reading, search, archive
├── widgets.py               # Reusable Textual UI components
├── config.py                # Settings read/write
├── app_log.py               # Debug logging with rotation
├── _version.py              # Single-source version string
├── pyproject.toml           # Project metadata and dependencies
├── install.sh / install.ps1 # Install scripts (Unix/Windows)
├── install.bat              # Windows batch launcher
├── uninstall.sh / uninstall.ps1 / uninstall.bat
├── bin/                     # Bundled ripgrep binaries (5 platforms)
│   ├── windows-x64/rg.exe
│   ├── macos-arm64/rg
│   ├── macos-x64/rg
│   ├── linux-x64/rg
│   └── linux-arm64/rg
├── docs/                    # Documentation
│   ├── usage.md
│   ├── how-it-works.md
│   ├── debug-logging.md
│   └── changelog.md
├── tests/                   # Test suite
│   ├── conftest.py
│   ├── helpers.py
│   ├── fixtures/            # Synthetic session fixture builders
│   │   └── integration_sessions/
│   ├── integration/         # Integration tests (require real data)
│   └── test_*.py            # Unit and headless GUI tests
├── archive/                 # Auto-generated SQLite session backups
└── meta/                    # Assets (demo GIF)
```

## Technology Stack

| Component | Technology |
|-----------|-----------|
| UI framework | [Textual](https://github.com/Textualize/textual) ≥ 0.40.0 |
| Search acceleration | [ripgrep](https://github.com/BurntSushi/ripgrep) 14.1.1 (bundled) |
| Data storage (read) | JSONL files, SQLite (read-only) |
| Data storage (write) | JSON/JSON.gz archive, JSON config |
| Test framework | pytest + pytest-asyncio |
| CI | GitHub Actions (Ubuntu, Python 3.10) |
| Python minimum | 3.10 |

## Runtime Data Locations

### Session data (read-only)
- **JSONL**: `~/.kiro/sessions/cli/` (v3, current format)
- **SQLite v2**: `conversations_v2` table in platform SQLite DB
- **SQLite v1**: `conversations` table in platform SQLite DB

### SQLite DB paths
- **Windows**: `%LOCALAPPDATA%\kiro-cli\data.sqlite3`
- **macOS**: `~/Library/Application Support/kiro-cli/data.sqlite3`
- **Linux**: `~/.local/share/kiro-cli/data.sqlite3`

### App data (read/write)
- **Windows**: `C:\ProgramData\kiro-cli-history\data\`
- **macOS/Linux**: `~/.local/share/kiro-cli-history/data/`
- Override with: `KIRO_HISTORY_DATA_DIR` env var

### Files in data dir
- `kiro-cli-history.json` — user settings
- `kiro-cli-history.log` — debug log
- `archive/` — SQLite session backups (`.json` / `.json.gz`)

## Environment Variables

| Variable | Effect |
|----------|--------|
| `KIRO_DEMO_DIR` | Redirect all data paths to a test directory (test isolation) |
| `KIRO_HISTORY_DATA_DIR` | Override the app data directory |

## Test Markers

| Marker | Description | Default |
|--------|-------------|---------|
| (none) | Unit tests, fast, no real data | Always run |
| `slow` | Full Textual app headless GUI tests (2–5s each) | Excluded by default |
| `integration` | Tests requiring real `~/.kiro` session data | Excluded by default |

Run all tests: `pytest tests/ -m "slow or integration"`
Run only slow: `pytest tests/ -m slow`
Run only unit: `pytest tests/` (default)
