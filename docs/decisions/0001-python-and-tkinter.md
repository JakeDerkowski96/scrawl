# 0001. Python and Tkinter

Status: Accepted

## Context

Scrawl must be as lightweight as possible while covering the basics: autosave, multiple notes, checklists, search, and a global hotkey. It is a personal Windows tool, written by someone who already works in Python with an established toolchain.

## Options considered

1. **Python + Tkinter.** No dependencies (Tkinter ships with CPython), starts quickly, small idle memory, fits the existing Python tooling and tests.
2. **C# WinForms/WPF.** The most native: a single small `.exe`, faster cold start, simpler Win32 hotkey and tray APIs, native text-box behavior and DPI handling.
3. **Tauri (Rust + web UI).** Small and modern, but a heavier toolchain and more effort than a notepad warrants.
4. **Electron.** Rejected outright; it contradicts the lightweight goal.

## Decision

Python and Tkinter, with the core logic kept free of UI imports.

## Consequences

- No runtime dependencies. Hotkeys, the tray icon, DPI awareness, and the dark title bar are done with `ctypes` against stable Win32 APIs, which is more code than C# would need and has to be careful about 64-bit handle types.
- Distribution is "install Python, `pip install`", not a standalone `.exe`. Acceptable for personal use. If the app is ever shared widely, PyInstaller or a C# rewrite of the UI layer is the follow-up.
- Because `store`, `search`, `checklist`, `config`, and `hotkeys` are UI-free, replacing the UI later does not touch storage or behavior.
- Tkinter's `Text` widget is adequate for plain text and Markdown-style checklists but not for rich text, which is an explicit non-goal.
