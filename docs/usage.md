# Usage

## Quick start

```bash
kiro-cli-history           # open all sessions
kiro-cli-history .         # open with current directory pre-filtered
kiro-cli-history /path     # open with specific path pre-filtered
```

---

## Keyboard shortcuts

### Session actions

| Key | Action |
|-----|--------|
| `Ctrl+R` | Resume selected session in Kiro CLI |
| `Ctrl+N` | Start a new Kiro CLI session (current directory) |
| `Alt+N` | Resume selected session in a different directory |
| `Ctrl+Y` | Copy full conversation to clipboard |
| `Ctrl+X` | Export selected session to `.json.gz` |
| `Ctrl+Del` | Delete selected session (with confirmation) |
| `F2` | Rename selected session |

### Navigation

| Key | Action |
|-----|--------|
| `j` / `↓` | Move down in session list |
| `k` / `↑` | Move up in session list |
| `→` / `l` | Focus preview pane |
| `←` / `h` | Focus session list |
| `m` | Preview page down (also loads more if near bottom) |
| `M` | Preview page up |
| `Space` | Load more messages (session list) |
| `Enter` | Focus preview pane |
| `PageDown/Up` | Scroll preview or jump list by 10 |
| `Home/End` | Scroll preview to top/bottom |

### Search

| Key | Action |
|-----|--------|
| `/` | Focus text search input |
| `p` | Focus path filter input |
| `Ctrl+F` | Open in-preview search |
| `Esc` | Clear both search inputs (no quit) |

### App

| Key | Action |
|-----|--------|
| `?` | Toggle keyboard shortcuts panel (right side) |
| `Ctrl+P` | Command palette (settings, export, retention) |
| `Ctrl+Q` | Exit |
| `Ctrl+C` | Exit (fallback) |

### Korean IME (두벌식) — navigation keys work in Korean mode

| Korean key | English equivalent |
|-----------|-------------------|
| `ㅔ` | `p` (path filter) |
| `ㅓ` | `j` (down) |
| `ㅏ` | `k` (up) |
| `ㅡ` | `m` (page down) |
| `ㅗ` | `h` (session list) |
| `ㅣ` | `l` (preview) |

---

## Two search inputs

**Text search** (`/` to focus): fuzzy-searches session titles, paths, and full message content.

**Path filter** (`p` to focus): substring match on working directory path. Useful when you know which project the session was in.

```bash
kiro-cli-history .        # pre-fills path filter with current directory
```

Both filters compose — path filter narrows the list, text search further narrows within that.

---

## In-preview search (`Ctrl+F`)

Search within the currently selected conversation:

| Key | Action |
|-----|--------|
| `Ctrl+F` | Open search bar in preview pane |
| `Enter` | Next match |
| `Shift+Tab` | Previous match |
| `n` / `N` | Next / previous match (when preview has focus) |
| `Esc` | Close search bar |

---

## Command palette (`Ctrl+P`)

| Command | Description |
|---------|-------------|
| Toggle --trust-all-tools | Enable/disable the flag on resume/new |
| Toggle single-turn sessions | Show/hide sessions with only one exchange |
| Toggle untitled sessions | Show/hide sessions with no title |
| Set Retention Days… | Choose 90 / 180 / 365 / ∞ for archive retention |
| Export All Transcripts… | Save all sessions as `.tar.gz` to current directory |
| Set Theme… | Change colour theme |
| Toggle Debug Logging | Enable/disable debug log file |
| Reset to Default Settings | Apply defaults immediately |

---

## New session (`Ctrl+N`)

Starts `kiro-cli chat` immediately in the current working directory.

## Resume in new directory (`Alt+N`)

1. Select a session in the list
2. Press `Alt+N`
3. `DirConfirmScreen` opens — pre-filled with the session's original directory
4. Edit the path if needed, press `Enter` to confirm
5. Runs `kiro-cli chat --resume-id <id>` from the new directory

The directory is created automatically if it doesn't exist.

## Export session (`Ctrl+X`)

Exports the selected session as a compressed JSON file:
- **Format**: `kiro-YYYYMMDD_HHMMSS-<title>.json.gz`
- **Location**: current working directory
- **Contents**: session metadata + all messages
- Notification shown on completion (bottom-right)

## Delete session (`Ctrl+Del`)

Shows a confirmation dialog (Cancel is default focus — safer).
- JSONL sessions: deletes `.jsonl` + `.json` sidecar files
- SQLite sessions: calls `kiro-cli chat --delete-session <id>`
- Archive sessions: deletes the archive file
- Session removed from list immediately

---

## Archive (SQLite retention)

SQLite sessions are automatically backed up to an `archive/` directory:
- New SQLite sessions → `archive/<id>.json` on startup
- Files older than `retention_days` → compressed to `archive/<id>.json.gz`
- Configure via `Ctrl+P → Set Retention Days…` (default: 90 days)

---

## Text selection

Hold **Alt** while dragging to select text from the preview pane.
Or press `Ctrl+Y` to copy the full conversation to clipboard.

---

## Lazy loading

- Sessions load in the background; UI is immediately usable
- Preview shows the first 30 messages; press `m` or `Space` to load more
- ripgrep (bundled) accelerates content search when cold cache
