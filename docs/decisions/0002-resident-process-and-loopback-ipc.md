# 0002. Resident process, with a loopback socket for single-instance and control

Status: Accepted

## Context

A global hotkey requires something alive to hear it while another application has focus. Scrawl therefore stays running in the tray, and later launches (`scrawl new`, a taskbar shortcut, start-at-login) must reach that process rather than start a second one.

## Options considered

For the single-instance lock and remote commands:

1. **Loopback TCP socket on a fixed port.** Binding the port is the lock; the OS releases it on process death; the same channel carries commands.
2. **Named mutex plus a named pipe.** Native and not network-visible, but needs more `ctypes` and does not work cross-platform.
3. **Lock file.** Simple, but goes stale after a crash and needs liveness checks.

For hotkeys: Win32 `RegisterHotKey` versus a low-level keyboard hook (`pynput`, `keyboard`).

## Decision

- A loopback socket bound to `127.0.0.1` with `SO_EXCLUSIVEADDRUSE`, accepting only four fixed command words and replying `scrawl ok`.
- `RegisterHotKey` on a dedicated shell thread with its own hidden window, which also hosts the tray icon.
- All outside events become `Command` values on a `queue.Queue` that the Tk main thread polls.

## Consequences

- No stale lock files, no extra dependencies, and the same code path serves "second launch" and `scrawl show|new|quit`.
- Any local process can show, hide, or quit the window. Accepted for a single-user desktop tool; the channel can never read or change note content and is not reachable from the network.
- The port can collide with another program. This is detected (the reply must be `scrawl ok`), reported clearly, and fixable via `ipc_port`.
- `RegisterHotKey` cannot observe other keystrokes, unlike a keyboard hook, and does not trigger antivirus heuristics. The cost is that a combination another program already owns cannot be registered; this is reported rather than fatal.
- Threading stays simple: Tk is only ever touched from one thread.
