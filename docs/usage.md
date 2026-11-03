# Usage

## Your notes

Each note is one Markdown file in the notes folder (default `~\Documents\Scrawl`; see [configuration](configuration.md)). The filename is a timestamp such as `20261031-142501.md` and never changes; the title shown in the sidebar is taken from the note's first line.

Because the notes are ordinary files, you can point the folder at OneDrive for sync and backup, open them in any editor, or search them with other tools. Scrawl re-reads the current note whenever you bring the window back, so edits made elsewhere show up, but only if you have no unsaved typing in that note (it never overwrites what you are writing).

A new note exists only in memory until it contains text, so opening "new note" and walking away leaves nothing behind. Deleting moves a note to `.trash\` inside the notes folder; nothing is ever permanently deleted except a note that is completely blank.

## Global hotkeys

| Default | Action |
|---|---|
| Ctrl+Alt+N | Show Scrawl with a fresh note, cursor ready |
| Ctrl+Alt+J | Show Scrawl, or hide it if it is already active |

Change them in `config.json`. If another program already owns a combination, Scrawl keeps running without it and shows a warning in the status bar.

## Window shortcuts

| Shortcut | Action |
|---|---|
| Ctrl+N | New note |
| Ctrl+F | Search (Enter opens the first result) |
| Ctrl+Enter | Toggle a checkbox on this line, or turn the line into one |
| Click `[ ]` | Toggle that checkbox |
| Enter | Continue a list; on an empty list item, end the list |
| Ctrl+Shift+Delete | Move the note to the trash folder |
| Ctrl+B | Show or hide the sidebar |
| Ctrl+T | Switch dark and light themes |
| Ctrl `+` / `-` / `0`, Ctrl+wheel | Zoom text in, out, reset |
| Esc, Ctrl+W | Hide the window (Scrawl keeps running in the tray) |
| Ctrl+Q | Quit |
| F1 | Show this list in the app |

Right-click a note in the sidebar to move it to the trash.

## Checklists

```text
- [ ] write the README
- [x] pick a name
```

Checked items are struck through and dimmed. Pressing Enter at the end of a list line starts the next item (`- [ ]` continues as `- [ ]`, `1.` as `2.`); pressing Enter on an empty item ends the list. Bullets (`- `, `* `, `+ `) and numbered items work the same way.

## Command line

| Command | What it does |
|---|---|
| `scrawl` / `scrawl run` | Start the app, or focus it if it is already running |
| `scrawl run --hidden` | Start in the tray with no window (what start-at-login uses) |
| `scrawl new` | Open a fresh note (starts the app if needed) |
| `scrawl show`, `scrawl quit` | Control the running app |
| `scrawl add "text"` | Create a note without opening the window; text can also be piped in |
| `scrawl list [-n N]` | Recent notes, newest first |
| `scrawl search WORDS...` | Notes containing every word, case-insensitive |
| `scrawl autostart enable\|disable\|status` | Start at login via the per-user registry Run key |
| `scrawl config` | Print the config location and the effective settings |

`--dry-run` on `add` and `autostart` reports what would change without changing it. `-v` adds debug detail on the console.
