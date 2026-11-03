"""Tests for config and state loading."""

import json
from pathlib import Path

import pytest

from scrawl.config import (
    DEFAULT_IPC_PORT,
    State,
    config_dir,
    default_notes_dir,
    load_config,
    load_state,
    save_state,
)
from scrawl.exceptions import ConfigurationError


def _write(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_config_dir_honors_env_override(isolated_config_dir: Path) -> None:
    assert config_dir() == isolated_config_dir


def test_missing_config_gives_defaults_without_writing(isolated_config_dir: Path) -> None:
    config = load_config()
    assert config.notes_dir == default_notes_dir()
    assert config.ipc_port == DEFAULT_IPC_PORT
    assert not (isolated_config_dir / "config.json").exists()


def test_write_defaults_creates_editable_file(isolated_config_dir: Path) -> None:
    load_config(write_defaults=True)
    written = json.loads((isolated_config_dir / "config.json").read_text(encoding="utf-8"))
    assert written["hotkey_new"] == "ctrl+alt+n"
    # A second load reads the file we just wrote.
    assert load_config().hotkey_new == "ctrl+alt+n"


def test_partial_config_merges_over_defaults(tmp_path: Path) -> None:
    path = _write(tmp_path / "c.json", {"font_size": 15, "notes_dir": str(tmp_path / "n")})
    config = load_config(path)
    assert config.font_size == 15
    assert config.notes_dir == tmp_path / "n"
    assert config.hotkey_toggle == "ctrl+alt+j"


def test_notes_dir_expands_environment_variables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SCRAWL_TEST_ROOT", str(tmp_path))
    path = _write(tmp_path / "c.json", {"notes_dir": "%SCRAWL_TEST_ROOT%/notes"})
    assert load_config(path).notes_dir.name == "notes"


def test_invalid_json_names_file_and_position(tmp_path: Path) -> None:
    path = tmp_path / "c.json"
    path.write_text("{ nope", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="not valid JSON"):
        load_config(path)


def test_non_object_json_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="JSON object"):
        load_config(_write(tmp_path / "c.json", [1, 2]))


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("font_size", "big", "must be int"),
        ("font_size", True, "must be int"),
        ("font_size", 2, "6-72"),
        ("ipc_port", 80, "1024-65535"),
        ("autosave_ms", 5, "100-10000"),
        ("close_to_tray", "yes", "must be bool"),
        ("hotkey_new", "n", "at least one modifier"),
        ("hotkey_new", "ctrl+alt+j", "must differ"),
    ],
)
def test_invalid_values_are_rejected(tmp_path: Path, key: str, value: object, message: str) -> None:
    path = _write(tmp_path / "c.json", {key: value})
    with pytest.raises(ConfigurationError, match=message):
        load_config(path)


def test_unknown_keys_are_ignored(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = _write(tmp_path / "c.json", {"mystery": 1})
    load_config(path)
    assert "mystery" in caplog.text


def test_state_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    save_state(State(theme="light", geometry="800x600+10+10", font_size=14, last_note_id="x"), path)
    loaded = load_state(path)
    assert loaded.theme == "light"
    assert loaded.geometry == "800x600+10+10"
    assert loaded.font_size == 14
    assert loaded.last_note_id == "x"


def test_missing_state_gives_defaults(tmp_path: Path) -> None:
    assert load_state(tmp_path / "nope.json") == State()


def test_corrupt_state_gives_defaults(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    path.write_text("not json", encoding="utf-8")
    assert load_state(path) == State()


def test_state_ignores_bad_field_values(tmp_path: Path) -> None:
    path = _write(tmp_path / "s.json", {"theme": "neon", "font_size": 999, "geometry": 5})
    assert load_state(path) == State()


def test_save_state_swallows_write_failures(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("file")
    save_state(State(), blocker / "state.json")  # must not raise
