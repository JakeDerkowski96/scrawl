"""Tests for checkbox and list line handling."""

import pytest

from scrawl import checklist


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("- [ ] buy milk", "- [x] buy milk"),
        ("- [x] buy milk", "- [ ] buy milk"),
        ("- [X] buy milk", "- [ ] buy milk"),
        ("  * [ ] nested", "  * [x] nested"),
        ("- buy milk", "- [ ] buy milk"),
        ("buy milk", "- [ ] buy milk"),
        ("    indented text", "    - [ ] indented text"),
        ("", "- [ ] "),
    ],
)
def test_toggle_line(line: str, expected: str) -> None:
    assert checklist.toggle_line(line) == expected


def test_toggle_is_reversible() -> None:
    line = "- [ ] thing"
    assert checklist.toggle_line(checklist.toggle_line(line)) == line


@pytest.mark.parametrize(
    ("line", "done"),
    [("- [x] a", True), ("- [X] a", True), ("- [ ] a", False), ("a", False), ("- a", False)],
)
def test_is_done(line: str, done: bool) -> None:
    assert checklist.is_done(line) is done


def test_checkbox_span_covers_the_brackets() -> None:
    line = "  - [ ] hi"
    span = checklist.checkbox_span(line)
    assert span is not None
    assert line[span[0] : span[1]] == "[ ]"


def test_checkbox_span_is_none_for_non_checkbox() -> None:
    assert checklist.checkbox_span("- plain") is None


def test_continuation_of_checkbox_starts_unchecked() -> None:
    cont = checklist.continuation("- [x] done thing")
    assert cont == checklist.Continuation(prefix="- [ ] ", empty=False)


def test_continuation_keeps_indent_and_bullet_style() -> None:
    cont = checklist.continuation("  * item")
    assert cont == checklist.Continuation(prefix="  * ", empty=False)


def test_continuation_increments_numbers() -> None:
    cont = checklist.continuation("9. nine")
    assert cont == checklist.Continuation(prefix="10. ", empty=False)


@pytest.mark.parametrize("line", ["- [ ] ", "- ", "3. "])
def test_continuation_flags_empty_items(line: str) -> None:
    cont = checklist.continuation(line)
    assert cont is not None
    assert cont.empty is True


def test_continuation_is_none_for_plain_text() -> None:
    assert checklist.continuation("just words") is None
