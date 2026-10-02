"""widgets.py — Reusable UI widgets for kiro-cli-history.

Contains small, self-contained Textual components used by KiroHistory app.
No dependency on kiro_history.py — safe to import independently.

Widgets:
    PreviewSearchInput  — search input with Shift+Tab prev-match binding
    RenameScreen        — modal dialog for renaming a session
    SessionItem         — single row in the session list
    EasterEggHeader     — Header that shows easter egg only when expanded
"""

import os
from datetime import datetime

from textual import on
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Header, Input, ListItem, ListView, Static


class EasterEggHeader(Header):
    """Header that refreshes title when clicked (to show/hide easter egg)."""

    def _on_click(self) -> None:
        """Toggle tall and refresh title display."""
        super()._on_click()
        # Force title refresh after CSS class toggle
        from textual.widgets._header import HeaderTitle
        from textual.css.query import NoMatches
        try:
            self.query_one(HeaderTitle).update(self.format_title())
        except NoMatches:
            pass  # HeaderTitle not yet mounted


class PreviewSearchInput(Input):
    """Search input for preview pane.

    Shift+Tab (BackTab) = previous match.
    Enter = next match (handled by App via Input.Submitted).
    """

    BINDINGS = [
        Binding("shift+tab", "prev_match", "Previous match", show=False),
    ]

    class PrevMatchRequested(Message):
        """Emitted when Shift+Tab is pressed (go to previous match)."""
        pass

    def action_prev_match(self) -> None:
        """Handle Shift+Tab → previous match."""
        self.post_message(self.PrevMatchRequested())


