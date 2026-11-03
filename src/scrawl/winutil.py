"""Windows-only window niceties, each a safe no-op on other platforms.

Required permissions: none.

Usage:
    winutil.enable_dpi_awareness()        # before creating the Tk root
    winutil.set_dark_titlebar(root, True)
    winutil.bring_to_front(root)

Notes:
    Every helper swallows (and logs) failures: these are cosmetic or
    best-effort behaviors, and none of them should stop the app from running.
"""

import ctypes
import logging
import sys
import tkinter as tk
from ctypes import wintypes

logger = logging.getLogger(__name__)

MB_ICONERROR = 0x10


def enable_dpi_awareness() -> None:
    """Opt in to DPI awareness so text is crisp instead of bitmap-scaled."""
    if sys.platform != "win32":
        return
    try:
        # 2 = per-monitor aware; falls back below on older Windows builds.
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
    except (OSError, AttributeError):
        try:
            ctypes.WinDLL("user32").SetProcessDPIAware()
        except (OSError, AttributeError):
            logger.debug("could not enable DPI awareness")


def _toplevel_hwnd(widget: tk.Misc) -> int:
    """Return the real Win32 handle of the window containing ``widget``."""
    from scrawl import win32

    # Tk's winfo_id is an inner child window; the frame Windows draws is its parent.
    inner = widget.winfo_id()
    return int(win32.GetParent(inner) or inner)


def set_dark_titlebar(widget: tk.Misc, dark: bool) -> None:
    """Switch the native title bar between dark and light (Windows 10 2004+)."""
    if sys.platform != "win32":
        return
    try:
        from scrawl import win32

        widget.update_idletasks()
        value = ctypes.c_int(1 if dark else 0)
        win32.DwmSetWindowAttribute(
            _toplevel_hwnd(widget),
            win32.DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
    except (OSError, tk.TclError) as exc:
        logger.debug("could not set title bar theme: %s", exc)


def bring_to_front(widget: tk.Misc) -> None:
    """Make the window the foreground window, working around Windows' focus lock.

    Windows refuses ``SetForegroundWindow`` from a process that does not own
    the foreground. Briefly attaching to the foreground thread's input queue
    is the standard way to get the hotkey-summons-window behavior users expect.
    """
    if sys.platform != "win32":
        return
    try:
        from scrawl import win32

        hwnd = _toplevel_hwnd(widget)
        foreground = win32.GetForegroundWindow()
        foreground_thread = win32.GetWindowThreadProcessId(foreground, None) if foreground else 0
        this_thread = win32.GetCurrentThreadId()
        attached = bool(foreground_thread) and foreground_thread != this_thread
        if attached:
            win32.AttachThreadInput(this_thread, foreground_thread, True)
        try:
            win32.SetForegroundWindow(hwnd)
        finally:
            if attached:
                win32.AttachThreadInput(this_thread, foreground_thread, False)
    except (OSError, tk.TclError) as exc:
        logger.debug("could not bring window to front: %s", exc)


def show_error(title: str, message: str) -> None:
    """Show a blocking error box (used when there is no console to print to)."""
    if sys.platform != "win32":
        return
    try:
        from scrawl import win32

        win32.MessageBoxW(wintypes.HWND(0), message, title, MB_ICONERROR)
    except OSError as exc:
        logger.debug("could not show error box: %s", exc)
