# Troubleshooting

The log is the first place to look: `%APPDATA%\scrawl\scrawl.log` (run `scrawl config` to confirm the folder). Add `-v` to a command for debug output on the console.

## The hotkey does nothing

- **Status bar says `hotkey ... is unavailable`.** Another program already owns that combination. Choose a different one in `config.json` ([configuration](configuration.md)), then `scrawl quit` and start again.
- **No warning, still nothing.** Scrawl may not be running: look for the tray icon (check the overflow `^`), or run `scrawl show`. If that says it could not reach a running Scrawl, start it with `scrawl-gui`.
- **It works in most apps but not in one.** Windows does not deliver global hotkeys to windows running as administrator when Scrawl is not. Run Scrawl elevated, or use a different combination.

## `scrawl show` or `new` says it could not reach a running Scrawl

Nothing is listening on the configured port, so the app is not running. Start it with `scrawl` or `scrawl-gui`.

## `port 47653 is in use by another program (not Scrawl)`

Another program holds the port Scrawl uses to detect a running copy. Set `ipc_port` to a free port between 1024 and 65535 in `config.json`.

## The window appears behind other windows or without focus

Windows restricts which programs may take the foreground. Scrawl works around this when the hotkey is pressed, but a few full-screen or elevated programs still win. Click the taskbar button or the tray icon.

## Two copies seem to be running

Scrawl prevents this by design; a second launch just focuses the first. If you see two, one is probably running from a different config folder (`SCRAWL_CONFIG_DIR`) and therefore a different port.

## `SAVE FAILED` in the status bar

The notes folder could not be written (disk full, permissions, a sync client holding the file, the folder is on a drive that went away). Your text is still in the editor and Scrawl retries every 3 seconds. Fix the cause or copy the text out. The message includes the exact path and error.

## A note disappeared

Deleted notes are moved to `.trash\` in the notes folder, so look there first. The only thing Scrawl ever removes outright is a note that is completely blank.

## The config file is rejected at startup

The error names the file and the offending key or the line and column of a JSON syntax error. Fix it, or delete `config.json` to regenerate the defaults on next start.

## Text looks blurry on a high-DPI screen

Scrawl opts in to DPI awareness at startup. If it still looks soft, check the executable's Properties, Compatibility, High DPI settings and make sure scaling is not overridden.

## The tray icon vanished after Explorer restarted

Scrawl listens for Explorer's restart and re-adds the icon (this path is implemented but has not been tested on a real Explorer restart). If the icon does not come back, press Ctrl+Alt+J to reach the window, quit with Ctrl+Q, and start Scrawl again.
