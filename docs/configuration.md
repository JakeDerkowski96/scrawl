# Configuration

Scrawl keeps three small files in its config folder, `%APPDATA%\scrawl` by default. Set the environment variable `SCRAWL_CONFIG_DIR` to use a different folder (the tests do this so they never touch your real settings). Run `scrawl config` to see the exact path.

| File | Purpose | Edit by hand? |
|---|---|---|
| `config.json` | Your settings (below) | Yes. Created with defaults on first run |
| `state.json` | Theme, window position, zoom, last note | No. Safe to delete |
| `scrawl.log` | Rotating log (256 KB, 2 backups) | Read it when troubleshooting |

## config.json

```json
{
  "notes_dir": "C:\\Users\\you\\Documents\\Scrawl",
  "hotkey_new": "ctrl+alt+n",
  "hotkey_toggle": "ctrl+alt+j",
  "ipc_port": 47653,
  "close_to_tray": true,
  "font_family": "Consolas",
  "font_size": 12,
  "autosave_ms": 700
}
```

Restart Scrawl (`scrawl quit`, then start it again) after editing. Any key you omit uses its default; unknown keys are ignored with a log warning; an invalid value stops startup with a message naming the file and the key.

| Setting | Meaning | Allowed |
|---|---|---|
| `notes_dir` | Folder holding the notes. `~` and `%ENV_VARS%` are expanded. Point it at a OneDrive folder for sync | Any path |
| `hotkey_new` | Show Scrawl with a fresh note | `modifier+...+key`; see below |
| `hotkey_toggle` | Show or hide Scrawl | Same, and must differ from `hotkey_new` |
| `ipc_port` | Loopback port used to detect a running instance. Change it only if another program uses 47653 | 1024-65535 |
| `close_to_tray` | `true`: the close button hides to the tray. `false`: it quits | `true` / `false` |
| `font_family`, `font_size` | Editor font. Zoom (Ctrl +/-) overrides the size and is remembered in `state.json` | Size 6-72 |
| `autosave_ms` | Pause after typing before a save | 100-10000 |

### Hotkey syntax

One or more modifiers plus exactly one key, joined by `+`, case-insensitive: `ctrl+alt+n`, `win+shift+space`, `ctrl+alt+f9`.

- Modifiers: `ctrl` (or `control`), `alt`, `shift`, `win` (or `super`, `meta`)
- Keys: letters, digits, `f1`-`f24`, `space`, `enter`, `tab`, `esc`, `backspace`, `insert`, `delete`, `home`, `end`, `pageup`, `pagedown`, the arrow keys, and `; = , - . / ` [ \ ] '`
- At least one modifier is required, because a bare key registered globally would be stolen from every application.

If Windows refuses a combination (another program owns it), Scrawl keeps running without that hotkey, logs a warning, and shows it in the status bar. Pick a different combination and restart.
