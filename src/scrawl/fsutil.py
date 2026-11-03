"""Filesystem helpers shared by the store, config, and state modules.

Required permissions: write access to the target directory only.
"""

import contextlib
import logging
import os
import time
from pathlib import Path

from scrawl.exceptions import StorageError

logger = logging.getLogger(__name__)

# The notes folder usually lives under OneDrive, whose sync client briefly
# holds files open. A short retry rides that out instead of failing a save.
_REPLACE_ATTEMPTS = 5
_REPLACE_DELAY_S = 0.05


def atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` so a crash can never leave a half-written file.

    The text goes to a sibling temp file, is flushed to disk, then renamed over
    the target. Content is UTF-8 with LF newlines regardless of platform.

    Args:
        path: Destination file. Parent directories are created if missing.
        text: Full file content.

    Raises:
        StorageError: If the file could not be written or replaced.
    """
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tmp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        _replace_with_retry(tmp, path)
    except OSError as exc:
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
        raise StorageError(f"could not write {path}: {exc}") from exc


def _replace_with_retry(source: Path, target: Path) -> None:
    """Rename ``source`` over ``target``, retrying on transient sharing errors."""
    for attempt in range(1, _REPLACE_ATTEMPTS + 1):
        try:
            source.replace(target)
        except PermissionError:
            if attempt == _REPLACE_ATTEMPTS:
                raise
            logger.debug("replace of %s blocked (attempt %d); retrying", target, attempt)
            time.sleep(_REPLACE_DELAY_S)
        else:
            return
