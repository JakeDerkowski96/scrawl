"""Draw the app icon in code so no binary asset needs to ship or be tracked.

Required permissions: none.

Usage:
    data = png_bytes(32)          # PNG for the tray icon or Tk's iconphoto

Notes:
    The icon is a rounded indigo square with three "scrawled" text lines. It is
    rasterized with a signed-distance function, which gives smooth edges at any
    size without an imaging library.
"""

import math
import struct
import zlib

_BACKGROUND = (79, 70, 229)
_FOREGROUND = (255, 255, 255)

# (center_x, center_y, half_width, half_height) as fractions of the icon size.
_LINES = (
    (0.50, 0.32, 0.26, 0.05),
    (0.50, 0.50, 0.26, 0.05),
    (0.44, 0.68, 0.20, 0.05),
)


def _rounded_box_distance(
    px: float, py: float, cx: float, cy: float, half_w: float, half_h: float, radius: float
) -> float:
    """Signed distance from a point to a rounded rectangle (negative inside)."""
    qx = abs(px - cx) - half_w + radius
    qy = abs(py - cy) - half_h + radius
    return min(max(qx, qy), 0.0) + math.hypot(max(qx, 0.0), max(qy, 0.0)) - radius


def _coverage(distance: float) -> float:
    """Convert a signed distance in pixels into 0..1 anti-aliased coverage."""
    return min(max(0.5 - distance, 0.0), 1.0)


def render_rgba(size: int) -> bytes:
    """Return the icon as ``size`` x ``size`` straight-alpha RGBA bytes."""
    half = size / 2
    radius = size * 0.22
    pixels = bytearray()
    for y in range(size):
        for x in range(size):
            px, py = x + 0.5, y + 0.5
            alpha = _coverage(_rounded_box_distance(px, py, half, half, half, half, radius))
            red, green, blue = _BACKGROUND
            for lx, ly, lw, lh in _LINES:
                bar = _coverage(
                    _rounded_box_distance(
                        px, py, lx * size, ly * size, lw * size, lh * size, lh * size
                    )
                )
                if bar > 0:
                    red = round(red + (_FOREGROUND[0] - red) * bar)
                    green = round(green + (_FOREGROUND[1] - green) * bar)
                    blue = round(blue + (_FOREGROUND[2] - blue) * bar)
            pixels += bytes((red, green, blue, round(alpha * 255)))
    return bytes(pixels)


def _chunk(kind: bytes, data: bytes) -> bytes:
    """Build one PNG chunk (length, type, data, CRC)."""
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def png_bytes(size: int) -> bytes:
    """Return the icon as a PNG file's bytes."""
    rgba = render_rgba(size)
    stride = size * 4
    # Each scanline is prefixed with filter type 0 (none).
    raw = b"".join(b"\x00" + rgba[row * stride : (row + 1) * stride] for row in range(size))
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(raw, 9))
        + _chunk(b"IEND", b"")
    )
