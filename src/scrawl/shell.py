"""The resident Windows shell: global hotkeys and the system tray icon.

Required permissions: none. Hotkeys are registered with ``RegisterHotKey``
(per-user, no elevation, no keyboard hook, nothing that reads other keystrokes).

Usage:
    shell = ShellThread({Command.NEW: parse_hotkey("ctrl+alt+n")}, events)
    warnings = shell.start()      # e.g. ["ctrl+alt+n is already in use"]
    ...
    shell.stop()

Notes:
    All of this runs on its own thread with its own hidden window and message
    loop, because ``RegisterHotKey`` and tray callbacks are delivered to the
    thread that created the window. Tk is not thread-safe, so the thread never
    touches Tk: it only puts ``Command`` values on a queue that the Tk main
    thread polls.
"""

import ctypes
import logging
import queue
import threading
from collections.abc import Mapping
from ctypes import wintypes

from scrawl import icon, win32
from scrawl.commands import Command
from scrawl.exceptions import ShellError
from scrawl.hotkeys import MOD_NOREPEAT, Hotkey

logger = logging.getLogger(__name__)

_CLASS_NAME = "ScrawlShellWindow"
_TRAY_ICON_ID = 1
_WM_TRAY = win32.WM_APP + 1
_START_TIMEOUT_S = 5.0

_MENU_SHOW = 1
_MENU_NEW = 2
_MENU_QUIT = 3
_ICON_VERSION = 0x00030000


