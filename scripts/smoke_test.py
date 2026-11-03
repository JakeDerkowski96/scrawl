"""End-to-end smoke test of the real app: tray/hotkey shell, IPC, and window.

Purpose:
    Unit tests cannot cover the Win32 shell or real window focus. This script
    launches an actual Scrawl process in a throwaway config and notes folder,
    then drives it the way a user would.

Required permissions:
    None. Runs as the current user, binds a random loopback port, and writes
    only under a temp folder. It never touches your real notes or settings.

Usage:
    .venv\\Scripts\\python scripts\\smoke_test.py

Prerequisites:
    Windows, with scrawl installed in the interpreter that runs this script.

Notes:
    * Hotkeys are tested twice: by posting ``WM_HOTKEY`` to the shell window
      (always possible), and with real injected keystrokes (only when the
      desktop is unlocked and accepts synthetic input; otherwise skipped and
      reported as such, never counted as a pass).
    * Real keystrokes use obscure Ctrl+Alt+Shift+F9/F10 combinations. Text is
      only typed after confirming a Scrawl window has focus, so it can never
      land in another application.
"""

import ctypes
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from ctypes import wintypes
from pathlib import Path

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.IsWindowVisible.argtypes = [wintypes.HWND]

WM_HOTKEY = 0x0312
# Hotkey ids follow registration order in scrawl.app._start_shell.
HOTKEY_NEW, HOTKEY_TOGGLE = 1, 2
VK_CTRL, VK_ALT, VK_SHIFT, VK_F9, VK_F10, VK_F13 = 0x11, 0x12, 0x10, 0x78, 0x79, 0x7C


def window_title(hwnd: int | None) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buffer, 256)
    return buffer.value


def window_class(hwnd: int | None) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buffer, 256)
    return buffer.value


def scrawl_windows() -> list[tuple[str, bool]]:
    """Return (title, visible) for each top-level Scrawl window.

    Matches Tk's window class as well as the title, so an unrelated window
    that merely ends in "Scrawl" (such as an Explorer window on a folder of
    that name) cannot confuse the checks.
    """
    found: list[tuple[str, bool]] = []

    @WNDENUMPROC
    def collect(hwnd: int, _lparam: int) -> bool:
        title = window_title(hwnd)
        if title.endswith("Scrawl") and window_class(hwnd) == "TkTopLevel":
            found.append((title, bool(user32.IsWindowVisible(hwnd))))
        return True

    user32.EnumWindows(collect, 0)
    return found


def any_visible() -> bool:
    return any(visible for _, visible in scrawl_windows())


def post_hotkey(hotkey_id: int) -> None:
    """Deliver WM_HOTKEY to the shell window exactly as Windows would."""
    hwnd = user32.FindWindowW("ScrawlShellWindow", None)
    if not hwnd:
        raise RuntimeError("shell window not found")
    user32.PostMessageW(hwnd, WM_HOTKEY, hotkey_id, 0)


def press(*keys: int) -> None:
    for key in keys:
        user32.keybd_event(key, 0, 0, 0)
    time.sleep(0.05)
    for key in reversed(keys):
        user32.keybd_event(key, 0, 2, 0)


def input_injection_works() -> bool:
    """True if synthetic key presses register (false on a locked session)."""
    user32.keybd_event(VK_F13, 0, 0, 0)
    time.sleep(0.05)
    registered = bool(user32.GetAsyncKeyState(VK_F13) & 0x8000)
    user32.keybd_event(VK_F13, 0, 2, 0)
    return registered


def wait_for(predicate: Callable[[], object], timeout: float = 8.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return False


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def port_open(port: int) -> bool:
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="scrawl-smoke-"))
    config_dir, notes = root / "cfg", root / "notes"
    config_dir.mkdir()
    port = free_port()
    (config_dir / "config.json").write_text(
        json.dumps(
            {
                "notes_dir": str(notes),
                "ipc_port": port,
                "hotkey_new": "ctrl+alt+shift+f9",
                "hotkey_toggle": "ctrl+alt+shift+f10",
            }
        ),
        encoding="utf-8",
    )
    env = {**os.environ, "SCRAWL_CONFIG_DIR": str(config_dir)}
    scrawl = [sys.executable, "-m", "scrawl"]
    results: list[tuple[str, bool]] = []

    def check(name: str, passed: bool) -> None:
        results.append((name, passed))
        print(f"{'PASS' if passed else 'FAIL'}  {name}")

    proc = subprocess.Popen([*scrawl, "run", "--hidden"], env=env)  # noqa: S603
    try:
        check("app starts and listens", wait_for(lambda: port_open(port)))
        time.sleep(1.0)
        check("hidden start shows no window", not any_visible())

        check(
            "`scrawl show` forwards to the running app",
            subprocess.run([*scrawl, "show"], env=env).returncode == 0  # noqa: S603
            and wait_for(any_visible),
        )
        check(
            "a second `run` does not start a second app",
            subprocess.run([*scrawl, "run"], env=env, timeout=15).returncode == 0,
        )  # noqa: S603

        post_hotkey(HOTKEY_TOGGLE)
        check("toggle hotkey (WM_HOTKEY) hides the window", wait_for(lambda: not any_visible()))
        post_hotkey(HOTKEY_TOGGLE)
        check("toggle hotkey (WM_HOTKEY) shows the window", wait_for(any_visible))
        post_hotkey(HOTKEY_NEW)
        check("new-note hotkey (WM_HOTKEY) shows the window", wait_for(any_visible))

        if input_injection_works():
            press(VK_CTRL, VK_ALT, VK_SHIFT, VK_F10)
            check("REAL keystroke hides the window", wait_for(lambda: not any_visible()))
            press(VK_CTRL, VK_ALT, VK_SHIFT, VK_F9)
            check("REAL keystroke shows a new note", wait_for(any_visible))
            time.sleep(0.4)
            focused = window_title(user32.GetForegroundWindow()).endswith("Scrawl")
            check("window takes focus after the hotkey", focused)
            if focused:
                for char in "smoke":
                    press(ord(char.upper()))
                check(
                    "typed text is autosaved to a file",
                    wait_for(
                        lambda: (
                            notes.exists()
                            and any(
                                p.read_text(encoding="utf-8").lower() == "smoke"
                                for p in notes.glob("*.md")
                            )
                        )
                    ),
                )
        else:
            print(
                "SKIP  real keystroke, focus, and typing checks "
                "(session is locked or does not accept synthetic input)"
            )

        check("`scrawl quit` succeeds", subprocess.run([*scrawl, "quit"], env=env).returncode == 0)  # noqa: S603
        try:
            check("app exits cleanly", proc.wait(timeout=10) == 0)
        except subprocess.TimeoutExpired:
            check("app exits cleanly", False)
    finally:
        if proc.poll() is None:
            proc.kill()

    failed = [name for name, passed in results if not passed]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        log = config_dir / "scrawl.log"
        print(f"--- {log} ---")
        print(log.read_text(encoding="utf-8") if log.exists() else "(no log)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
