"""Tests for the command-line interface (commands that never open a window)."""

import json
import sys
from pathlib import Path

import pytest

from scrawl import __version__, autostart
from scrawl.cli import main


@pytest.fixture
def notes_dir(isolated_config_dir: Path, tmp_path: Path) -> Path:
    """Configure a temp notes folder via config.json."""
    notes = tmp_path / "notes"
    isolated_config_dir.mkdir(parents=True, exist_ok=True)
    (isolated_config_dir / "config.json").write_text(
        json.dumps({"notes_dir": str(notes)}), encoding="utf-8"
    )
    return notes


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_add_creates_note(notes_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["add", "call", "the", "dentist"]) == 0
    files = list(notes_dir.glob("*.md"))
    assert len(files) == 1
    assert files[0].read_text(encoding="utf-8") == "call the dentist\n"
    assert "created" in capsys.readouterr().out


def test_add_dry_run_writes_nothing(notes_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["add", "--dry-run", "preview"]) == 0
    assert not notes_dir.exists()
    assert "would create" in capsys.readouterr().out


def test_dry_run_flag_works_before_the_subcommand(notes_dir: Path) -> None:
    assert main(["--dry-run", "add", "preview"]) == 0
    assert not notes_dir.exists()


def test_add_reads_stdin(
    notes_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import io

    class PipedInput(io.StringIO):
        def isatty(self) -> bool:
            return False

    monkeypatch.setattr(sys, "stdin", PipedInput("- [ ] from a pipe\n"))
    assert main(["add"]) == 0
    (note,) = notes_dir.glob("*.md")
    assert note.read_text(encoding="utf-8") == "- [ ] from a pipe\n"


def test_add_with_nothing_fails_cleanly(
    notes_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import io

    class PipedInput(io.StringIO):
        def isatty(self) -> bool:
            return False

    monkeypatch.setattr(sys, "stdin", PipedInput("   \n"))
    assert main(["add"]) == 1
    assert "empty" in capsys.readouterr().err
    assert not notes_dir.exists()


def test_list_and_search(notes_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["add", "Groceries: milk and eggs"])
    main(["add", "Ideas: new app"])
    capsys.readouterr()

    assert main(["list"]) == 0
    listing = capsys.readouterr().out
    assert "Groceries: milk and eggs" in listing
    assert "Ideas: new app" in listing

    assert main(["search", "milk"]) == 0
    found = capsys.readouterr().out
    assert "Groceries" in found
    assert "Ideas" not in found


def test_list_limit(notes_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    for text in ("one", "two", "three"):
        main(["add", text])
        # ids are second-granular; the store adds a suffix on collision.
    capsys.readouterr()
    main(["list", "-n", "2"])
    assert len(capsys.readouterr().out.strip().splitlines()) == 2


def test_config_command_prints_effective_settings(
    notes_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["config"]) == 0
    out = capsys.readouterr().out
    assert "config file:" in out
    assert "hotkey_new" in out


def test_invalid_config_is_reported_not_raised(
    isolated_config_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    isolated_config_dir.mkdir(parents=True, exist_ok=True)
    (isolated_config_dir / "config.json").write_text("{ broken", encoding="utf-8")
    assert main(["list"]) == 1
    assert "not valid JSON" in capsys.readouterr().err


def test_show_without_running_instance_reports_error(
    isolated_config_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    isolated_config_dir.mkdir(parents=True, exist_ok=True)
    # A port nothing listens on, so the failure path is exercised deterministically.
    (isolated_config_dir / "config.json").write_text(
        json.dumps({"ipc_port": 59999}), encoding="utf-8"
    )
    assert main(["show"]) == 1
    assert "could not reach" in capsys.readouterr().err


@pytest.mark.skipif(sys.platform != "win32", reason="autostart is Windows-only")
def test_autostart_dry_run_does_not_touch_registry(capsys: pytest.CaptureFixture[str]) -> None:
    was_enabled = autostart.is_enabled()
    assert main(["autostart", "enable", "--dry-run"]) == 0
    assert "would set" in capsys.readouterr().out
    assert autostart.is_enabled() is was_enabled


@pytest.mark.skipif(sys.platform != "win32", reason="autostart is Windows-only")
def test_autostart_command_line_launches_hidden() -> None:
    command = autostart.command_line()
    assert command.endswith("-m scrawl run --hidden")
    assert command.startswith('"')
