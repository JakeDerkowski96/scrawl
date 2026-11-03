"""Behavior tests that drive the real Tk window without running its main loop.

These need a desktop session able to create Tk windows; they skip otherwise.
"""

import gc
import queue
import time
import tkinter as tk
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from scrawl.commands import Command
from scrawl.config import Config, State
from scrawl.store import NoteStore

pytest.importorskip("tkinter")

from scrawl.ui.window import MainWindow  # noqa: E402


@dataclass
class Harness:
    window: MainWindow
    store: NoteStore
    events: "queue.Queue[Command]"

    def type(self, text: str) -> None:
        """Insert text as if typed, and let Tk deliver the <<Modified>> event."""
        self.window._editor.insert("end", text)
        self.window.root.update()


def _create_window(config: Config, store: NoteStore, events: "queue.Queue[Command]") -> MainWindow:
    """Create a window, retrying Tk's occasional init flake before skipping.

    Creating and destroying many Tk roots in one process can intermittently
    fail with "invalid command name tcl_findLibrary". The app only ever makes
    one root, so this is a test-suite artifact; retrying keeps real failures
    visible instead of hiding them behind a skip.
    """
    last_error: tk.TclError | None = None
    for _ in range(3):
        try:
            return MainWindow(config, State(), store, events, resident=True, warnings=[])
        except tk.TclError as exc:
            last_error = exc
            gc.collect()
            time.sleep(0.2)
    pytest.skip(f"cannot create a Tk window here: {last_error}")


@pytest.fixture
def harness(tmp_path: Path) -> Iterator[Harness]:
    config = Config(notes_dir=tmp_path / "notes", autosave_ms=100)
    store = NoteStore(config.notes_dir)
    events: queue.Queue[Command] = queue.Queue()
    window = _create_window(config, store, events)
    window.root.update()
    yield Harness(window, store, events)
    window.destroy()


def _only_note_text(h: Harness) -> str:
    (note,) = h.store.list_notes()
    return h.store.read(note.id)


def test_typing_autosaves_after_a_pause(harness: Harness) -> None:
    harness.type("hello world")
    # Let the debounced autosave timer fire.
    harness.window.root.after(300, harness.window.root.quit)
    harness.window.root.mainloop()
    assert _only_note_text(harness) == "hello world"


def test_flush_saves_immediately(harness: Harness) -> None:
    harness.type("urgent")
    assert harness.window._flush() is True
    assert _only_note_text(harness) == "urgent"


def test_blank_new_note_creates_no_file(harness: Harness) -> None:
    harness.window.new_note()
    harness.window.new_note()
    assert harness.store.list_notes() == []


def test_new_note_saves_the_previous_one_and_starts_blank(harness: Harness) -> None:
    harness.type("first")
    harness.window.new_note()
    assert harness.window._editor.get_text() == ""
    harness.type("second")
    harness.window._flush()
    assert sorted(harness.store.read(n.id) for n in harness.store.list_notes()) == [
        "first",
        "second",
    ]


def test_clearing_a_saved_note_removes_it_when_leaving(harness: Harness) -> None:
    harness.type("temp")
    harness.window._flush()
    harness.window._editor.delete("1.0", "end")
    harness.window.root.update()
    harness.window.new_note()
    assert harness.store.list_notes() == []


def test_ctrl_enter_toggles_checkbox_and_keeps_caret(harness: Harness) -> None:
    harness.type("- [ ] buy milk")
    editor = harness.window._editor
    editor.mark_set("insert", "1.8")
    assert editor._on_toggle(None) == "break"
    assert editor.get_text() == "- [x] buy milk"
    assert editor.index("insert") == "1.8"
    assert editor.tag_ranges("done")  # checked items are struck through
    editor._on_toggle(None)
    assert editor.get_text() == "- [ ] buy milk"
    assert not editor.tag_ranges("done")


def test_enter_continues_a_checklist(harness: Harness) -> None:
    harness.type("- [ ] one")
    editor = harness.window._editor
    editor.mark_set("insert", "end-1c")
    assert editor._on_return(None) == "break"
    assert editor.get_text() == "- [ ] one\n- [ ] "


def test_enter_on_an_empty_item_ends_the_list(harness: Harness) -> None:
    harness.type("- [ ] one\n- [ ] ")
    editor = harness.window._editor
    editor.mark_set("insert", "end-1c")
    assert editor._on_return(None) == "break"
    assert editor.get_text() == "- [ ] one\n"


def test_enter_in_plain_text_is_left_to_tk(harness: Harness) -> None:
    harness.type("just words")
    editor = harness.window._editor
    editor.mark_set("insert", "end-1c")
    assert editor._on_return(None) is None


def test_enter_mid_line_is_left_to_tk(harness: Harness) -> None:
    harness.type("- [ ] one")
    editor = harness.window._editor
    editor.mark_set("insert", "1.4")
    assert editor._on_return(None) is None


def test_clicking_the_box_toggles_it(harness: Harness) -> None:
    window = harness.window
    window.root.deiconify()
    harness.type("- [ ] click me")
    window.root.update()
    bbox = window._editor.bbox("1.3")  # the space inside [ ]
    assert bbox is not None

    class Click:
        x = bbox[0] + 1
        y = bbox[1] + 1

    assert window._editor._on_click(Click()) == "break"
    assert window._editor.get_text() == "- [x] click me"