class RenameScreen(ModalScreen):
    """Dialog for renaming a session."""

    CSS = """
    RenameScreen {
        align: center middle;
    }
    #rename-dialog {
        width: 80%;
        height: 40%;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
        align: center middle;
    }
    #rename-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    #rename-input {
        margin: 1 0;
        width: 100%;
    }
    #rename-buttons {
        margin-top: 1;
        align: center middle;
    }
    #rename-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "save", "Save", show=False),
    ]

    def __init__(self, current_title: str):
        super().__init__()
        self._current_title = current_title

    def compose(self):
        with Vertical(id="rename-dialog"):
            yield Static("Rename Session", id="rename-title")
            yield Input(value=self._current_title, id="rename-input", placeholder="Enter new title...")
            with Horizontal(id="rename-buttons"):
                yield Button("Save", variant="primary", id="save-btn")
                yield Button("Cancel", id="cancel-btn")

    def on_mount(self) -> None:
        self.query_one("#rename-input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            self.action_save()
        else:
            self.action_cancel()

    @on(Input.Submitted, "#rename-input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in rename input."""
        self.action_save()

    def action_save(self) -> None:
        new_title = self.query_one("#rename-input", Input).value.strip()
        self.dismiss(new_title if new_title else None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class SessionItem(ListItem):
    """A single session row in the list."""

    def __init__(self, session: dict) -> None:
        super().__init__()
        self.session = session

    def compose(self):
        raw_ts = (self.session.get("updated_at") or "")[:10]
        try:
            dt = datetime.strptime(raw_ts, "%Y-%m-%d")
            ts = f"{dt.day} {dt.strftime('%b %Y')}"
        except (ValueError, TypeError):
            ts = raw_ts
        title = (self.session.get("title") or "(untitled)")[:60]
        title = title.replace("[", "\\[").replace("]", "\\]")
        cwd = os.path.basename(self.session.get("cwd") or "")
        msgs = self.session.get("msg_count", 0)
        dur = self.session.get("duration_min", 0)
        dur_str = "-" if dur == 0 else (f"{dur}m" if dur < 60 else f"{dur // 60}h {dur % 60}m")
        yield Static(
            f"[bold]{title}[/bold]\n"
            f"[dim]{cwd}[/dim]  [dim italic]{ts}[/dim italic]  [dim cyan]{msgs} msgs[/dim cyan]  [dim green]{dur_str}[/dim green]",
            markup=True,
        )


class ThemePickerScreen(ModalScreen):
    """Modal list for picking a theme. Dismisses with the chosen theme name or None."""

    CSS = """
    ThemePickerScreen {
        align: center middle;
    }
    #theme-dialog {
        width: 60;
        height: auto;
        max-height: 80%;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    #theme-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    #theme-list {
        height: auto;
        max-height: 20;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, themes: list[str], current: str):
        super().__init__()
        self._themes = themes
        self._current = current

    def compose(self):
        with Vertical(id="theme-dialog"):
            yield Static("Select Theme", id="theme-title")
            items = []
            for name in self._themes:
                label = f"✓ {name}" if name == self._current else f"  {name}"
                items.append(ListItem(Static(label), id=f"theme-{name}"))
            yield ListView(*items, id="theme-list")

    def on_mount(self) -> None:
        lv = self.query_one("#theme-list", ListView)
        # Focus the current theme item
        for i, name in enumerate(self._themes):
            if name == self._current:
                lv.index = i
                break
        lv.focus()

    def on_key(self, event) -> None:
        """Handle navigation keys for the theme list."""
        lv = self.query_one("#theme-list", ListView)
        if event.key == "pageup":
            event.prevent_default()
            event.stop()
            lv.index = max(0, lv.index - 10)
        elif event.key == "pagedown":
            event.prevent_default()
            event.stop()
            lv.index = min(len(self._themes) - 1, lv.index + 10)
        elif event.key == "home":
            event.prevent_default()
            event.stop()
            lv.index = 0
        elif event.key == "end":
            event.prevent_default()
            event.stop()
            lv.index = len(self._themes) - 1

    @on(ListView.Selected)
    def _on_theme_selected(self, event: ListView.Selected) -> None:
        # id is "theme-{name}" — strip prefix
        theme_name = event.item.id[len("theme-"):]
        self.dismiss(theme_name)

    def action_cancel(self) -> None:
        self.dismiss(None)


class MissingDirScreen(ModalScreen):
    """Modal dialog shown when a session's original directory no longer exists."""

    CSS = """
    MissingDirScreen {
        align: center middle;
    }
    #missing-dir-dialog {
        width: 80%;
        height: auto;
        max-width: 80;
        border: thick $error;
        background: $surface;
        padding: 1 2;
        align: center middle;
    }
    #missing-dir-title {
        text-align: center;
        text-style: bold;
        color: $error;
        margin-bottom: 1;
    }
    #missing-dir-info {
        text-align: center;
        margin-bottom: 1;
    }
    #missing-dir-buttons {
        margin-top: 1;
        align: center middle;
    }
    #missing-dir-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, missing_cwd: str):
        super().__init__()
        self._missing_cwd = missing_cwd

    def compose(self):
        with Vertical(id="missing-dir-dialog"):
            yield Static("Directory Not Found", id="missing-dir-title")
            yield Static(
                f"[dim]{self._missing_cwd}[/dim]\n\nHow would you like to resume?",
                id="missing-dir-info",
                markup=True,
            )
            with Horizontal(id="missing-dir-buttons"):
                yield Button("Create Directory", variant="primary", id="create-btn")
                yield Button("Use Current Dir", variant="default", id="current-btn")
                yield Button("Cancel", id="cancel-btn")

    def on_mount(self) -> None:
        self.query_one("#create-btn", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "create-btn":
            self.dismiss("create")
        elif event.button.id == "current-btn":
            self.dismiss("current")
        else:
            self.dismiss(None)



class RetentionPickerScreen(ModalScreen):
    """Modal for picking retention days. Dismisses with chosen int or None."""

    CSS = """
    RetentionPickerScreen {
        align: center middle;
    }
    #retention-dialog {
        width: 50;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    #retention-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    #retention-list {
        height: auto;
    }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, options: list[tuple[str, int]], current: int):
        super().__init__()
        self._options = options  # [(label, days), ...]
        self._current = current

    def compose(self):
        with Vertical(id="retention-dialog"):
            yield Static("Set Retention Days", id="retention-title")
            items = []
            for label, days in self._options:
                marker = "✓ " if days == self._current else "  "
                items.append(ListItem(Static(f"{marker}{label}"), id=f"ret-{days}"))
            yield ListView(*items, id="retention-list")

    def on_mount(self) -> None:
        lv = self.query_one("#retention-list", ListView)
        for i, (_, days) in enumerate(self._options):
            if days == self._current:
                lv.index = i
                break
        lv.focus()

    @on(ListView.Selected)
    def _on_selected(self, event: ListView.Selected) -> None:
        raw = event.item.id[len("ret-"):]
        self.dismiss(int(raw))

    def action_cancel(self) -> None:
        self.dismiss(None)



