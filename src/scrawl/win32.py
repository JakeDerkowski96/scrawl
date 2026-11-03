"""Raw ctypes bindings for the handful of Win32 calls Scrawl needs.

Required permissions: none (user-session APIs only; no elevation).

Notes:
    Importable on Windows only. Every function gets explicit ``argtypes`` and
    ``restype``: ctypes' defaults truncate 64-bit handles and pointers to 32-bit
    ints, which crashes or silently misbehaves on 64-bit Python.
"""

import ctypes
from ctypes import wintypes
from typing import Any

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)

# Window messages
WM_NULL = 0x0000
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_HOTKEY = 0x0312
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_APP = 0x8000

# Shell_NotifyIcon
NIM_ADD = 0
NIM_MODIFY = 1
NIM_DELETE = 2
NIF_MESSAGE = 0x1
NIF_ICON = 0x2
NIF_TIP = 0x4

# Popup menus
MF_STRING = 0x0
MF_SEPARATOR = 0x800
TPM_RIGHTBUTTON = 0x2
TPM_NONOTIFY = 0x80
TPM_RETURNCMD = 0x100

# Misc
SM_CXSMICON = 49
LR_DEFAULTCOLOR = 0
IDI_APPLICATION = 32512
DWMWA_USE_IMMERSIVE_DARK_MODE = 20


class WNDCLASSW(ctypes.Structure):
    """Window class registration record."""

    _fields_ = (
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    )


class GUID(ctypes.Structure):
    """Globally unique identifier (only present to size NOTIFYICONDATAW)."""

    _fields_ = (
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    )


class NOTIFYICONDATAW(ctypes.Structure):
    """Tray icon description."""

    _fields_ = (
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    )


def _bind(func: Any, argtypes: list[Any], restype: Any) -> Any:
    """Set a function's prototype and return it."""
    func.argtypes = argtypes
    func.restype = restype
    return func


DefWindowProcW = _bind(
    user32.DefWindowProcW,
    [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM],
    LRESULT,
)
RegisterClassW = _bind(user32.RegisterClassW, [ctypes.POINTER(WNDCLASSW)], wintypes.ATOM)
UnregisterClassW = _bind(
    user32.UnregisterClassW, [wintypes.LPCWSTR, wintypes.HINSTANCE], wintypes.BOOL
)
CreateWindowExW = _bind(
    user32.CreateWindowExW,
    [
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        wintypes.HMENU,
        wintypes.HINSTANCE,
        wintypes.LPVOID,
    ],
    wintypes.HWND,
)
DestroyWindow = _bind(user32.DestroyWindow, [wintypes.HWND], wintypes.BOOL)
GetMessageW = _bind(
    user32.GetMessageW,
    [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT],
    ctypes.c_int,
)
TranslateMessage = _bind(user32.TranslateMessage, [ctypes.POINTER(wintypes.MSG)], wintypes.BOOL)
DispatchMessageW = _bind(user32.DispatchMessageW, [ctypes.POINTER(wintypes.MSG)], LRESULT)
PostMessageW = _bind(
    user32.PostMessageW,
    [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM],
    wintypes.BOOL,
)
PostQuitMessage = _bind(user32.PostQuitMessage, [ctypes.c_int], None)
RegisterHotKey = _bind(
    user32.RegisterHotKey,
    [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT],
    wintypes.BOOL,
)
UnregisterHotKey = _bind(user32.UnregisterHotKey, [wintypes.HWND, ctypes.c_int], wintypes.BOOL)
RegisterWindowMessageW = _bind(user32.RegisterWindowMessageW, [wintypes.LPCWSTR], wintypes.UINT)
CreatePopupMenu = _bind(user32.CreatePopupMenu, [], wintypes.HMENU)
AppendMenuW = _bind(
    user32.AppendMenuW,
    [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR],
    wintypes.BOOL,
)
TrackPopupMenu = _bind(
    user32.TrackPopupMenu,
    [
        wintypes.HMENU,
        wintypes.UINT,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        ctypes.c_void_p,
    ],
    wintypes.BOOL,
)
DestroyMenu = _bind(user32.DestroyMenu, [wintypes.HMENU], wintypes.BOOL)
GetCursorPos = _bind(user32.GetCursorPos, [ctypes.POINTER(wintypes.POINT)], wintypes.BOOL)
SetForegroundWindow = _bind(user32.SetForegroundWindow, [wintypes.HWND], wintypes.BOOL)
GetForegroundWindow = _bind(user32.GetForegroundWindow, [], wintypes.HWND)
GetParent = _bind(user32.GetParent, [wintypes.HWND], wintypes.HWND)
GetWindowThreadProcessId = _bind(
    user32.GetWindowThreadProcessId,
    [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)],
    wintypes.DWORD,
)
AttachThreadInput = _bind(
    user32.AttachThreadInput, [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL], wintypes.BOOL
)
GetSystemMetrics = _bind(user32.GetSystemMetrics, [ctypes.c_int], ctypes.c_int)
CreateIconFromResourceEx = _bind(
    user32.CreateIconFromResourceEx,
    [
        ctypes.c_char_p,
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ],
    wintypes.HICON,
)
LoadIconW = _bind(user32.LoadIconW, [wintypes.HINSTANCE, ctypes.c_void_p], wintypes.HICON)
DestroyIcon = _bind(user32.DestroyIcon, [wintypes.HICON], wintypes.BOOL)
MessageBoxW = _bind(
    user32.MessageBoxW,
    [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT],
    ctypes.c_int,
)
Shell_NotifyIconW = _bind(
    shell32.Shell_NotifyIconW, [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)], wintypes.BOOL
)
GetModuleHandleW = _bind(kernel32.GetModuleHandleW, [wintypes.LPCWSTR], wintypes.HMODULE)
GetCurrentThreadId = _bind(kernel32.GetCurrentThreadId, [], wintypes.DWORD)
DwmSetWindowAttribute = _bind(
    dwmapi.DwmSetWindowAttribute,
    [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD],
    ctypes.c_long,
)
