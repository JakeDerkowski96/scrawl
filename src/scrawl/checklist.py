"""Pure text helpers for Markdown-style checkbox and bullet lines.

Required permissions: none.

Usage:
    toggle_line("- [ ] buy milk")   # -> "- [x] buy milk"
    toggle_line("buy milk")         # -> "- [ ] buy milk"
    continuation("- [x] done")      # -> Continuation(prefix="- [ ] ", empty=False)

Notes:
    These functions work on single lines of text and know nothing about Tk, so
    they can be tested without a window.
"""

import re
from dataclasses import dataclass

_CHECKBOX_RE = re.compile(r"^(?P<indent>\s*)(?P<bullet>[-*+])\s+\[(?P<mark>[ xX])\](?P<rest>.*)$")
_BULLET_RE = re.compile(r"^(?P<indent>\s*)(?P<bullet>[-*+])\s+(?P<rest>.*)$")
_NUMBERED_RE = re.compile(r"^(?P<indent>\s*)(?P<num>\d+)(?P<sep>[.)])\s+(?P<rest>.*)$")


@dataclass(frozen=True)
class Continuation:
    """What pressing Enter at the end of a list line should do.

    Attributes:
        prefix: Marker to start the next line with (e.g. ``"- [ ] "``).
        empty: True when the current line holds only the marker, meaning the
            user is ending the list and the marker should be removed instead.
    """

    prefix: str
    empty: bool


def is_checkbox(line: str) -> bool:
    """Return whether ``line`` is a ``- [ ]`` / ``- [x]`` item."""
    return _CHECKBOX_RE.match(line) is not None


def is_done(line: str) -> bool:
    """Return whether ``line`` is a checked checkbox item."""
    match = _CHECKBOX_RE.match(line)
    return match is not None and match.group("mark") in "xX"


def checkbox_span(line: str) -> tuple[int, int] | None:
    """Return the ``[start, end)`` columns of the ``[ ]`` brackets, if any.

    Used to decide whether a mouse click landed on the box itself.
    """
    match = _CHECKBOX_RE.match(line)
    if match is None:
        return None
    # The mark sits one column after the opening bracket; the span is 3 wide.
    mark_col = match.start("mark")
    return mark_col - 1, mark_col + 2


def toggle_line(line: str) -> str:
    """Flip a checkbox line, or turn a bullet or plain line into a checkbox.

    ``- [ ]`` and ``- [x]`` swap; ``- text`` becomes ``- [ ] text``; any other
    non-blank text becomes ``- [ ] text``. A blank line becomes an empty
    checkbox so the shortcut also starts a new item.
    """
    match = _CHECKBOX_RE.match(line)
    if match is not None:
        new_mark = " " if match.group("mark") in "xX" else "x"
        return f"{match.group('indent')}{match.group('bullet')} [{new_mark}]{match.group('rest')}"

    bullet = _BULLET_RE.match(line)
    if bullet is not None:
        return f"{bullet.group('indent')}{bullet.group('bullet')} [ ] {bullet.group('rest')}"

    indent = line[: len(line) - len(line.lstrip())]
    return f"{indent}- [ ] {line.strip()}".rstrip() + ("" if line.strip() else " ")


def continuation(line: str) -> Continuation | None:
    """Return how to continue a list after ``line``, or ``None`` if not a list.

    Checkbox items continue as unchecked boxes, bullets as bullets, and
    numbered items as the next number.
    """
    match = _CHECKBOX_RE.match(line)
    if match is not None:
        prefix = f"{match.group('indent')}{match.group('bullet')} [ ] "
        return Continuation(prefix=prefix, empty=not match.group("rest").strip())

    bullet = _BULLET_RE.match(line)
    if bullet is not None:
        prefix = f"{bullet.group('indent')}{bullet.group('bullet')} "
        return Continuation(prefix=prefix, empty=not bullet.group("rest").strip())

    numbered = _NUMBERED_RE.match(line)
    if numbered is not None:
        next_num = int(numbered.group("num")) + 1
        prefix = f"{numbered.group('indent')}{next_num}{numbered.group('sep')} "
        return Continuation(prefix=prefix, empty=not numbered.group("rest").strip())

    return None