class ShellThread:
    """Owns the hidden message window, hotkey registrations, and tray icon."""

    def __init__(
        self,
        hotkeys: Mapping[Command, Hotkey],
        events: "queue.Queue[Command]",
        *,
        tooltip: str = "Scrawl",
    ) -> None:
        self._hotkeys = dict(hotkeys)
        self._events = events
        self._tooltip = tooltip
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._startup_error: BaseException | None = None
        self._hwnd: int | None = None
        self._hicon: int | None = None
        self._hotkey_ids: dict[int, Command] = {}
        self._taskbar_created = 0
        # Held so the C callback is not garbage collected while Windows can call it.
        self._wndproc_ref = win32.WNDPROC(self._wndproc)
        self.warnings: list[str] = []
        self.tray_available = False

    @property
    def hotkeys_registered(self) -> int:
        """How many hotkeys Windows accepted."""
        return len(self._hotkey_ids)

    def start(self, timeout: float = _START_TIMEOUT_S) -> list[str]:
        """Start the thread and wait until hotkeys and tray are set up.

        Returns:
            Human-readable warnings for anything that could not be registered
            (hotkey already taken, no tray). The app still runs without them.

        Raises:
            ShellError: If the hidden window itself could not be created.
        """
        self._thread = threading.Thread(target=self._run, name="scrawl-shell", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout):
            raise ShellError("timed out starting the tray/hotkey shell")
        if self._startup_error is not None:
            raise ShellError(f"could not start the tray/hotkey shell: {self._startup_error}")
        return list(self.warnings)

    def stop(self) -> None:
        """Remove the tray icon and hotkeys, and end the thread."""
        if self._thread is None or not self._thread.is_alive() or self._hwnd is None:
            return
        win32.PostMessageW(self._hwnd, win32.WM_CLOSE, 0, 0)
        self._thread.join(timeout=3)

    def _run(self) -> None:
        """Thread body: build the window, then pump messages until closed."""
        try:
            self._create_window()
            self._register_hotkeys()
            self._add_tray_icon()
        except OSError as exc:
            self._startup_error = exc
            self._ready.set()
            self._cleanup()
            return
        self._ready.set()

        msg = wintypes.MSG()
        while True:
            result = win32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if result in (0, -1):  # WM_QUIT, or an error that makes looping pointless
                break
            win32.TranslateMessage(ctypes.byref(msg))
            win32.DispatchMessageW(ctypes.byref(msg))
        self._cleanup()

    def _create_window(self) -> None:
        """Register the window class and create the (never shown) window."""
        instance = win32.GetModuleHandleW(None)
        wndclass = win32.WNDCLASSW()
        wndclass.lpfnWndProc = self._wndproc_ref
        wndclass.hInstance = instance
        wndclass.lpszClassName = _CLASS_NAME
        if not win32.RegisterClassW(ctypes.byref(wndclass)):
            raise ctypes.WinError(ctypes.get_last_error())
        # A normal top-level window (not message-only) is required to receive
        # the broadcast "TaskbarCreated" message used to restore the tray icon.
        hwnd = win32.CreateWindowExW(
            0, _CLASS_NAME, "Scrawl shell", 0, 0, 0, 0, 0, None, None, instance, None
        )
        if not hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        self._hwnd = int(hwnd)
        self._taskbar_created = win32.RegisterWindowMessageW("TaskbarCreated")

    def _register_hotkeys(self) -> None:
        """Register each hotkey, recording a warning for any that fail."""
        for hotkey_id, (command, hotkey) in enumerate(self._hotkeys.items(), start=1):
            ok = win32.RegisterHotKey(
                self._hwnd, hotkey_id, hotkey.modifiers | MOD_NOREPEAT, hotkey.vk
            )
            if ok:
                self._hotkey_ids[hotkey_id] = command
                logger.info("registered hotkey %s for %s", hotkey.text, command.value)
            else:
                error = ctypes.WinError(ctypes.get_last_error())
                message = f"hotkey {hotkey.text} is unavailable ({error.strerror}); change it in config.json"
                logger.warning(message)
                self.warnings.append(message)

    def _add_tray_icon(self) -> None:
        """Create the tray icon; failure is a warning, not fatal."""
        self._hicon = self._make_icon()
        if not win32.Shell_NotifyIconW(win32.NIM_ADD, ctypes.byref(self._notify_data())):
            message = "could not add the tray icon; closing the window will quit the app"
            logger.warning(message)
            self.warnings.append(message)
            return
        self.tray_available = True

    def _notify_data(self) -> win32.NOTIFYICONDATAW:
        """Build the tray icon description."""
        data = win32.NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(win32.NOTIFYICONDATAW)
        data.hWnd = self._hwnd
        data.uID = _TRAY_ICON_ID
        data.uFlags = win32.NIF_MESSAGE | win32.NIF_ICON | win32.NIF_TIP
        data.uCallbackMessage = _WM_TRAY
        data.hIcon = self._hicon
        data.szTip = self._tooltip
        return data

    def _make_icon(self) -> int | None:
        """Create the tray HICON from the generated PNG, falling back to a stock icon."""
        size = win32.GetSystemMetrics(win32.SM_CXSMICON) or 16
        png = icon.png_bytes(size)
        handle = win32.CreateIconFromResourceEx(
            png, len(png), True, _ICON_VERSION, size, size, win32.LR_DEFAULTCOLOR
        )
        if handle:
            return int(handle)
        logger.warning("could not build the tray icon; using the stock application icon")
        stock = win32.LoadIconW(None, win32.IDI_APPLICATION)
        return int(stock) if stock else None

    def _cleanup(self) -> None:
        """Release hotkeys, the tray icon, and the window."""
        if self._hwnd is not None:
            for hotkey_id in self._hotkey_ids:
                win32.UnregisterHotKey(self._hwnd, hotkey_id)
            if self.tray_available:
                win32.Shell_NotifyIconW(win32.NIM_DELETE, ctypes.byref(self._notify_data()))
                self.tray_available = False
        if self._hicon:
            win32.DestroyIcon(self._hicon)
            self._hicon = None

    def _wndproc(
        self, hwnd: int, msg: int, wparam: int, lparam: int
    ) -> int:  # called by Windows on the shell thread
        """Handle messages for the hidden window."""
        try:
            if msg == win32.WM_HOTKEY:
                command = self._hotkey_ids.get(wparam)
                if command is not None:
                    self._events.put(command)
                return 0
            if msg == _WM_TRAY:
                self._on_tray_event(lparam & 0xFFFF)
                return 0
            if msg == self._taskbar_created and self._taskbar_created:
                # Explorer restarted and the tray was rebuilt; add the icon back.
                self.tray_available = False
                self._add_tray_icon()
                return 0
            if msg == win32.WM_CLOSE:
                win32.DestroyWindow(hwnd)
                return 0
            if msg == win32.WM_DESTROY:
                win32.PostQuitMessage(0)
                return 0
        except Exception:
            # An exception escaping a C callback is printed and dropped by
            # ctypes; log it properly so a tray bug is diagnosable.
            logger.exception("error handling window message 0x%04X", msg)
        return int(win32.DefWindowProcW(hwnd, msg, wparam, lparam))

    def _on_tray_event(self, mouse_message: int) -> None:
        """React to a click on the tray icon."""
        if mouse_message == win32.WM_LBUTTONUP:
            self._events.put(Command.SHOW)
        elif mouse_message == win32.WM_RBUTTONUP:
            self._show_menu()

    def _show_menu(self) -> None:
        """Pop up the tray context menu and queue the chosen command."""
        menu = win32.CreatePopupMenu()
        new_hotkey = self._hotkey_for(Command.NEW)
        new_label = f"New note\t{new_hotkey}" if new_hotkey else "New note"
        win32.AppendMenuW(menu, win32.MF_STRING, _MENU_SHOW, "Open Scrawl")
        win32.AppendMenuW(menu, win32.MF_STRING, _MENU_NEW, new_label)
        win32.AppendMenuW(menu, win32.MF_SEPARATOR, 0, None)
        win32.AppendMenuW(menu, win32.MF_STRING, _MENU_QUIT, "Quit")

        point = wintypes.POINT()
        win32.GetCursorPos(ctypes.byref(point))
        # The menu only dismisses on an outside click if our window is foreground.
        win32.SetForegroundWindow(self._hwnd)
        choice = win32.TrackPopupMenu(
            menu,
            win32.TPM_RETURNCMD | win32.TPM_NONOTIFY | win32.TPM_RIGHTBUTTON,
            point.x,
            point.y,
            0,
            self._hwnd,
            None,
        )
        # Documented workaround so the menu closes correctly on later clicks.
        win32.PostMessageW(self._hwnd, win32.WM_NULL, 0, 0)
        win32.DestroyMenu(menu)

        chosen = {_MENU_SHOW: Command.SHOW, _MENU_NEW: Command.NEW, _MENU_QUIT: Command.QUIT}
        if choice in chosen:
            self._events.put(chosen[choice])

    def _hotkey_for(self, command: Command) -> str | None:
        """Return the display text of the hotkey bound to ``command``."""
        hotkey = self._hotkeys.get(command)
        if hotkey is None:
            return None
        return "+".join(part.capitalize() for part in hotkey.text.split("+"))
