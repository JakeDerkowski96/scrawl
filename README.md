# Scrawl

A tiny, fast notepad for brain dumps, ideas, and to-do lists. It lives in your system tray, and one global hotkey drops you into a fresh note from anywhere. Notes are plain Markdown files in a folder you choose, with no database, no account, and no runtime dependencies beyond Python itself.

## Purpose

Most note apps are heavy, slow to open, or lock your notes into their own format. Scrawl does a handful of things well: capture a thought in under a second, keep a checklist, find it again later, and never lose text. If you can open the folder in any editor and read your notes, Scrawl has done its job.

## What's here

```text
src/scrawl/     the application (core logic, Windows tray/hotkey shell, Tk UI)
tests/          unit tests, plus Tk window behavior tests
scripts/        smoke_test.py: end-to-end check of the real app
docs/           architecture, configuration, usage, operations, troubleshooting, ADRs
```

## Prerequisites

- Windows 10 or 11 (global hotkeys and the tray icon are Windows-only; the notepad itself runs elsewhere)
- Python 3.11 or newer with Tkinter (included in the standard python.org installer)

## Required permissions

| Role | Scope | Reason |
|---|---|---|
| None (standard user, no elevation) | Notes folder (default `~\Documents\Scrawl`) | Read and write note files |
| None | `%APPDATA%\scrawl` | Read and write config, state, and the log file |
| None | `127.0.0.1` loopback port 47653 (configurable) | Single-instance check and `scrawl show/new/quit` |
| None | `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` | Only if you run `scrawl autostart enable` |

Scrawl never needs administrator rights, never listens on the network, and registers hotkeys with `RegisterHotKey` rather than a keyboard hook, so it cannot see your other keystrokes.

## Usage

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

scrawl                  # start (or focus) the app
scrawl-gui              # same, but with no console window
```

Then press **Ctrl+Alt+N** from any application for a new note, or **Ctrl+Alt+J** to show or hide the window. Closing the window hides it to the tray; **Ctrl+Q** or the tray menu quits.

Checklists: type `- [ ] thing`, press **Ctrl+Enter** on any line to toggle it, or click the `[ ]`. **F1** lists every shortcut.

From a terminal:

```powershell
scrawl add "call the dentist"      # create a note without opening the window
"idea" | scrawl add                # ...or from a pipe
scrawl search milk eggs            # notes containing both words
scrawl autostart enable            # start quietly in the tray at login
```

Every state-changing command accepts `--dry-run`, and every command accepts `-v/--verbose`.

## Documentation

See [docs/README.md](docs/README.md) for the index: [usage](docs/usage.md), [configuration](docs/configuration.md), [architecture](docs/architecture.md), [operations and testing](docs/operations.md), [troubleshooting](docs/troubleshooting.md), and the [decision records](docs/decisions/).

## Contributing

Work happens on short-lived branches named `<type>/<short-description>` (for example `feat/note-pinning`), with [Conventional Commits](https://www.conventionalcommits.org/) messages, and merges to `main` by squash through a pull request. Before opening one:

```powershell
ruff check . ; ruff format --check . ; mypy src ; pytest
python scripts\smoke_test.py
```

## License

[MIT](LICENSE)
