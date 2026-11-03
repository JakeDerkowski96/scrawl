# Architecture

## Shape of the program

```text
              +--------------------+
 hotkeys ---> |  shell thread      |--\
 tray clicks  |  (hidden window +  |   \   Command values
              |   message loop)    |    \
              +--------------------+     v
                                       queue.Queue ---> Tk main thread
              +--------------------+     ^              (MainWindow._poll
 `scrawl show`|  ipc thread        |    /                every 50 ms)
 `scrawl new` |  (loopback socket) |---/
              +--------------------+
```

Scrawl is one resident process. Two background threads receive outside events and the Tk main thread owns everything the user sees.

**Why a queue.** Tk is not thread-safe, and `RegisterHotKey` and tray callbacks are delivered to whichever thread created the window that registered them. So the shell thread owns its own hidden window and message loop, and never touches Tk; it only puts a `Command` (`show`, `new`, `toggle`, `quit`) on a queue. The main thread drains the queue on a 50 ms timer. All Tk calls stay on one thread, with no locks.

## Modules

| Module | Responsibility |
|---|---|
| `cli.py` | Argument parsing, logging setup, exit codes. No logic |
| `app.py` | Startup: single-instance check, start the shell, build the window, tear down |
| `store.py` | Notes as files: list, read, atomic write, trash. No Tk, no globals |
| `search.py` | Full-text search over the store |
| `checklist.py` | Pure functions for checkbox and list lines |
| `config.py` | `config.json` (user-edited) and `state.json` (app-managed) |
| `hotkeys.py` | Parses `ctrl+alt+n` into Win32 modifier and key codes |
| `shell.py`, `win32.py` | The Windows tray icon and hotkeys via ctypes. `win32.py` is only prototypes |
| `ipc.py` | Single-instance lock and remote commands over `127.0.0.1` |
| `winutil.py` | Best-effort Windows niceties: DPI, dark title bar, foreground focus |
| `autostart.py` | Per-user registry Run entry |
| `icon.py` | Draws the icon as PNG bytes in code, so no binary asset is committed |
| `ui/` | `window.py` (orchestration), `editor.py` (checkbox behavior), `sidebar.py`, `theme.py` |

The core (`store`, `search`, `checklist`, `config`, `hotkeys`) imports no UI and no Windows code, so it is fully unit-tested without a window. The UI can be replaced without touching storage.

## Single instance

Binding the loopback port is the lock. The first process to bind `127.0.0.1:47653` is the running instance; a later launch fails to bind, sends its request (`show` or `new`) to the first, and exits. The operating system releases the port when a process dies, so there is no stale lock file to clean up. On Windows the socket uses `SO_EXCLUSIVEADDRUSE` so nothing can share the port.

The listener only ever accepts four fixed command words and replies `scrawl ok`, which also lets a launcher distinguish Scrawl from an unrelated program squatting on the port. Any local process can send those commands. That is acceptable for a single-user notepad: the commands can show or close the window but can never read or change note content.

## Saving

- Writes are atomic: a temp file in the same folder, flushed to disk, then renamed over the target, so a crash never leaves a half-written note. The rename retries briefly because OneDrive's sync client can hold a file open.
- Autosave runs after a short pause in typing (`autosave_ms`), and also on switching notes, hiding the window, and quitting.
- A failed save keeps the text in the editor, shows `SAVE FAILED` in the status bar, and retries every 3 seconds.
- A new note is in memory only until it has content. An existing note that is emptied is removed when you leave it, but only after re-reading it to confirm it is blank.
- If the current note changes on disk while the window is hidden and you have not typed in it, it is reloaded on show. If you have unsaved typing, your text wins and is saved over the external change on the next autosave. There is no merge. Do not edit the same note in two places at once.

## Platform support

The notepad itself is portable Tk code. Hotkeys, the tray icon, and start-at-login are Windows-only and degrade gracefully elsewhere: the window opens, the status bar explains what is unavailable, and closing the window quits (hiding it would leave no way to get it back).

## Decisions

See [decisions/](decisions/) for why Python and Tkinter, why a resident process, and why plain files.
