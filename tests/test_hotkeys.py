"""Tests for hotkey string parsing."""

import pytest

from scrawl.exceptions import ConfigurationError
from scrawl.hotkeys import MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, parse_hotkey


def test_parses_letter_hotkey() -> None:
    hotkey = parse_hotkey("ctrl+alt+n")
    assert hotkey.modifiers == MOD_CONTROL | MOD_ALT
    assert hotkey.vk == ord("N")
    assert hotkey.text == "ctrl+alt+n"


def test_normalizes_case_spacing_and_order() -> None:
    assert parse_hotkey(" Alt + CTRL + J ").text == "ctrl+alt+j"


def test_aliases_map_to_canonical_modifiers() -> None:
    hotkey = parse_hotkey("control+super+shift+k")
    assert hotkey.modifiers == MOD_CONTROL | MOD_WIN | MOD_SHIFT
    assert hotkey.text == "ctrl+shift+win+k"


def test_function_keys() -> None:
    assert parse_hotkey("ctrl+f1").vk == 0x70
    assert parse_hotkey("ctrl+f24").vk == 0x87


def test_named_and_digit_keys() -> None:
    assert parse_hotkey("ctrl+alt+space").vk == 0x20
    assert parse_hotkey("ctrl+alt+5").vk == ord("5")
    assert parse_hotkey("ctrl+alt+;").vk == 0xBA


@pytest.mark.parametrize(
    "spec",
    ["", "n", "ctrl", "ctrl+", "ctrl++", "ctrl+alt+n+m", "ctrl+f25", "ctrl+banana", "f5"],
)
def test_invalid_specs_raise(spec: str) -> None:
    with pytest.raises(ConfigurationError):
        parse_hotkey(spec)


def test_error_message_names_the_spec() -> None:
    with pytest.raises(ConfigurationError, match="ctrl\\+banana"):
        parse_hotkey("ctrl+banana")
