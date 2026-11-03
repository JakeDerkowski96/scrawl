"""The small command vocabulary shared by hotkeys, the tray, IPC, and the UI.

Every external trigger (a hotkey press, a tray click, a second launch of the
program) is reduced to one of these values and placed on a queue that the Tk
main thread drains. That keeps all Tk calls on one thread.
"""

from enum import StrEnum


class Command(StrEnum):
    """An instruction for the running window."""

    SHOW = "show"
    NEW = "new"
    TOGGLE = "toggle"
    QUIT = "quit"