def test_clicking_text_does_not_toggle(harness: Harness) -> None:
    window = harness.window
    window.root.deiconify()
    harness.type("- [ ] click me")
    window.root.update()
    bbox = window._editor.bbox("1.10")
    assert bbox is not None

    class Click:
        x = bbox[0] + 1
        y = bbox[1] + 1

    assert window._editor._on_click(Click()) is None
    assert window._editor.get_text() == "- [ ] click me"


def test_sidebar_lists_saved_notes_and_filters_by_search(harness: Harness) -> None:
    harness.store.write("a", "Groceries\nmilk")
    harness.store.write("b", "Ideas\napp")
    window = harness.window
    window._refresh_list()
    assert window._sidebar.listbox.size() == 2

    window._sidebar._query.set("milk")
    window._refresh_list()
    assert [n.id for n in window._visible_notes] == ["a"]


def test_selecting_a_note_loads_it_and_flushes_the_current_one(harness: Harness) -> None:
    harness.store.write("saved", "old note")
    harness.type("in progress")
    window = harness.window
    window._refresh_list()
    index = next(i for i, n in enumerate(window._visible_notes) if n.id == "saved")
    window._on_sidebar_select(index)
    assert window._editor.get_text() == "old note"
    assert any(harness.store.read(n.id) == "in progress" for n in harness.store.list_notes())


def test_external_edit_is_picked_up_on_show_when_unmodified(harness: Harness) -> None:
    harness.type("v1")
    harness.window._flush()
    (note,) = harness.store.list_notes()
    harness.store.write(note.id, "v2 from elsewhere")
    harness.window.show()
    assert harness.window._editor.get_text() == "v2 from elsewhere"


def test_external_edit_never_overwrites_unsaved_typing(harness: Harness) -> None:
    harness.type("v1")
    harness.window._flush()
    (note,) = harness.store.list_notes()
    harness.type(" plus my typing")
    harness.store.write(note.id, "v2 from elsewhere")
    harness.window.show()
    assert harness.window._editor.get_text() == "v1 plus my typing"


def test_delete_moves_note_to_trash_after_confirmation(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("scrawl.ui.window.messagebox.askyesno", lambda *a, **k: True)
    harness.type("doomed")
    harness.window._flush()
    harness.window._delete_current()
    assert harness.store.list_notes() == []
    assert len(list((harness.store.root / ".trash").glob("*.md"))) == 1
    assert harness.window._editor.get_text() == ""


def test_delete_declined_keeps_the_note(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scrawl.ui.window.messagebox.askyesno", lambda *a, **k: False)
    harness.type("safe")
    harness.window._flush()
    harness.window._delete_current()
    assert _only_note_text(harness) == "safe"
    assert harness.window._editor.get_text() == "safe"


def test_commands_show_toggle_and_new(harness: Harness) -> None:
    window = harness.window
    window._dispatch(Command.SHOW)
    assert window.root.state() == "normal"
    window.hide()
    assert window.root.state() == "withdrawn"
    window._dispatch(Command.SHOW)
    assert window.root.state() == "normal"

    harness.type("keep me")
    window._dispatch(Command.NEW)
    assert window._editor.get_text() == ""
    assert _only_note_text(harness) == "keep me"


def test_events_from_other_threads_are_drained_by_poll(harness: Harness) -> None:
    harness.events.put(Command.SHOW)
    harness.window.hide()
    harness.window._poll()
    assert harness.window.root.state() == "normal"


def test_hide_is_ignored_when_nothing_could_bring_the_window_back(tmp_path: Path) -> None:
    config = Config(notes_dir=tmp_path / "notes")
    window = MainWindow(
        config, State(), NoteStore(config.notes_dir), queue.Queue(), resident=False, warnings=[]
    )
    try:
        window.show()
        window.hide()
        assert window.root.state() == "normal"
    finally:
        window.destroy()


def test_theme_toggle_updates_state(harness: Harness) -> None:
    window = harness.window
    start = window._state.theme
    window._toggle_theme()
    assert window._state.theme != start
    window._toggle_theme()
    assert window._state.theme == start


def test_zoom_is_clamped(harness: Harness) -> None:
    window = harness.window
    for _ in range(100):
        window._zoom(1)
    assert window._state.font_size == 48
    for _ in range(100):
        window._zoom(-1)
    assert window._state.font_size == 6
    window._zoom(0)
    assert window._state.font_size == window._config.font_size


def test_quit_saves_content_and_remembers_the_note(harness: Harness) -> None:
    harness.type("remember me")
    harness.window.quit()
    assert _only_note_text(harness) == "remember me"
    assert harness.window._state.last_note_id == harness.store.list_notes()[0].id


def test_save_failure_is_surfaced_and_keeps_text(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scrawl.exceptions import StorageError

    def boom(*_args: object) -> None:
        raise StorageError("disk full")

    monkeypatch.setattr(harness.store, "write", boom)
    harness.type("do not lose me")
    assert harness.window._flush() is False
    assert "SAVE FAILED" in harness.window._status.get()
    assert harness.window._editor.get_text() == "do not lose me"
    harness.window._cancel_save_job()
