"""The text editor widget with checkbox and list behavior.

Required permissions: none.

Usage:
    editor = EditorText(parent, font=font, theme=DARK)
    editor.set_text("- [ ] first thing")

Notes:
    Behavior added on top of ``tk.Text``:
      * Ctrl+Enter toggles ``- [ ]`` / ``- [x]`` on the current line (and turns
        plain lines into checkboxes).
      * Clicking a ``[ ]`` box toggles it.
      * Enter at the end of a list line continues the list; Enter on an empty
        list line ends it.
      * Checked items are drawn struck-through and dimmed.
"""

import tkinter as tk
from tkinter import font as tkfont

from scrawl import checklist
from scrawl.ui.theme import Theme


class EditorText(tk.Text):
    """A word-wrapped text widget tuned for notes and checklists."""

    def __init__(self, master: tk.Misc, *, font: tkfont.Font, theme: Theme) -> None:
        super().__init__(
            master,
            wrap="word",
            undo=True,
            maxundo=-1,
            font=font,
            borderwidth=0,
            highlightthickness=0,
            padx=18,
            pady=14,
            spacing1=2,
            spacing3=2,
        )
        self.tag_configure("done", overstrike=True)
        self.apply_theme(theme)
        self.bind("<Return>", self._on_return)
        self.bind("<Control-Return>", self._on_toggle)
        self.bind("<Button-1>", self._on_click)

    def apply_theme(self, theme: Theme) -> None:
        """Recolor the editor."""
        self.configure(
            bg=theme.bg,
            fg=theme.fg,
            insertbackground=theme.fg,
            selectbackground=theme.select_bg,
            selectforeground=theme.select_fg,
        )
        self.tag_configure("done", foreground=theme.done_fg)

    def get_text(self) -> str:
        """Return the full content without Tk's trailing newline."""
        return self.get("1.0", "end-1c")

    def set_text(self, text: str) -> None:
        """Replace the content and clear undo history."""
        self.delete("1.0", "end")
        self.insert("1.0", text)
        self.edit_reset()
        self.refresh_tags()

    def refresh_tags(self) -> None:
        """Re-apply the struck-through style to checked items."""
        self.tag_remove("done", "1.0", "end")
        for number, line in enumerate(self.get_text().split("\n"), start=1):
            if checklist.is_done(line):
                self.tag_add("done", f"{number}.0", f"{number}.end")

    def _replace_line(self, number: int, new_text: str) -> None:
        """Replace one whole line, as a single undo step."""
        self.edit_separator()
        self.delete(f"{number}.0", f"{number}.end")
        self.insert(f"{number}.0", new_text)
        self.edit_separator()
        self.refresh_tags()

    def _on_toggle(self, _event: tk.Event) -> str:
        """Ctrl+Enter: toggle the checkbox on the cursor's line."""
        number, column = (int(part) for part in self.index("insert").split("."))
        line = self.get(f"{number}.0", f"{number}.end")
        new_line = checklist.toggle_line(line)
        self._replace_line(number, new_line)
        # Keep the caret where it was relative to the text, even if the marker grew.
        shifted = max(0, column + len(new_line) - len(line))
        self.mark_set("insert", f"{number}.{min(shifted, len(new_line))}")
        return "break"

    def _on_click(self, event: tk.Event) -> str | None:
        """Toggle a checkbox when its ``[ ]`` is clicked; otherwise do nothing special."""
        number, column = (int(part) for part in self.index(f"@{event.x},{event.y}").split("."))
        line = self.get(f"{number}.0", f"{number}.end")
        span = checklist.checkbox_span(line)
        if span is not None and span[0] <= column < span[1]:
            self._replace_line(number, checklist.toggle_line(line))
            return "break"
        return None

    def _on_return(self, _event: tk.Event) -> str | None:
        """Enter: continue (or end) a list when the caret is at the end of a list line."""
        if self.tag_ranges("sel"):
            return None
        number = int(self.index("insert").split(".")[0])
        if self.compare("insert", "!=", f"{number}.end"):
            return None
        line = self.get(f"{number}.0", f"{number}.end")
        cont = checklist.continuation(line)
        if cont is None:
            return None
        self.edit_separator()
        if cont.empty:
            # Enter on a bare marker means "I'm done with this list".
            self.delete(f"{number}.0", f"{number}.end")
        else:
            self.insert("insert", "\n" + cont.prefix)
        self.see("insert")
        self.edit_separator()
        self.refresh_tags()
        return "break"