class KeysHelpScreen(ModalScreen):
    """Right-side keyboard shortcut reference panel. Toggle with '?'."""

    CSS = """
    KeysHelpScreen {
        align: right top;
        background: transparent;
    }
    #keys-panel {
        width: 38;
        height: 100%;
        background: $surface;
        border-left: thick $accent;
        padding: 1 2;
        overflow-y: auto;
    }
    #keys-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    .key-row {
        height: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("question_mark", "dismiss", "Close"),
    ]

    SHORTCUT_ROWS = [
        ("Ctrl+R",       "Resume session"),
        ("Ctrl+N",       "New session (current dir)"),
        ("Alt+N",        "Resume selected in new dir"),
        ("Ctrl+Y",       "Copy conversation"),
        ("Ctrl+X",       "Export session to .json.gz"),
        ("Ctrl+Del",     "Delete session"),
        ("Ctrl+F",       "Search in preview"),
        ("Ctrl+P",       "Command palette"),
        ("Ctrl+Q",       "Exit"),
        ("",             ""),
        ("/",            "Focus text search"),
        ("p",            "Focus path filter"),
        ("j",            "Session list down"),
        ("k",            "Session list up"),
        ("m",            "Preview page down"),
        ("M",            "Preview page up"),
        ("Enter",        "Focus preview"),
        ("← / h",       "Focus session list"),
        ("→ / l",       "Focus preview"),
        ("",             ""),
        ("F2",           "Rename session"),
        ("?",            "Toggle this panel"),
        ("Esc",          "Clear search / path"),
    ]

    def compose(self):
        with Vertical(id="keys-panel"):
            yield Static("⌨  Keyboard Shortcuts", id="keys-title", markup=True)
            for key, desc in self.SHORTCUT_ROWS:
                if not key and not desc:
                    yield Static("")
                else:
                    key_esc = key.replace("[", "\\[")
                    desc_esc = desc.replace("[", "\\[")
                    yield Static(
                        f"[bold cyan]{key_esc:<12}[/bold cyan] {desc_esc}",
                        markup=True, classes="key-row"
                    )


class DirConfirmScreen(ModalScreen):
    """Second-step dialog: confirm or edit the chosen directory path."""

    CSS = """
    DirConfirmScreen {
        align: center middle;
    }
    #dir-confirm-dialog {
        width: 85%;
        max-width: 80;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    #dir-confirm-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    #dir-confirm-label {
        margin-bottom: 0;
        color: $text-muted;
    }
    #dir-confirm-input {
        margin: 0 0 1 0;
        width: 100%;
    }
    #dir-confirm-buttons {
        align: center middle;
    }
    #dir-confirm-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+enter", "confirm", "Confirm", show=False),
    ]

    def __init__(self, initial_path: str, title: str = "Confirm Directory"):
        super().__init__()
        self._initial_path = initial_path
        self._title = title

    def compose(self):
        with Vertical(id="dir-confirm-dialog"):
            yield Static(self._title, id="dir-confirm-title")
            yield Static("Directory path (edit if needed):", id="dir-confirm-label")
            yield Input(value=self._initial_path, id="dir-confirm-input")
            with Horizontal(id="dir-confirm-buttons"):
                yield Button("Confirm", variant="primary", id="confirm-btn")
                yield Button("Cancel", id="cancel-btn")

    def on_mount(self) -> None:
        inp = self.query_one("#dir-confirm-input", Input)
        inp.focus()
        # Move cursor to end
        inp.cursor_position = len(self._initial_path)

    @on(Input.Submitted, "#dir-confirm-input")
    def on_input_submitted(self, event) -> None:
        self.action_confirm()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-btn":
            self.action_confirm()
        else:
            self.action_cancel()

    def action_confirm(self) -> None:
        path = self.query_one("#dir-confirm-input", Input).value.strip()
        self.dismiss(path if path else None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class DeleteConfirmScreen(ModalScreen):
    """Center confirmation dialog before deleting a session."""

    CSS = """
    DeleteConfirmScreen {
        align: center middle;
    }
    #delete-dialog {
        width: 70%;
        max-width: 64;
        height: auto;
        border: thick $error;
        background: $surface;
        padding: 1 2;
    }
    #delete-title {
        text-align: center;
        text-style: bold;
        color: $error;
        margin-bottom: 1;
    }
    #delete-session-title {
        text-align: center;
        margin-bottom: 0;
    }
    #delete-warning {
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
    }
    #delete-buttons {
        margin-top: 1;
        align: center middle;
    }
    #delete-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("left", "prev_button", "Prev", show=False),
        Binding("right", "next_button", "Next", show=False),
    ]

    def __init__(self, session_title: str):
        super().__init__()
        self._session_title = session_title

    def compose(self):
        safe = self._session_title.replace("[", "\\[")
        with Vertical(id="delete-dialog"):
            yield Static("Delete Session", id="delete-title")
            yield Static(f'[bold]"{safe}"[/bold]', id="delete-session-title", markup=True)
            yield Static("This cannot be undone.", id="delete-warning")
            with Horizontal(id="delete-buttons"):
                yield Button("Cancel", variant="primary", id="cancel-btn")
                yield Button("Delete", variant="error", id="delete-btn")

    def on_mount(self) -> None:
        # Default focus on Cancel (safer)
        self.query_one("#cancel-btn", Button).focus()

    def action_prev_button(self) -> None:
        buttons = list(self.query(Button))
        for i, b in enumerate(buttons):
            if b.has_focus:
                buttons[(i - 1) % len(buttons)].focus()
                return

    def action_next_button(self) -> None:
        buttons = list(self.query(Button))
        for i, b in enumerate(buttons):
            if b.has_focus:
                buttons[(i + 1) % len(buttons)].focus()
                return

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "delete-btn")

    def action_cancel(self) -> None:
        self.dismiss(False)
