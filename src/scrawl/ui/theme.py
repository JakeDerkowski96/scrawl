"""Color themes for the window.

Required permissions: none.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    """A complete set of colors; every widget reads from one of these."""

    name: str
    bg: str
    fg: str
    sidebar_bg: str
    sidebar_fg: str
    select_bg: str
    select_fg: str
    muted: str
    border: str
    accent: str
    done_fg: str


DARK = Theme(
    name="dark",
    bg="#1e1e24",
    fg="#e6e6ea",
    sidebar_bg="#17171c",
    sidebar_fg="#b8b8c2",
    select_bg="#33334a",
    select_fg="#ffffff",
    muted="#7d7d8a",
    border="#2a2a33",
    accent="#7c83ff",
    done_fg="#6b6b78",
)

LIGHT = Theme(
    name="light",
    bg="#fbfbfc",
    fg="#22222a",
    sidebar_bg="#f0f0f3",
    sidebar_fg="#44444e",
    select_bg="#dcdcf5",
    select_fg="#14141a",
    muted="#8a8a96",
    border="#dcdce2",
    accent="#4f46e5",
    done_fg="#9a9aa6",
)

THEMES = {DARK.name: DARK, LIGHT.name: LIGHT}
