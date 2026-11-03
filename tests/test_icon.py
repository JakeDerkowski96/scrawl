"""Tests for the generated icon."""

import struct
import zlib

import pytest

from scrawl.icon import png_bytes, render_rgba


@pytest.mark.parametrize("size", [16, 32, 64])
def test_png_is_structurally_valid(size: int) -> None:
    data = png_bytes(size)
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", data[16:24])
    assert (width, height) == (size, size)
    assert data.endswith(b"IEND" + struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF))


def test_idat_decompresses_to_expected_length() -> None:
    size = 32
    data = png_bytes(size)
    idat_start = data.index(b"IDAT") + 4
    idat_len = struct.unpack(">I", data[idat_start - 8 : idat_start - 4])[0]
    raw = zlib.decompress(data[idat_start : idat_start + idat_len])
    assert len(raw) == size * (1 + size * 4)


def test_corners_are_transparent_and_center_is_opaque() -> None:
    size = 32
    rgba = render_rgba(size)
    assert rgba[3] == 0  # top-left pixel alpha
    center = (size // 2 * size + size // 2) * 4
    assert rgba[center + 3] == 255
