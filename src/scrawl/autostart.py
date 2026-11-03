"""Start Scrawl at login via the per-user registry Run key.

Required permissions: write to ``HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\
CurrentVersion\\Run`` (the signed-in user's own hive; no elevation needed).

Usage:
    autostart.enable(dry_run=True)    # shows what would be written
    autostart.enable()
    autostart.is_enabled()
    autostart.disable()

Notes:
    The entry launches ``pythonw.exe`` (no console window) with ``--hidden`` so
    the app starts quietly in the tray instead of popping a window at login.
"""

import logging
import sys
from pathlib import Path

from scrawl.exceptions import ScrawlError

logger = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Scrawl"


def command_line() -> str:
    """Return the command the Run entry will execute."""
    interpreter = Path(sys.executable)
    windowless = interpreter.with_name("pythonw.exe")
    exe = windowless if windowless.exists() else interpreter
    return f'"{exe}" -m scrawl run --hidden'


def _require_windows() -> None:
    if sys.platform != "win32":
        raise ScrawlError("autostart is only supported on Windows")


def is_enabled() -> bool:
    """Return whether the Run entry exists."""
    _require_windows()
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise ScrawlError(f"could not read the registry Run key: {exc}") from exc
    return True


def enable(*, dry_run: bool = False) -> str:
    """Create the Run entry and return a human-readable description.

    With ``dry_run`` nothing is written.
    """
    _require_windows()
    import winreg

    command = command_line()
    if dry_run:
        return f"would set HKCU\\{RUN_KEY}\\{VALUE_NAME} = {command}"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command)
    except OSError as exc:
        raise ScrawlError(f"could not write the registry Run key: {exc}") from exc
    logger.info("autostart enabled: %s", command)
    return f"autostart enabled: {command}"


def disable(*, dry_run: bool = False) -> str:
    """Remove the Run entry (a no-op if absent) and describe what happened."""
    _require_windows()
    import winreg

    if not is_enabled():
        return "autostart was not enabled"
    if dry_run:
        return f"would delete HKCU\\{RUN_KEY}\\{VALUE_NAME}"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except OSError as exc:
        raise ScrawlError(f"could not delete the registry Run entry: {exc}") from exc
    logger.info("autostart disabled")
    return "autostart disabled"
