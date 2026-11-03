"""The main window: wires the sidebar, editor, autosave, and external commands.

Required permissions: read/write on the notes folder and the config folder.

Usage:
    window = MainWindow(config, state, store, events, resident=True, warnings=[])
    window.run(hidden=False, initial=None)

Notes:
    * Everything here runs on the Tk main thread. Hotkey, tray, and IPC
      threads only put ``Command`` values on ``events``; ``_poll`` drains them.
    * A brand-new note exists only in memory until it has real content, so
      opening and abandoning "new note" never litters the notes folder.
    * Saves are atomic and happen after a short pause in typing, on switching
      notes, on hiding the window, and on quit.
"""

import base64
import logging
import queue
import re
import tkinter as tk
from collections.abc import Callable
from datetime import datetime
from tkinter import font as tkfont
from tkinter import messagebox

from scrawl import icon, search, winutil
from scrawl.commands import Command
from scrawl.config import Config, State, save_state
from scrawl.exceptions import StorageError
from scrawl.store import Note, NoteStore, derive_title
from scrawl.ui.editor import EditorText
from scrawl.ui.sidebar import Sidebar
from scrawl.ui.theme import THEMES, Theme

logger = logging.getLogger(__name__)

_POLL_MS = 50
_RETRY_SAVE_MS = 3000
_DEFAULT_GEOMETRY = "960x640"
_GEOMETRY_RE = re.compile(r"^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$")
_MIN_FONT = 6
_MAX_FONT = 48

HELP_TEXT = """\
Ctrl+N            New note
Ctrl+F            Search notes
Ctrl+Enter        Toggle a checkbox on this line (or make one)
Click [ ]         Toggle that checkbox
Enter             Continue a list / end an empty list item
Ctrl+Shift+Del    Move this note to the trash folder
Ctrl+B            Show / hide the sidebar
Ctrl+T            Switch dark / light theme
Ctrl +  /  -  /  0   Zoom text in / out / reset
Esc / Ctrl+W      Hide the window (Scrawl keeps running in the tray)
Ctrl+Q            Quit Scrawl
F1                This help
"""


