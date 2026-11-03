"""Settings (hand-edited JSON) and window state (app-managed JSON).

Required permissions: read/write on the config folder (``%APPDATA%\\scrawl``,
or ``$SCRAWL_CONFIG_DIR``).

Usage:
    config = load_config()                 # creates config.json on first run
    state = load_state()
    save_state(state)

Notes:
    ``config.json`` holds choices the user makes by editing the file;
    ``state.json`` holds things the app remembers (theme, window position) and
    is safe to delete. They are separate so the app never rewrites a file the
    user is editing by hand.
"""

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, TypeVar

from scrawl.exceptions import ConfigurationError, StorageError
from scrawl.fsutil import atomic_write_text
from scrawl.hotkeys import parse_hotkey

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

APP_DIR_NAME = "scrawl"
ENV_CONFIG_DIR = "SCRAWL_CONFIG_DIR"
CONFIG_FILENAME = "config.json"
STATE_FILENAME = "state.json"
LOG_FILENAME = "scrawl.log"

DEFAULT_IPC_PORT = 47653


def config_dir() -> Path:
    """Return the folder holding config, state, and the log file."""
    override = os.environ.get(ENV_CONFIG_DIR)
    if override:
        return Path(override).expanduser()
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / APP_DIR_NAME
    return Path.home() / ".config" / APP_DIR_NAME


def default_notes_dir() -> Path:
    """Return the default notes folder, ``~/Documents/Scrawl``."""
    return Path.home() / "Documents" / "Scrawl"


@dataclass(frozen=True)
class Config:
    """User-editable settings. See ``docs/configuration.md`` for each field."""

    notes_dir: Path
    hotkey_new: str = "ctrl+alt+n"
    hotkey_toggle: str = "ctrl+alt+j"
    ipc_port: int = DEFAULT_IPC_PORT
    close_to_tray: bool = True
    font_family: str = "Consolas"
    font_size: int = 12
    autosave_ms: int = 700

    def to_json_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict of every field."""
        data = asdict(self)
        data["notes_dir"] = str(self.notes_dir)
        return data


@dataclass
class State:
    """Things the app remembers between runs."""

    theme: str = "dark"
    geometry: str | None = None
    sidebar_visible: bool = True
    font_size: int | None = None
    last_note_id: str | None = None


def default_config() -> Config:
    """Return the built-in defaults."""
    return Config(notes_dir=default_notes_dir())


def load_config(path: Path | None = None, *, write_defaults: bool = False) -> Config:
    """Load settings from ``path`` (default: ``config.json`` in the config dir).

    Args:
        path: Config file to read.
        write_defaults: If the file is missing, create it with the defaults so
            the user can discover and edit the options.

    Raises:
        ConfigurationError: If the file is not valid JSON or a value is invalid.
        StorageError: If defaults had to be written and that failed.
    """
    path = path or config_dir() / CONFIG_FILENAME
    if not path.exists():
        config = default_config()
        if write_defaults:
            atomic_write_text(path, _dump(config.to_json_dict()))
            logger.info("wrote default config to %s", path)
        return config

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            f"{path} is not valid JSON (line {exc.lineno}, column {exc.colno}): {exc.msg}"
        ) from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigurationError(f"could not read {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigurationError(f"{path} must contain a JSON object")
    return _config_from_mapping(raw, path)


def _config_from_mapping(raw: dict[str, Any], source: Path) -> Config:
    """Validate ``raw`` and merge it over the defaults."""
    defaults = default_config()
    known = set(defaults.to_json_dict())
    for key in sorted(set(raw) - known):
        logger.warning("%s: ignoring unknown setting %r", source, key)

    notes_dir_raw = _typed(raw, "notes_dir", str, str(defaults.notes_dir), source)
    notes_dir = Path(os.path.expandvars(notes_dir_raw)).expanduser()
    config = Config(
        notes_dir=notes_dir,
        hotkey_new=_typed(raw, "hotkey_new", str, defaults.hotkey_new, source),
        hotkey_toggle=_typed(raw, "hotkey_toggle", str, defaults.hotkey_toggle, source),
        ipc_port=_typed(raw, "ipc_port", int, defaults.ipc_port, source),
        close_to_tray=_typed(raw, "close_to_tray", bool, defaults.close_to_tray, source),
        font_family=_typed(raw, "font_family", str, defaults.font_family, source),
        font_size=_typed(raw, "font_size", int, defaults.font_size, source),
        autosave_ms=_typed(raw, "autosave_ms", int, defaults.autosave_ms, source),
    )
    _validate(config, source)
    return config


def _typed(raw: dict[str, Any], key: str, kind: type[_T], default: _T, source: Path) -> _T:
    """Return ``raw[key]`` if it has type ``kind``, else the default if absent."""
    if key not in raw:
        return default
    value = raw[key]
    # bool is a subclass of int; "ipc_port": true must not pass as 1.
    if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
        raise ConfigurationError(
            f"{source}: {key!r} must be {kind.__name__}, got {type(value).__name__}"
        )
    return value


def _validate(config: Config, source: Path) -> None:
    """Check ranges and hotkey syntax."""
    if not 1024 <= config.ipc_port <= 65535:
        raise ConfigurationError(f"{source}: 'ipc_port' must be 1024-65535")
    if not 6 <= config.font_size <= 72:
        raise ConfigurationError(f"{source}: 'font_size' must be 6-72")
    if not 100 <= config.autosave_ms <= 10_000:
        raise ConfigurationError(f"{source}: 'autosave_ms' must be 100-10000")
    new = parse_hotkey(config.hotkey_new)
    toggle = parse_hotkey(config.hotkey_toggle)
    if (new.modifiers, new.vk) == (toggle.modifiers, toggle.vk):
        raise ConfigurationError(f"{source}: 'hotkey_new' and 'hotkey_toggle' must differ")


def load_state(path: Path | None = None) -> State:
    """Load remembered window state; any problem yields defaults.

    State is disposable convenience data, so a corrupt file is logged and
    ignored rather than blocking startup.
    """
    path = path or config_dir() / STATE_FILENAME
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return State()
    except (OSError, ValueError) as exc:
        logger.warning("ignoring unreadable state file %s: %s", path, exc)
        return State()
    if not isinstance(raw, dict):
        logger.warning("ignoring state file %s: not a JSON object", path)
        return State()

    state = State()
    if raw.get("theme") in ("dark", "light"):
        state.theme = raw["theme"]
    if isinstance(raw.get("geometry"), str):
        state.geometry = raw["geometry"]
    if isinstance(raw.get("sidebar_visible"), bool):
        state.sidebar_visible = raw["sidebar_visible"]
    size = raw.get("font_size")
    if isinstance(size, int) and not isinstance(size, bool) and 6 <= size <= 72:
        state.font_size = size
    if isinstance(raw.get("last_note_id"), str):
        state.last_note_id = raw["last_note_id"]
    return state


def save_state(state: State, path: Path | None = None) -> None:
    """Persist ``state``; failures are logged, never raised.

    Losing a window position is not worth interrupting shutdown for.
    """
    path = path or config_dir() / STATE_FILENAME
    try:
        atomic_write_text(path, _dump(asdict(state)))
    except StorageError as exc:
        logger.warning("could not save state: %s", exc)


def _dump(data: dict[str, Any]) -> str:
    """Serialize ``data`` as readable, hand-editable JSON."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
