"""Case-insensitive full-text search across notes.

Required permissions: read access to the notes folder.

Usage:
    results = search_notes(store, "milk eggs")   # notes containing both words

Notes:
    A scan of every file is deliberate. For the few hundred small text files
    this app targets it is instant, and it avoids maintaining an index that
    could go stale when files are edited outside the app.
"""

import logging

from scrawl.exceptions import StorageError
from scrawl.store import Note, NoteStore

logger = logging.getLogger(__name__)


def parse_query(query: str) -> list[str]:
    """Split a query into lowercase terms; an empty list means "match all"."""
    return query.casefold().split()


def search_notes(store: NoteStore, query: str) -> list[Note]:
    """Return notes whose text contains every term in ``query``.

    Notes whose *title* matches come first; otherwise results stay in
    most-recently-modified order. A blank query returns every note.
    """
    terms = parse_query(query)
    notes = store.list_notes()
    if not terms:
        return notes

    hits: list[tuple[int, Note]] = []
    for note in notes:
        try:
            haystack = store.read(note.id).casefold()
        except StorageError as exc:
            logger.warning("skipping %s during search: %s", note.id, exc)
            continue
        if all(term in haystack for term in terms):
            title = note.title.casefold()
            rank = 0 if all(term in title for term in terms) else 1
            hits.append((rank, note))
    # sort() is stable, so recency order survives within each rank.
    hits.sort(key=lambda hit: hit[0])
    return [note for _, note in hits]
