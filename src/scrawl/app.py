"""Application bootstrap: single-instance check, shell, window, and teardown.

Required permissions: read/write on the notes and config folders; loopback
socket on the configured port; ``RegisterHotKey`` and a tray icon (all
per-user, no elevation).

Usage:
    run_app(config, hidden=False, initial=None)
    run_app(config, hidden=True, initial=None)       # start quietly in the tray
    run_app(config, hidden=False, initial=Command.NEW)

Notes:
    If Scrawl is already running, ``run_app`` forwards the request to it and
    returns instead of starting a second copy.
"""

import logging
import queue
import sys
from typing import TYPE_CHECKING

from scrawl import winutil
from scrawl.commands import Command
from scrawl.config import Config, load_state
from scrawl.exceptions import ShellError
from scrawl.ipc import SingleInstanceServer, send_command
from scrawl.store import NoteStore

if TYPE_CHECKING:
    from scrawl.shell import ShellThread

logger = logging.getLogger(__name__)


def run_app(config: Config, *, hidden: bool, initial: Command | None) -> int:
    """Run Scrawl until the user quits, or hand off to the running instance.

    Args:
        config: Loaded settings.
        hidden: Start without showing the window (used at login).
        initial: Command to run once started, e.g. ``Command.NEW``.

    Returns:
        Process exit code.
    """
    events: queue.Queue[Command] = queue.Queue()
    server = SingleInstanceServer(config.ipc_port, events)
    if not server.start():
        return _forward_to_running(config, hidden=hidden, initial=initial)

    shell: ShellThread | None = None
    window = None
    try:
        # DPI awareness must be set before any window exists.
        winutil.enable_dpi_awareness()
        shell, warnings, resident = _start_shell(config, events)
        # Imported here so CLI-only commands never pay the Tk import cost.
        from scrawl.ui.window import MainWindow

        window = MainWindow(
            config,
            load_state(),
            NoteStore(config.notes_dir),
            events,
            resident=resident,
            warnings=warnings,
        )
        window.run(hidden=hidden, initial=initial)
        return 0
    finally:
        if shell is not None:
            shell.stop()
        if window is not None:
            window.destroy()
        server.stop()


def _forward_to_running(config: Config, *, hidden: bool, initial: Command | None) -> int:
    """Ask the already-running instance to do what this launch wanted."""
    if hidden and initial is None:
        logger.info("Scrawl is already running; nothing to do for a hidden start")
        return 0
    command = initial or Command.SHOW
    send_command(config.ipc_port, command)
    logger.info("Scrawl is already running; sent %r to it", command.value)
    return 0


def _start_shell(
    config: Config, events: "queue.Queue[Command]"
) -> "tuple[ShellThread | None, list[str], bool]":
    """Start the tray/hotkey shell where supported.

    Returns:
        ``(shell, warnings, resident)`` where ``resident`` says whether the
        user has any way to get the window back once it is hidden.
    """
    if sys.platform != "win32":
        return None, ["global hotkeys and the tray icon are only supported on Windows"], False

    from scrawl.hotkeys import parse_hotkey
    from scrawl.shell import ShellThread

    shell = ShellThread(
        {
            Command.NEW: parse_hotkey(config.hotkey_new),
            Command.TOGGLE: parse_hotkey(config.hotkey_toggle),
        },
        events,
    )
    try:
        warnings = shell.start()
    except ShellError as exc:
        # The window still works without hotkeys and tray; degrade, don't die.
        logger.error("%s", exc)
        return None, [str(exc)], False
    resident = shell.tray_available or shell.hotkeys_registered > 0
    return shell, warnings, resident
