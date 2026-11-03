"""Parse hotkey strings such as ``ctrl+alt+n`` into Win32 modifier/key codes.

Required permissions: none (pure parsing; registration lives in ``shell``).

Usage:
    hotkey = parse_hotkey("Ctrl+Alt+N")
    hotkey.text        # "ctrl+alt+n"  (canonical form)

Notes:
    At least one modifier is required. A bare letter registered globally would
    swallow that key in every application.
"""

from dataclasses import dataclass

from scrawl.exceptions import ConfigurationError

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
# Without this, holding the keys down would fire the hotkey repeatedly.
MOD_NOREPEAT = 0x4000

_MODIFIERS = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "super": MOD_WIN,
    "meta": MOD_WIN,
}

# Canonical modifier order for the normalized text form.
_MODIFIER_ORDER = (("ctrl", MOD_CONTROL), ("alt", MOD_ALT), ("shift", MOD_SHIFT), ("win", MOD_WIN))

_NAMED_KEYS = {
    "space": 0x20,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "backspace": 0x08,
    "insert": 0x2D,
    "delete": 0x2E,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    ";": 0xBA,
    "=": 0xBB,
    ",": 0xBC,
    "-": 0xBD,
    ".": 0xBE,
    "/": 0xBF,
    "`": 0xC0,
    "[": 0xDB,
    "\\": 0xDC,
    "]": 0xDD,
    "'": 0xDE,
}


@dataclass(frozen=True)
class Hotkey:
    """A parsed global hotkey.

    Attributes:
        modifiers: Bitwise OR of ``MOD_*`` flags (without ``MOD_NOREPEAT``).
        vk: Windows virtual-key code of the main key.
        text: Canonical lowercase spelling, e.g. ``"ctrl+alt+n"``.
    """

    modifiers: int
    vk: int
    text: str


def parse_hotkey(spec: str) -> Hotkey:
    """Parse ``spec`` (e.g. ``"Ctrl+Alt+N"``) into a ``Hotkey``.

    Raises:
        ConfigurationError: If the spec is empty, has no modifier, has more or
            fewer than one main key, or names an unknown key.
    """
    parts = [part.strip().lower() for part in spec.split("+")]
    # Empty parts come from "", "ctrl+", or "ctrl++"; the plus sign itself is
    # not supported as a main key because it is the separator.
    if any(not part for part in parts):
        raise ConfigurationError(f"hotkey {spec!r} is not valid; expected e.g. 'ctrl+alt+n'")

    modifiers = 0
    keys: list[str] = []
    for part in parts:
        if part in _MODIFIERS:
            modifiers |= _MODIFIERS[part]
        else:
            keys.append(part)

    if modifiers == 0:
        raise ConfigurationError(
            f"hotkey {spec!r} needs at least one modifier (ctrl, alt, shift, win)"
        )
    if len(keys) != 1:
        raise ConfigurationError(f"hotkey {spec!r} must have exactly one non-modifier key")

    vk = _key_to_vk(keys[0], spec)
    names = [name for name, flag in _MODIFIER_ORDER if modifiers & flag]
    return Hotkey(modifiers=modifiers, vk=vk, text="+".join([*names, keys[0]]))


def _key_to_vk(key: str, spec: str) -> int:
    """Translate one key name to a virtual-key code."""
    if len(key) == 1 and key.isascii() and key.isalnum():
        # Virtual-key codes for 0-9 and A-Z equal their uppercase ASCII values.
        return ord(key.upper())
    if key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        return 0x70 + int(key[1:]) - 1
    if key in _NAMED_KEYS:
        return _NAMED_KEYS[key]
    raise ConfigurationError(f"hotkey {spec!r} uses an unknown key {key!r}")
