# Usage

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `/` | Focus search bar (session search) |
| `Down` / `Up` or `j` / `k` | Navigate sessions |
| `Right` or `l` | Focus preview pane (for scrolling) |
| `Left` or `h` | Focus back to session list |
| `m` or `Space` | Load more messages (lazy loading) |
| `F2` | Rename selected session |
| `Ctrl+R` | Resume session in Kiro CLI |
| `Ctrl+N` | Start a new Kiro CLI session |
| `Ctrl+Y` | Copy conversation to clipboard |
| `Ctrl+P` | Open command palette |
| `Ctrl+F` | Search within preview (in-preview search) |
| `Esc` | Clear search / Close preview search / Quit |
| `Ctrl+C` | Quit |

## In-preview search (`Ctrl+F`)

Search within the currently selected conversation:

| Key | Action |
|-----|--------|
| `Ctrl+F` | Open search bar in preview pane |
| `Enter` | Jump to next match |
| `Shift+Enter` | Jump to previous match |
| `Esc` | Close search bar |

- Matching messages are highlighted with a distinct background color
- Search ignores markdown formatting (backticks, bold `**`, italic `*`)
- All messages are loaded before searching to ensure complete results

## Command palette (`Ctrl+P`)

| Command | Description |
|---------|-------------|
| Toggle --trust-all-tools | Enable/disable the flag on resume/new |
| Toggle single-turn sessions | Show/hide sessions with only one exchange (hidden by default) |
| Toggle untitled sessions | Show/hide sessions with no title (hidden by default) |
| Reset to Default Settings | Apply default settings immediately and persist |

Settings are auto-saved on every toggle — no separate save step needed.

## Searching

Type in the search bar to fuzzy-search across:
- Session titles
- Working directories
- Full conversation content (every message exchanged)

Search is case-insensitive and covers all session formats. Multi-word queries
match independently ("mem leak" matches "Debug memory leak").

## Text selection

Hold **Alt** while dragging to select text from the preview pane.
Or press `Ctrl+Y` to copy the full conversation to clipboard.

## Lazy loading

- Sessions load in the background on startup; the UI is immediately usable.
- Preview shows the first 30 messages. Press `m` or `Space` to load more.

## Resuming sessions

`Ctrl+R` exits kiro-cli-history and launches `kiro-cli chat --resume-id <id>` in the same directory the session was started in.

`Ctrl+N` starts a fresh `kiro-cli chat` session in the current directory.
