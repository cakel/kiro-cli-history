# kiro-cli-history

![kiro-cli-history demo](/meta/demo.gif)

A terminal UI for fuzzy-searching, browsing, and resuming [Kiro CLI](https://kiro.dev/docs/cli/) conversations.

## The problem

Kiro CLI has great built-in [conversation persistence](https://kiro.dev/docs/cli/chat/#conversation-persistence) - it saves your sessions and lets you resume them with `--resume` and `--resume-picker`. However, these are scoped to the directory where the session was started. If you work across many projects and directories, finding a specific past conversation means remembering which folder you were in at the time.

`kiro-cli-history` complements Kiro CLI's native persistence by adding **global fuzzy search across all sessions** - regardless of which directory they were started in. It searches the full content of every message exchanged, not just session titles.

## What it offers

- **Global search** - find conversations across all directories, not just the current one
- **Full-text fuzzy search** - searches every message you and Kiro exchanged, not just titles
- **Conversation preview** - read through the full exchange with markdown rendering before deciding to resume
- **In-preview search** - press `Ctrl+F` to search within the current conversation with match highlighting
- **One-key resume** - press `Ctrl+R` to jump into Kiro CLI and continue the conversation
- **Session management** - rename sessions (`F2`), hide single-turn and untitled sessions
- **Lazy loading** - fast startup with background session loading; preview loads incrementally
- **Copy to clipboard** - press `Ctrl+Y` to copy an entire conversation
- **All session formats** - reads all three Kiro CLI storage versions (v1 SQLite, v2 SQLite, v3 JSONL)

## Install

### macOS / Linux

```bash
git clone https://github.com/cakel/kiro-cli-history.git
cd kiro-cli-history
bash install.sh
```

Installs to `~/.local/share/kiro-cli-history` and adds `~/.local/bin` to your PATH.

### Windows

```bat
git clone https://github.com/cakel/kiro-cli-history.git
cd kiro-cli-history
install.bat
```

Installs to `C:\ProgramData\kiro-cli-history` and adds it to your User PATH.

### Dependencies

- Python 3.10+
- [textual](https://github.com/Textualize/textual) (installed automatically)

## Quick start

```bash
kiro-cli-history
```

Run from anywhere. Press `/` to search sessions, `Ctrl+F` to search within a conversation, `Ctrl+R` to resume.

## Documentation

- [Usage and keyboard shortcuts](docs/usage.md)
- [How it works](docs/how-it-works.md)
- [Changelog vs upstream](docs/changelog.md)

## Uninstall

### macOS / Linux

```bash
bash uninstall.sh
```

### Windows

```bat
uninstall.bat
```

## Known issues

- **Command Palette first-open delay**: When opening the Command Palette (`Ctrl+P`) for the first time, you may need to press Enter twice to execute a command. This is due to Textual's internal 0.25s command batching — the first Enter moves focus before results are fully gathered. Subsequent opens work normally.

## Credits

Fork of [prabhugr/kiro-cli-history](https://github.com/prabhugr/kiro-cli-history).  
Inspired by [raine/claude-history](https://github.com/raine/claude-history).

## License

MIT
