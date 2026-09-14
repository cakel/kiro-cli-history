# kiro-cli-history

![kiro-cli-history demo](/meta/demo.gif)

A terminal UI for fuzzy-searching, browsing, and resuming [Kiro CLI](https://kiro.dev/docs/cli/) conversations.

## The problem

Kiro CLI has great built-in [conversation persistence](https://kiro.dev/docs/cli/chat/#conversation-persistence) — it saves your sessions and lets you resume them with `--resume` and `--resume-picker`. However, these are scoped to the directory where the session was started. If you work across many projects and directories, finding a specific past conversation means remembering which folder you were in at the time.

`kiro-cli-history` complements Kiro CLI's native persistence by adding **global fuzzy search across all sessions** — regardless of which directory they were started in. It searches the full content of every message exchanged, not just session titles.

## What it offers

- **Global search** — find conversations across all directories, not just the current one
- **Full-text fuzzy search** — searches every message you and Kiro exchanged, not just titles
- **Conversation preview** — read through the full exchange with markdown rendering before deciding to resume
- **One-key resume** — press `Ctrl+R` to jump into Kiro CLI and continue the conversation
- **Session management** — rename sessions (`F2`)
- **Lazy loading** — fast startup with background session loading; preview loads incrementally
- **Copy to clipboard** — press `Ctrl+Y` to copy an entire conversation
- **All session formats** — reads all three Kiro CLI storage versions (v1 SQLite, v2 SQLite, v3 JSONL), covering both `--classic` and new TUI modes

## Session data

This tool reads from:
- `~/.kiro/sessions/cli/` (JSONL sessions)
- `~/Library/Application Support/kiro-cli/data.sqlite3` (SQLite sessions, macOS)
- `%LOCALAPPDATA%\kiro-cli\data.sqlite3` (SQLite sessions, Windows)
- `~/.local/share/kiro-cli/data.sqlite3` (SQLite sessions, Linux)

Session titles can be modified via `F2` or command palette (writes back to source files).

## Install

### macOS / Linux

```bash
git clone https://github.com/cakel/kiro-cli-history.git
cd kiro-cli-history
bash install.sh
```

### Windows

```bat
git clone https://github.com/cakel/kiro-cli-history.git
cd kiro-cli-history
install.bat
```

`install.bat` installs to `C:\ProgramData\kiro-cli-history` (fixed path to avoid encoding issues with non-ASCII usernames) and automatically adds the `bin` directory to your **User PATH**, so `kiro-cli-history` works from any terminal after opening a new window.

### Dependencies

- Python 3.9+
- [textual](https://github.com/Textualize/textual) (installed automatically by `install.sh` / `install.bat`)

## Usage

```bash
kiro-cli-history
```

Run it from anywhere. It searches globally.

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| `/` | Focus search bar |
| `↓` / `↑` or `j` / `k` | Navigate sessions |
| `→` or `l` | Focus preview pane (for scrolling) |
| `←` or `h` | Focus back to session list |
| `m` or `Space` | Load more messages (lazy loading) |
| `F2` | Rename selected session |
| `Ctrl+R` | Resume session in Kiro CLI |
| `Ctrl+N` | Start a new Kiro CLI session |
| `Ctrl+Y` | Copy conversation to clipboard |
| `Ctrl+P` | Open command palette |
| `Ctrl+F` | Focus search bar |
| `Esc` | Clear search / Quit |
| `Ctrl+C` | Quit |

### Command palette (`Ctrl+P`)

Access additional commands:
- **Toggle --trust-all-tools** — enable/disable the flag on resume/new
- **Toggle non-interactive sessions** — show/hide background agent sessions (hidden by default)
- **Toggle untitled sessions** — show/hide sessions with no title (hidden by default)

### Searching

Type in the search bar to fuzzy-search across:
- Session titles
- Working directories
- Full conversation content (every message exchanged)

Search is case-insensitive and covers all session formats.

### Text selection

Hold **Option (Alt)** while dragging to select text from the preview pane. Or press **Ctrl+Y** to copy the full conversation to clipboard.

## How it works

Kiro CLI stores conversations in three formats depending on the version and mode:

| Format | Location | Used by |
|--------|----------|---------|
| v3 (JSONL) | `~/.kiro/sessions/cli/*.json` + `*.jsonl` | `kiro-cli --classic` |
| v2 (SQLite) | `~/Library/Application Support/kiro-cli/data.sqlite3` | New TUI mode (`kiro-cli`) |
| v1 (SQLite) | Same database, `conversations` table | Legacy |

`kiro-cli-history` reads all three and presents them in a unified view. Each session shows:
- **Title** — first message or auto-generated title
- **Directory** — where the session was started
- **Date** — last activity (e.g., "7 Apr 2026")
- **Message count** — total exchanges
- **Duration** — elapsed time

## Performance

- **Lazy loading**: UI displays immediately while sessions load in background
- **Incremental preview**: Only first 30 messages load initially; press `m` or `Space` for more
- **13x faster** initial session loading via byte-level JSONL scanning (vs full JSON parsing)

## How this complements Kiro CLI

Kiro CLI's native `--resume` and `--resume-picker` work well when you know which directory a session was started in. `kiro-cli-history` is a companion tool for when you need to find a conversation but don't remember where it happened — it gives you a global view with full-text search.

| | `--resume-picker` (native) | `kiro-cli-history` |
|---|---|---|
| Scope | Current directory | All directories |
| Search | Browse by title | Full-text across all messages |
| Preview | Title + message count | Full conversation with markdown |
| Resume | By title | By session ID (reliable) |

## Platform

macOS, Linux, and Windows (Python 3.9+).

Clipboard support: `pbcopy` (macOS), `xclip`/`xsel` (Linux), `clip` (Windows).

## Uninstall

### macOS / Linux

```bash
bash uninstall.sh
```

### Windows

```bat
uninstall.bat
```

Removes the installation directory and cleans up PATH entries.

## Credits

Inspired by [raine/claude-history](https://github.com/raine/claude-history) — an excellent fuzzy-search tool for Claude Code conversations. If you use Claude Code, check that out.

## License

MIT
