"""Plain-text note storage: one Markdown file per note in a single folder.

Required permissions: read/write on the notes folder only.

Usage:
    store = NoteStore(Path("~/Documents/Scrawl").expanduser())
    note = store.create("- [ ] buy milk")
    print(store.read(note.id))

Notes:
    * A note's id is its filename stem and never changes, even when the title
      (derived from the first line) does. Renaming files on every edit would
      fight with OneDrive and make external references unstable.
    * Deleting moves a note to ``.trash/``; nothing is ever unlinked except an
      empty note (see ``discard_if_empty``).
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from scrawl.exceptions import StorageError
from scrawl.fsutil import atomic_write_text

logger = logging.getLogger(__name__)

NOTE_SUFFIX = ".md"
TRASH_DIR = ".trash"

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_MARKER_RE = re.compile(r"^(?:#+\s+|[-*+]\s+\[[ xX]\]\s+|[-*+]\s+|\d+[.)]\s+)")
_TITLE_MAX = 60
# Titles only need the first line, so listing never reads whole files.
_HEAD_BYTES = 1024


@dataclass(frozen=True)
class Note:
    """Metadata for one stored note."""

    id: str
    path: Path
    title: str
    modified: float


def derive_title(text: str) -> str:
    """Return a short title from the first non-blank line of ``text``.

    List and heading markers are stripped so ``- [ ] call mom`` titles as
    ``call mom``.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        title = _MARKER_RE.sub("", stripped, count=1).strip() or stripped
        if len(title) > _TITLE_MAX:
            return title[: _TITLE_MAX - 1].rstrip() + "…"
        return title
    return "Untitled"


class NoteStore:
    """Reads and writes notes under one root folder."""

    def __init__(self, root: Path) -> None:
        self._root = root
        # filename -> (mtime_ns, title); avoids re-reading unchanged files.
        self._title_cache: dict[str, tuple[int, str]] = {}

    @property
    def root(self) -> Path:
        """The folder holding the notes."""
        return self._root

    def path_for(self, note_id: str) -> Path:
        """Return the file path for ``note_id``.

        Raises:
            StorageError: If the id could escape the notes folder.
        """
        if not _ID_RE.match(note_id):
            raise StorageError(f"invalid note id: {note_id!r}")
        return self._root / f"{note_id}{NOTE_SUFFIX}"

    def new_id(self) -> str:
        """Return an unused, time-ordered id such as ``20261031-142501``."""
        base = datetime.now().strftime("%Y%m%d-%H%M%S")
        candidate = base
        suffix = 2
        while self.path_for(candidate).exists():
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    def exists(self, note_id: str) -> bool:
        """Return whether ``note_id`` is saved on disk."""
        return self.path_for(note_id).is_file()

    def get(self, note_id: str) -> Note | None:
        """Return metadata for ``note_id``, or ``None`` if it is not on disk."""
        path = self.path_for(note_id)
        try:
            return self._note_from_path(path)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise StorageError(f"could not read {path}: {exc}") from exc

    def list_notes(self) -> list[Note]:
        """Return all notes, most recently modified first."""
        if not self._root.is_dir():
            return []
        notes: list[Note] = []
        try:
            entries = list(self._root.iterdir())
        except OSError as exc:
            raise StorageError(f"could not list {self._root}: {exc}") from exc
        for path in entries:
            if path.suffix != NOTE_SUFFIX or path.name.startswith(".") or not path.is_file():
                continue
            try:
                notes.append(self._note_from_path(path))
            except OSError as exc:
                # One unreadable file must not hide every other note.
                logger.warning("skipping unreadable note %s: %s", path, exc)
        notes.sort(key=lambda n: (n.modified, n.id), reverse=True)
        return notes

    def read(self, note_id: str) -> str:
        """Return the full text of a note.

        Raises:
            StorageError: If the note is missing or not valid UTF-8.
        """
        path = self.path_for(note_id)
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise StorageError(f"could not read {path}: {exc}") from exc

    def write(self, note_id: str, text: str) -> Note:
        """Save ``text`` as note ``note_id`` (creating it if needed)."""
        path = self.path_for(note_id)
        atomic_write_text(path, text)
        note = self.get(note_id)
        if note is None:  # pragma: no cover - only if the file vanished mid-call
            raise StorageError(f"{path} disappeared right after writing")
        return note

    def create(self, text: str, *, dry_run: bool = False) -> Note:
        """Create a new note holding ``text``.

        With ``dry_run`` the returned ``Note`` describes what would be created
        and nothing is written.
        """
        note_id = self.new_id()
        if dry_run:
            return Note(
                id=note_id,
                path=self.path_for(note_id),
                title=derive_title(text),
                modified=datetime.now().timestamp(),
            )
        return self.write(note_id, text)

    def trash(self, note_id: str) -> Path:
        """Move a note into ``.trash/`` and return its new location.

        Raises:
            StorageError: If the note is missing or cannot be moved.
        """
        source = self.path_for(note_id)
        trash_dir = self._root / TRASH_DIR
        destination = trash_dir / source.name
        try:
            trash_dir.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                stamp = datetime.now().strftime("%H%M%S%f")
                destination = trash_dir / f"{note_id}-{stamp}{NOTE_SUFFIX}"
            source.replace(destination)
        except OSError as exc:
            raise StorageError(f"could not move {source} to trash: {exc}") from exc
        self._title_cache.pop(source.name, None)
        return destination

    def discard_if_empty(self, note_id: str) -> bool:
        """Delete the note's file only if it is blank; return whether it did.

        This is the one place a file is unlinked outright. Reading it first
        guarantees nothing but whitespace can be lost.
        """
        path = self.path_for(note_id)
        if not path.is_file():
            return False
        if self.read(note_id).strip():
            return False
        try:
            path.unlink()
        except OSError as exc:
            raise StorageError(f"could not remove empty note {path}: {exc}") from exc
        self._title_cache.pop(path.name, None)
        return True

    def _note_from_path(self, path: Path) -> Note:
        """Build a ``Note`` from a file, using the title cache when possible."""
        stat = path.stat()
        cached = self._title_cache.get(path.name)
        if cached is not None and cached[0] == stat.st_mtime_ns:
            title = cached[1]
        else:
            with path.open("rb") as handle:
                head = handle.read(_HEAD_BYTES).decode("utf-8", errors="replace")
            title = derive_title(head)
            self._title_cache[path.name] = (stat.st_mtime_ns, title)
        return Note(id=path.stem, path=path, title=title, modified=stat.st_mtime)
