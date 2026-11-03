"""Shared fixtures."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from scrawl.config import ENV_CONFIG_DIR
from scrawl.store import NoteStore


@pytest.fixture
def store(tmp_path: Path) -> NoteStore:
    """A store backed by an empty temp folder."""
    return NoteStore(tmp_path / "notes")


@pytest.fixture(autouse=True)
def isolated_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the config folder at a temp dir so tests never touch real settings."""
    path = tmp_path / "config"
    monkeypatch.setenv(ENV_CONFIG_DIR, str(path))
    yield path
