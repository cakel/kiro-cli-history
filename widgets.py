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
