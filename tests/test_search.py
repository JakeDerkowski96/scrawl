"""Tests for full-text search."""

import os

from scrawl.search import parse_query, search_notes
from scrawl.store import NoteStore


def _seed(store: NoteStore) -> None:
    store.write("a", "Groceries\n- milk\n- eggs")
    store.write("b", "Project ideas\nbuy milk later")
    store.write("c", "Milk run notes")
    for index, note_id in enumerate(("a", "b", "c")):
        os.utime(store.path_for(note_id), (1_000 + index, 1_000 + index))


def test_parse_query_lowercases_and_splits() -> None:
    assert parse_query("  Milk   EGGS ") == ["milk", "eggs"]


def test_blank_query_returns_everything(store: NoteStore) -> None:
    _seed(store)
    assert [n.id for n in search_notes(store, "")] == ["c", "b", "a"]


def test_all_terms_must_match(store: NoteStore) -> None:
    _seed(store)
    assert [n.id for n in search_notes(store, "milk eggs")] == ["a"]


def test_search_is_case_insensitive(store: NoteStore) -> None:
    _seed(store)
    assert {n.id for n in search_notes(store, "MILK")} == {"a", "b", "c"}


def test_title_matches_rank_first(store: NoteStore) -> None:
    _seed(store)
    # "c" has milk in its title; "b" and "a" only in the body, though "b" is newer than "a".
    assert [n.id for n in search_notes(store, "milk")] == ["c", "b", "a"]


def test_no_match_returns_empty(store: NoteStore) -> None:
    _seed(store)
    assert search_notes(store, "zebra") == []
