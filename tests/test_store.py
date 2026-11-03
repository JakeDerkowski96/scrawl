"""Tests for note storage."""

import os
from pathlib import Path

import pytest

from scrawl.exceptions import StorageError
from scrawl.store import NoteStore, derive_title


@pytest.mark.parametrize(
    ("text", "title"),
    [
        ("Groceries\n- milk", "Groceries"),
        ("\n\n  spaced out  \nmore", "spaced out"),
        ("# Heading", "Heading"),
        ("- [ ] call mom", "call mom"),
        ("- [x] done", "done"),
        ("1. first", "first"),
        ("", "Untitled"),
        ("   \n  ", "Untitled"),
        ("-", "-"),
    ],
)
def test_derive_title(text: str, title: str) -> None:
    assert derive_title(text) == title


def test_derive_title_truncates_long_lines() -> None:
    title = derive_title("x" * 200)
    assert len(title) == 60
    assert title.endswith("…")


def test_write_then_read_round_trips(store: NoteStore) -> None:
    note = store.write("abc", "hello\nworld")
    assert store.read("abc") == "hello\nworld"
    assert note.id == "abc"
    assert note.title == "hello"


def test_write_uses_lf_newlines(store: NoteStore) -> None:
    store.write("abc", "a\nb")
    assert store.path_for("abc").read_bytes() == b"a\nb"


def test_write_creates_missing_folder(store: NoteStore) -> None:
    assert not store.root.exists()
    store.write("abc", "x")
    assert store.root.is_dir()


def test_write_leaves_no_temp_files(store: NoteStore) -> None:
    store.write("abc", "x")
    assert [p.name for p in store.root.iterdir()] == ["abc.md"]


def test_list_notes_sorts_newest_first(store: NoteStore) -> None:
    store.write("old", "old")
    store.write("new", "new")
    os.utime(store.path_for("old"), (1_000_000, 1_000_000))
    os.utime(store.path_for("new"), (2_000_000, 2_000_000))
    assert [n.id for n in store.list_notes()] == ["new", "old"]


def test_list_notes_on_missing_folder_is_empty(store: NoteStore) -> None:
    assert store.list_notes() == []


def test_list_notes_ignores_other_files_and_trash(store: NoteStore) -> None:
    store.write("keep", "keep")
    (store.root / "readme.txt").write_text("nope")
    (store.root / ".hidden.md").write_text("nope")
    store.trash("keep")
    assert store.list_notes() == []


def test_title_cache_refreshes_when_file_changes(store: NoteStore) -> None:
    store.write("abc", "first title")
    assert store.list_notes()[0].title == "first title"
    store.write("abc", "second title")
    os.utime(store.path_for("abc"), None)
    assert store.list_notes()[0].title == "second title"


def test_new_id_avoids_existing_notes(store: NoteStore, monkeypatch: pytest.MonkeyPatch) -> None:
    first = store.new_id()
    store.write(first, "x")
    second = store.new_id()
    assert second != first
    assert store.path_for(second).exists() is False


@pytest.mark.parametrize("bad", ["../escape", "a/b", "a\\b", "", ".hidden", "with space"])
def test_invalid_ids_are_rejected(store: NoteStore, bad: str) -> None:
    with pytest.raises(StorageError, match="invalid note id"):
        store.path_for(bad)


def test_read_missing_note_raises(store: NoteStore) -> None:
    with pytest.raises(StorageError, match="could not read"):
        store.read("nope")


def test_read_non_utf8_raises_storage_error(store: NoteStore) -> None:
    store.root.mkdir()
    store.path_for("bad").write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(StorageError, match="could not read"):
        store.read("bad")


def test_get_returns_none_for_missing(store: NoteStore) -> None:
    assert store.get("nope") is None


def test_create_dry_run_writes_nothing(store: NoteStore) -> None:
    note = store.create("preview me", dry_run=True)
    assert note.title == "preview me"
    assert not store.root.exists()


def test_create_writes_note(store: NoteStore) -> None:
    note = store.create("real")
    assert store.read(note.id) == "real"


def test_trash_moves_note_and_keeps_content(store: NoteStore) -> None:
    store.write("abc", "precious")
    destination = store.trash("abc")
    assert not store.exists("abc")
    assert destination.read_text(encoding="utf-8") == "precious"
    assert destination.parent.name == ".trash"


def test_trash_twice_does_not_overwrite(store: NoteStore) -> None:
    store.write("abc", "one")
    first = store.trash("abc")
    store.write("abc", "two")
    second = store.trash("abc")
    assert first != second
    assert first.read_text(encoding="utf-8") == "one"
    assert second.read_text(encoding="utf-8") == "two"


def test_trash_missing_note_raises(store: NoteStore) -> None:
    store.root.mkdir()
    with pytest.raises(StorageError, match="could not move"):
        store.trash("nope")


def test_discard_if_empty_removes_blank_note(store: NoteStore) -> None:
    store.write("abc", "  \n ")
    assert store.discard_if_empty("abc") is True
    assert not store.exists("abc")


def test_discard_if_empty_keeps_real_content(store: NoteStore) -> None:
    store.write("abc", "x")
    assert store.discard_if_empty("abc") is False
    assert store.exists("abc")


def test_discard_if_empty_ignores_missing_note(store: NoteStore) -> None:
    assert store.discard_if_empty("nope") is False


def test_write_failure_is_reported_as_storage_error(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file, not a folder")
    broken = NoteStore(blocker / "notes")
    with pytest.raises(StorageError, match="could not write"):
        broken.write("abc", "x")
