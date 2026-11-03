"""Sidebar: a search box above the list of notes.

Required permissions: none.

Usage:
    sidebar = Sidebar(parent, theme=DARK, font=font,
                      on_select=open_note, on_search=filter_notes,
                      on_delete=trash_note)
    sidebar.set_titles(["Groceries", "Ideas"])
"""

import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import font as tkfont

from scrawl.ui.theme import Theme

_SEARCH_DEBOUNCE_MS = 150


class Sidebar(tk.Frame):
    """Search entry plus note list."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        theme: Theme,
        font: tkfont.Font,
        on_select: Callable[[int], None],
        on_search: Callable[[str], None],
        on_delete: Callable[[int], None],
    ) -> None:
        super().__init__(master, width=240)
        self.pack_propagate(False)
        self._on_select = on_select
        self._on_search = on_search
        self._on_delete = on_delete
        self._search_job: str | None = None

        self._query = tk.StringVar()
        self.search = tk.Entry(self, textvariable=self._query, relief="flat", font=font)
        self.search.pack(fill="x", padx=10, pady=(10, 6), ipady=4)
        self._query.trace_add("write", self._on_query_changed)
        self.search.bind("<Return>", lambda _e: self._focus_first())
        self.search.bind("<Down>", lambda _e: self._focus_first())

        self.listbox = tk.Listbox(
            self,
            activestyle="none",
            exportselection=False,  # keep the highlight while the editor has focus
            borderwidth=0,
            highlightthickness=0,
            font=font,
        )
        self.listbox.pack(fill="both", expand=True, padx=(6, 0), pady=(0, 6))
        self.listbox.bind("<<ListboxSelect>>", self._on_listbox_select)
        self.listbox.bind("<Return>", lambda _e: self._announce_opened())
        self.listbox.bind("<Double-Button-1>", lambda _e: self._announce_opened())

        self._menu = tk.Menu(self, tearoff=False)
        self._menu.add_command(label="Move to trash", command=self._delete_clicked)
        self._menu_index: int | None = None
        self.listbox.bind("<Button-3>", self._on_right_click)
        self.apply_theme(theme)

    @property
    def query(self) -> str:
        """The current search text."""
        return self._query.get()

    def clear_query(self) -> None:
        """Empty the search box (triggers a refresh)."""
        self._query.set("")

    def apply_theme(self, theme: Theme) -> None:
        """Recolor the sidebar."""
        self.configure(bg=theme.sidebar_bg)
        self.search.configure(
            bg=theme.bg,
            fg=theme.fg,
            insertbackground=theme.fg,
            selectbackground=theme.select_bg,
            selectforeground=theme.select_fg,
        )
        self.listbox.configure(
            bg=theme.sidebar_bg,
            fg=theme.sidebar_fg,
            selectbackground=theme.select_bg,
            selectforeground=theme.select_fg,
        )

    def set_titles(self, titles: Sequence[str]) -> None:
        """Replace the list contents."""
        self.listbox.delete(0, "end")
        for title in titles:
            self.listbox.insert("end", f" {title}")

    def select(self, index: int | None) -> None:
        """Highlight one row (or clear the highlight) without firing ``on_select``."""
        self.listbox.selection_clear(0, "end")
        if index is not None:
            self.listbox.selection_set(index)
            self.listbox.see(index)

    def _on_query_changed(self, *_args: object) -> None:
        """Debounce typing so each keystroke does not rescan every note."""
        if self._search_job is not None:
            self.after_cancel(self._search_job)
        self._search_job = self.after(_SEARCH_DEBOUNCE_MS, self._fire_search)

    def _fire_search(self) -> None:
        self._search_job = None
        self._on_search(self._query.get())

    def _focus_first(self) -> str:
        """Enter/Down in the search box: jump to the first result and open it."""
        if self.listbox.size():
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(0)
            self._on_select(0)
            self._announce_opened()
        return "break"

    def _announce_opened(self) -> None:
        """Tell the window the user chose a note on purpose (focus the editor)."""
        self.event_generate("<<SidebarOpened>>")

    def _on_listbox_select(self, _event: object) -> None:
        selection = self.listbox.curselection()  # type: ignore[no-untyped-call]
        if selection:
            self._on_select(int(selection[0]))

    def _on_right_click(self, event: tk.Event) -> None:
        index = self.listbox.nearest(event.y)  # type: ignore[no-untyped-call]
        if index < 0 or index >= self.listbox.size():
            return
        self._menu_index = index
        self._menu.tk_popup(event.x_root, event.y_root)

    def _delete_clicked(self) -> None:
        if self._menu_index is not None:
            self._on_delete(self._menu_index)
