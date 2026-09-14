# Usage

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `/` | Focus search bar |
| `Down` / `Up` or `j` / `k` | Navigate sessions |
| `Right` or `l` | Focus preview pane (for scrolling) |
| `Left` or `h` | Focus back to session list |
| `m` or `Space` | Load more messages (lazy loading) |
| `F2` | Rename selected session |
| `Ctrl+R` | Resume session in Kiro CLI |
| `Ctrl+N` | Start a new Kiro CLI session |
| `Ctrl+Y` | Copy conversation to clipboard |
| `Ctrl+P` | Open command palette |
| `Ctrl+F` | Focus search bar |
| `Esc` | Clear search / Quit |
| `Ctrl+C` | Quit |

## Command palette (`Ctrl+P`)

| Command | Description |
|---------|-------------|
| Toggle --trust-all-tools | Enable/disable the flag on resume/new |
| Toggle single-turn sessions | Show/hide sessions with only one exchange (hidden by default) |
| Toggle untitled sessions | Show/hide sessions with no title (hidden by default) |

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
