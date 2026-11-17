"""Draws the app icon: the mushroom mascot with a dark outline, at every size Windows asks for.

Run:  uv run python design/make_icon.py
Out:  src/thedownloader/assets/icon.ico   (used by the window, the taskbar and the shortcuts)
      design/icon-preview.png             (all sizes side by side, on a dark and a light strip)

Each size is the 16 by 16 drawing scaled by a whole number, so the pixels stay crisp.
The outline keeps the pink and cream readable on a light taskbar as well as a dark one.
"""

import struct
import zlib
from pathlib import Path

from make_mascots import LETTERS, MASCOTS

OUTLINE = "#020f08"
SIZES = [16, 24, 32, 48, 64, 128, 256]


def outlined() -> list[list[str | None]]:
    rows = MASCOTS["mushroom"].strip("\n").split("\n")
    grid = [[LETTERS[c] if c != "." else None for c in row] for row in rows]
    out = [row[:] for row in grid]
    for y in range(16):
        for x in range(16):
            if grid[y][x] is None and any(
                0 <= y + dy < 16 and 0 <= x + dx < 16 and grid[y + dy][x + dx] is not None
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            ):
                out[y][x] = OUTLINE
    return out


def render(size: int, art: list[list[str | None]]) -> list[list[bytes]]:
    """RGBA rows. Sizes that are not a multiple of 16 get the largest whole scale, centred."""
    scale = max(1, size // 16)
    offset = (size - 16 * scale) // 2
    clear = b"\x00\x00\x00\x00"
    pixels = [[clear] * size for _ in range(size)]
    for y in range(16):
        for x in range(16):
            colour = art[y][x]
            if colour:
                value = bytes.fromhex(colour[1:]) + b"\xff"
                for yy in range(scale):
                    for xx in range(scale):
                        pixels[offset + y * scale + yy][offset + x * scale + xx] = value
    return pixels


def png(pixels: list[list[bytes]]) -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    height, width = len(pixels), len(pixels[0])
    data = b"".join(b"\x00" + b"".join(row) for row in pixels)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(data, 9)) + chunk(b"IEND", b""))


def ico(images: list[tuple[int, bytes]]) -> bytes:
    """An .ico file holding PNG images, which Windows reads since Vista."""
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, blob in images:
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(blob), offset)
        blobs += blob
        offset += len(blob)
    return header + entries + blobs


def main() -> None:
    art = outlined()
    root = Path(__file__).resolve().parents[1]
    target = root / "src" / "thedownloader" / "assets" / "icon.ico"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(ico([(size, png(render(size, art))) for size in SIZES]))
    print(target, target.stat().st_size, "bytes")

    # preview: every size on a dark strip above a light strip
    width = sum(SIZES) + 20 * (len(SIZES) + 1)
    height = 2 * (256 + 40)
    preview = [[bytes.fromhex("063420ff" if y < height // 2 else "f3f3f3ff") for _ in range(width)] for y in range(height)]
    for strip in (0, 1):
        x = 20
        for size in SIZES:
            top = strip * (height // 2) + 20 + (256 - size)
            for y, row in enumerate(render(size, art)):
                for dx, value in enumerate(row):
                    if value[3]:
                        preview[top + y][x + dx] = value
            x += size + 20
    preview_file = root / "design" / "icon-preview.png"
    preview_file.write_bytes(png(preview))
    print(preview_file)


if __name__ == "__main__":
    main()
