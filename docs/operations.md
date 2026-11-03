# Operations

## Development setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

If `pip` fails with `CERTIFICATE_VERIFY_FAILED`, you are likely behind a TLS-inspecting proxy whose certificate is trusted by Windows but not by pip. Make pip use the Windows certificate store (this keeps verification on):

```powershell
$env:PIP_USE_FEATURE = "truststore"
pip install -e ".[dev]"
```

## Checks

```powershell
ruff check .
ruff format --check .
mypy src
pytest
```

`pytest` includes `tests/test_window.py`, which drives the real Tk window (typing, autosave, checkboxes, search, delete, commands) without running its main loop. These need a desktop session that can create Tk windows and skip otherwise.

## Smoke test

```powershell
python scripts\smoke_test.py
```

Launches a real Scrawl process against a throwaway config and notes folder, then checks: hidden start, single instance, `scrawl show`, the toggle and new-note hotkeys (delivered as `WM_HOTKEY`), and a clean `scrawl quit`. If the desktop is unlocked and accepts synthetic input it also presses the real hotkeys, checks the window takes focus, and types into it. Otherwise it prints `SKIP` for those checks; a skip is not a pass.

## Manual checks before a release

These need a person at an unlocked desktop. Automated tests cannot see them.

- [ ] Press the real **Ctrl+Alt+N** while another app has focus: Scrawl appears in front, focused, with a blank note, and typing works immediately.
- [ ] Press **Ctrl+Alt+J** twice: the window hides, then shows again.
- [ ] The tray icon is visible (check the overflow `^` area) and looks right. Left-click shows the window; right-click shows the menu (Open, New note, Quit) and the menu dismisses when you click elsewhere.
- [ ] Close the window with X: it hides rather than quits. Quit from the tray menu: the process exits (`Get-Process python*` or Task Manager).
- [ ] Dark title bar and text are sharp, not blurry, on a high-DPI display. Switch themes with Ctrl+T.
- [ ] `scrawl autostart enable`, sign out and in: Scrawl starts hidden in the tray. Then `scrawl autostart disable`.
- [ ] With the notes folder under OneDrive: create a note, confirm it syncs, and that no stray `.tmp` files remain.
- [ ] Press a hotkey another program already owns: Scrawl still starts and the status bar shows the warning.

## Start at login

```powershell
scrawl autostart enable      # writes HKCU\...\Run\Scrawl
scrawl autostart status
scrawl autostart disable
```

The entry runs `pythonw.exe -m scrawl run --hidden` from the Python environment you ran the command in. If you move or delete that environment, run `disable` and `enable` again from the new one.

## Stopping Scrawl

`scrawl quit`, the tray menu's Quit, or Ctrl+Q in the window. Each saves first.

## Releasing

1. Update `CHANGELOG.md` and bump `version` in `pyproject.toml` and `src/scrawl/__init__.py`.
2. Merge to `main` through a pull request.
3. Tag an annotated release: `git tag -a v0.1.0 -m "v0.1.0"`, then push the tag.