class MainWindow:
    """The Scrawl window and its behavior."""

    def __init__(
        self,
        config: Config,
        state: State,
        store: NoteStore,
        events: "queue.Queue[Command]",
        *,
        resident: bool,
        warnings: list[str],
    ) -> None:
        """Build the window (hidden until ``run`` decides to show it).

        Args:
            config: User settings.
            state: Remembered window state; mutated and saved as the user works.
            store: Where notes live.
            events: Commands from hotkeys, the tray, and later launches.
            resident: True if the user can get the window back after hiding it
                (a tray icon or at least one working hotkey). When False,
                closing the window quits instead of hiding it.
            warnings: Startup problems to surface in the status bar.
        """
        self._config = config
        self._state = state
        self._store = store
        self._events = events
        self._resident = resident
        self._warnings = warnings
        self._theme: Theme = THEMES[state.theme]
        self._visible_notes: list[Note] = []
        self._current_id = store.new_id()
        self._saved_text = ""
        self._save_job: str | None = None
        self._tags_job: str | None = None

        self.root = tk.Tk()
        self.root.withdraw()  # avoid a flash of window when starting hidden
        self.root.title("Scrawl")
        self.root.minsize(480, 320)
        self.root.geometry(self._sanitize_geometry(state.geometry))
        self._window_icon = tk.PhotoImage(data=base64.b64encode(icon.png_bytes(64)))
        self.root.iconphoto(True, self._window_icon)

        self._editor_font = tkfont.Font(
            family=config.font_family, size=state.font_size or config.font_size
        )
        self._ui_font = tkfont.Font(family="Segoe UI", size=10)

        self._build_widgets()
        self._bind_shortcuts()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._apply_theme()
        self._open_initial_note()

    # ------------------------------------------------------------------ setup

    def _build_widgets(self) -> None:
        """Create the status bar, sidebar, divider, and editor."""
        self._status = tk.StringVar()
        self._warning = tk.StringVar(value=self._warnings[0] if self._warnings else "")
        self._info = tk.StringVar()

        self._statusbar = tk.Frame(self.root)
        self._statusbar.pack(side="bottom", fill="x")
        self._status_label = tk.Label(
            self._statusbar, textvariable=self._status, font=self._ui_font, anchor="w"
        )
        self._status_label.pack(side="left", padx=(12, 0), pady=3)
        self._info_label = tk.Label(
            self._statusbar, textvariable=self._info, font=self._ui_font, anchor="e"
        )
        self._info_label.pack(side="right", padx=(0, 12), pady=3)
        self._warning_label = tk.Label(
            self._statusbar, textvariable=self._warning, font=self._ui_font, anchor="e"
        )
        self._warning_label.pack(side="right", padx=(0, 16), pady=3)

        self._body = tk.Frame(self.root)
        self._body.pack(side="top", fill="both", expand=True)

        self._sidebar = Sidebar(
            self._body,
            theme=self._theme,
            font=self._ui_font,
            on_select=self._on_sidebar_select,
            on_search=lambda _query: self._refresh_list(),
            on_delete=self._on_sidebar_delete,
        )
        self._divider = tk.Frame(self._body, width=1)
        self._editor = EditorText(self._body, font=self._editor_font, theme=self._theme)
        self._editor.pack(side="right", fill="both", expand=True)
        if self._state.sidebar_visible:
            self._pack_sidebar()

        self._editor.bind("<<Modified>>", self._on_modified)
        self._sidebar.bind("<<SidebarOpened>>", lambda _e: self._editor.focus_set())

    def _pack_sidebar(self) -> None:
        """Show the sidebar and its divider to the left of the editor."""
        self._sidebar.pack(side="left", fill="y", before=self._editor)
        self._divider.pack(side="left", fill="y", before=self._editor)

    def _bind_shortcuts(self) -> None:
        """Register keyboard shortcuts on every widget that can hold focus."""
        shortcuts: dict[str, Callable[[], None]] = {
            "<Control-n>": self.new_note,
            "<Control-f>": self._focus_search,
            "<Control-b>": self._toggle_sidebar,
            "<Control-t>": self._toggle_theme,
            "<Control-q>": self.quit,
            "<Control-w>": self.hide,
            "<Control-Shift-Delete>": self._delete_current,
            "<Control-equal>": lambda: self._zoom(1),
            "<Control-plus>": lambda: self._zoom(1),
            "<Control-minus>": lambda: self._zoom(-1),
            "<Control-0>": lambda: self._zoom(0),
            "<F1>": self._show_help,
            "<Escape>": self._on_escape,
        }
        for sequence, action in shortcuts.items():
            self._bind_shortcut(sequence, action)

        # Tk's Text uses Emacs-style Ctrl+A (line start); notepad users expect select-all.
        for sequence in ("<Control-a>", "<Control-A>"):
            self._editor.bind(sequence, self._select_all)
        self._editor.bind("<Control-MouseWheel>", self._on_ctrl_wheel)

    def _bind_shortcut(self, sequence: str, action: Callable[[], None]) -> None:
        """Bind ``sequence`` (and its CapsLock variant) so it pre-empts Tk's defaults.

        Widget-level bindings run before the class bindings, and returning
        "break" stops them. That matters because Tk's Text/Entry classes bind
        several Emacs-style Ctrl combinations (Ctrl+N, Ctrl+F, Ctrl+B, Ctrl+T).
        """

        def handler(_event: object) -> str:
            action()
            return "break"

        sequences = [sequence]
        last = sequence[-2]
        if sequence.endswith(f"-{last}>") and last.isalpha():
            sequences.append(sequence[:-2] + last.upper() + ">")
        widgets: tuple[tk.Misc, ...] = (
            self.root,
            self._editor,
            self._sidebar.search,
            self._sidebar.listbox,
        )
        for widget in widgets:
            for seq in sequences:
                widget.bind(seq, handler)

    def _sanitize_geometry(self, geometry: str | None) -> str:
        """Return a saved geometry if it is plausibly on-screen, else the default."""
        if not geometry:
            return _DEFAULT_GEOMETRY
        match = _GEOMETRY_RE.match(geometry)
        if match is None:
            return _DEFAULT_GEOMETRY
        width, height, x, y = (int(part) for part in match.groups())
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        width = min(max(width, 480), screen_w)
        height = min(max(height, 320), screen_h)
        # Reject positions that would strand the window off-screen (e.g. after
        # unplugging a monitor); the limits are loose to allow multi-monitor setups.
        if x < -width + 100 or x > 2 * screen_w or y < -10 or y > screen_h - 100:
            return f"{width}x{height}"
        return f"{width}x{height}+{x}+{y}"

    def _open_initial_note(self) -> None:
        """Open the last-used note if it still exists, otherwise start a blank one."""
        last = self._state.last_note_id
        try:
            if last and self._store.exists(last):
                self._current_id = last
                self._load_text(self._store.read(last))
            else:
                self._load_text("")
        except StorageError as exc:
            logger.error("could not open the last note: %s", exc)
            self._set_status(f"Could not open last note: {exc}")
            self._load_text("")
        self._refresh_list()

    # ------------------------------------------------------------- public API

    def run(self, *, hidden: bool, initial: Command | None) -> None:
        """Show (or keep hidden) the window and run the Tk event loop."""
        if hidden:
            self.root.withdraw()
        else:
            self.show()
        if initial == Command.NEW:
            self.show()
            self.new_note()
        self.root.after(_POLL_MS, self._poll)
        self.root.mainloop()

    def show(self) -> None:
        """Bring the window to the front with the editor focused."""
        self._reload_if_changed_on_disk()
        self._refresh_list()
        self.root.deiconify()
        if self.root.state() == "iconic":
            self.root.state("normal")
        self.root.lift()
        winutil.set_dark_titlebar(self.root, self._theme.name == "dark")
        winutil.bring_to_front(self.root)
        self._editor.focus_set()

    def hide(self) -> None:
        """Save and hide the window; the process keeps running."""
        if not self._resident:
            # Nothing could bring the window back, so hiding would strand the app.
            return
        self._flush()
        self._remember_geometry()
        self.root.withdraw()

    def toggle(self) -> None:
        """Hide if the window is active, otherwise show it."""
        if self.root.state() == "normal" and self.root.focus_displayof() is not None:
            self.hide()
        else:
            self.show()

    def new_note(self) -> None:
        """Start a fresh note and focus the editor."""
        self._flush()
        if not self._editor.get_text().strip() and not self._store.exists(self._current_id):
            # Already looking at an empty unsaved note; don't churn ids.
            self._editor.focus_set()
            return
        self._leave_current()
        self._current_id = self._store.new_id()
        self._load_text("")
        self._refresh_list()
        self._editor.focus_set()

    def quit(self) -> None:
        """Save everything and end the event loop."""
        self._flush()
        self._leave_current()
        self._remember_geometry()
        self._state.last_note_id = (
            self._current_id if self._store.exists(self._current_id) else None
        )
        save_state(self._state)
        self.root.quit()

    def destroy(self) -> None:
        """Tear down Tk after the event loop has ended."""
        try:
            self.root.destroy()
        except tk.TclError:
            logger.debug("root window already destroyed")

    # --------------------------------------------------------- command intake

    def _poll(self) -> None:
        """Drain queued commands from other threads, then reschedule."""
        try:
            while True:
                command = self._events.get_nowait()
                try:
                    self._dispatch(command)
                except Exception:
                    # A bug handling one command must not kill the poll loop.
                    logger.exception("error handling command %s", command)
        except queue.Empty:
            pass
        self.root.after(_POLL_MS, self._poll)

    def _dispatch(self, command: Command) -> None:
        logger.debug("command: %s", command.value)
        if command == Command.SHOW:
            self.show()
        elif command == Command.NEW:
            self.show()
            self.new_note()
        elif command == Command.TOGGLE:
            self.toggle()
        elif command == Command.QUIT:
            self.quit()

    # ------------------------------------------------------- note load / save

    def _load_text(self, text: str) -> None:
        """Put ``text`` in the editor as the clean, saved baseline."""
        self._cancel_save_job()
        self._editor.set_text(text)
        # Reset the flag *after* the insert; <<Modified>> events are delivered
        # asynchronously and _on_modified ignores events while the flag is clear.
        self._editor.edit_modified(False)
        self._saved_text = text
        self._update_title_and_info()

    def _on_modified(self, _event: object) -> None:
        """Text changed: schedule an autosave and refresh derived UI."""
        if not self._editor.edit_modified():
            return
        self._editor.edit_modified(False)
        if self._editor.get_text() == self._saved_text:
            return
        self._set_status("Editing…")
        self._schedule_save(self._config.autosave_ms)
        self._update_title_and_info()
        if self._tags_job is None:
            self._tags_job = self.root.after_idle(self._refresh_tags)

    def _refresh_tags(self) -> None:
        self._tags_job = None
        self._editor.refresh_tags()

    def _schedule_save(self, delay_ms: int) -> None:
        self._cancel_save_job()
        self._save_job = self.root.after(delay_ms, self._flush)

    def _cancel_save_job(self) -> None:
        if self._save_job is not None:
            self.root.after_cancel(self._save_job)
            self._save_job = None

    def _flush(self) -> bool:
        """Write the editor content to disk if it changed.

        Returns:
            True if nothing is left unsaved; False if the write failed (it is
            retried automatically and the failure is shown in the status bar).
        """
        self._cancel_save_job()
        text = self._editor.get_text()
        if text == self._saved_text:
            return True
        if not text.strip() and not self._store.exists(self._current_id):
            self._saved_text = text
            return True
        try:
            self._store.write(self._current_id, text)
        except StorageError as exc:
            logger.error("autosave failed: %s", exc)
            self._set_status(f"SAVE FAILED: {exc}")
            self._schedule_save(_RETRY_SAVE_MS)
            return False
        self._saved_text = text
        self._set_status(f"Saved {datetime.now():%H:%M:%S}")
        self._refresh_list()
        return True

    def _leave_current(self) -> None:
        """Called before switching away: drop the current note if it is blank."""
        try:
            if self._store.discard_if_empty(self._current_id):
                logger.debug("discarded empty note %s", self._current_id)
        except StorageError as exc:
            logger.warning("could not discard empty note: %s", exc)

    def _reload_if_changed_on_disk(self) -> None:
        """Pick up edits made elsewhere (OneDrive sync, another editor).

        Only reloads when the editor has no unsaved changes, so it can never
        overwrite what the user is typing.
        """
        if self._editor.get_text() != self._saved_text or not self._store.exists(self._current_id):
            return
        try:
            on_disk = self._store.read(self._current_id)
        except StorageError as exc:
            logger.warning("could not re-read current note: %s", exc)
            return
        if on_disk != self._saved_text:
            logger.info("note %s changed on disk; reloading", self._current_id)
            self._load_text(on_disk)

    def _open_note(self, note_id: str) -> None:
        """Switch the editor to an existing note."""
        if note_id == self._current_id:
            return
        if not self._flush():
            self._set_status("Not switching: the current note could not be saved")
            return
        try:
            text = self._store.read(note_id)
        except StorageError as exc:
            logger.error("could not open note %s: %s", note_id, exc)
            self._set_status(f"Could not open note: {exc}")
            return
        self._leave_current()
        self._current_id = note_id
        self._load_text(text)
        self._refresh_list()

    # ------------------------------------------------------------ list / search

    def _refresh_list(self) -> None:
        """Rebuild the sidebar from disk, honoring the search box."""
        try:
            self._visible_notes = search.search_notes(self._store, self._sidebar.query)
        except StorageError as exc:
            logger.error("could not list notes: %s", exc)
            self._set_status(f"Could not list notes: {exc}")
            return
        self._sidebar.set_titles([note.title for note in self._visible_notes])
        index = next(
            (i for i, note in enumerate(self._visible_notes) if note.id == self._current_id),
            None,
        )
        self._sidebar.select(index)

    def _on_sidebar_select(self, index: int) -> None:
        if 0 <= index < len(self._visible_notes):
            self._open_note(self._visible_notes[index].id)

    def _on_sidebar_delete(self, index: int) -> None:
        if 0 <= index < len(self._visible_notes):
            self._trash_note(self._visible_notes[index].id)

    def _focus_search(self) -> None:
        if not self._sidebar.winfo_ismapped():
            self._toggle_sidebar()
        self._sidebar.search.focus_set()
        self._sidebar.search.selection_range(0, "end")

    # ----------------------------------------------------------------- delete

    def _delete_current(self) -> None:
        self._trash_note(self._current_id)

    def _trash_note(self, note_id: str) -> None:
        """Move a note to the trash folder after confirmation."""
        if note_id == self._current_id:
            self._flush()
        if not self._store.exists(note_id):
            if note_id == self._current_id:
                self._load_text("")
            return
        title = derive_title(self._store.read(note_id)[:2000])
        if not messagebox.askyesno(
            "Move to trash",
            f"Move “{title}” to the trash folder?\n\n"
            f"You can restore it from {self._store.root / '.trash'}.",
            parent=self.root,
        ):
            return
        try:
            destination = self._store.trash(note_id)
        except StorageError as exc:
            logger.error("could not trash note: %s", exc)
            self._set_status(f"Could not delete: {exc}")
            return
        logger.info("moved %s to %s", note_id, destination)
        if note_id == self._current_id:
            self._current_id = self._store.new_id()
            self._load_text("")
        self._refresh_list()
        self._set_status("Moved to trash")

    # ------------------------------------------------------------- appearance

    def _apply_theme(self) -> None:
        """Recolor every widget from the current theme."""
        theme = self._theme
        self.root.configure(bg=theme.bg)
        for frame in (self._body, self._statusbar):
            frame.configure(bg=theme.sidebar_bg if frame is self._statusbar else theme.bg)
        self._divider.configure(bg=theme.border)
        for label in (self._status_label, self._info_label):
            label.configure(bg=theme.sidebar_bg, fg=theme.muted)
        self._warning_label.configure(bg=theme.sidebar_bg, fg=theme.accent)
        self._editor.apply_theme(theme)
        self._sidebar.apply_theme(theme)
        winutil.set_dark_titlebar(self.root, theme.name == "dark")

    def _toggle_theme(self) -> None:
        self._theme = THEMES["light" if self._theme.name == "dark" else "dark"]
        self._state.theme = self._theme.name
        self._apply_theme()

    def _toggle_sidebar(self) -> None:
        if self._sidebar.winfo_ismapped():
            self._sidebar.pack_forget()
            self._divider.pack_forget()
            self._state.sidebar_visible = False
            self._editor.focus_set()
        else:
            self._pack_sidebar()
            self._state.sidebar_visible = True

    def _zoom(self, direction: int) -> None:
        """Change the editor font size (0 resets to the configured size)."""
        if direction == 0:
            size = self._config.font_size
        else:
            size = min(max(int(self._editor_font.cget("size")) + direction, _MIN_FONT), _MAX_FONT)
        self._editor_font.configure(size=size)
        self._state.font_size = size

    def _on_ctrl_wheel(self, event: tk.Event) -> str:
        self._zoom(1 if event.delta > 0 else -1)
        return "break"

    def _select_all(self, _event: object) -> str:
        self._editor.tag_add("sel", "1.0", "end-1c")
        return "break"

    # ------------------------------------------------------------- misc events

    def _on_escape(self) -> None:
        """Esc: clear an active search first, otherwise hide the window."""
        if self.root.focus_get() is self._sidebar.search and self._sidebar.query:
            self._sidebar.clear_query()
            self._editor.focus_set()
        else:
            self.hide()

    def _on_close(self) -> None:
        """The window's close button: hide to the tray, or quit if that is impossible."""
        if self._resident and self._config.close_to_tray:
            self.hide()
        else:
            self.quit()

    def _show_help(self) -> None:
        messagebox.showinfo("Scrawl shortcuts", HELP_TEXT, parent=self.root)

    def _remember_geometry(self) -> None:
        # A withdrawn or minimized window reports a meaningless geometry.
        if self.root.state() == "normal":
            self._state.geometry = self.root.geometry()

    def _set_status(self, message: str) -> None:
        self._status.set(message)

    def _update_title_and_info(self) -> None:
        text = self._editor.get_text()
        title = derive_title(text[:2000]) if text.strip() else "New note"
        self.root.title(f"{title} — Scrawl")
        words = len(text.split())
        self._info.set(f"{words} word{'s' if words != 1 else ''}")
