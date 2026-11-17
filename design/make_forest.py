"""Draws the app's forest background as pixel art and saves it as a small PNG.

Run:  uv run python design/make_forest.py
Out:  ui/src/art/forest.png

The picture is original and made entirely by this script, so it can be changed by
changing numbers here. It repeats seamlessly left to right, and its top row is one
flat colour, so the window can show it at a fixed size on any screen:
3 screen pixels per art pixel, pinned to the bottom, repeated sideways. At that size it
is 2160 screen pixels tall, enough for a maximised window on a 4K screen.

Only the standard library is used; no image library is needed.
"""

import math
import random
import struct
import sys
import zlib
from pathlib import Path

W, H = 640, 400    # the scene: everything is drawn in these coordinates
TOTAL = 720        # the saved picture is taller: the big trunks carry on upward, for a maximised window
LIFT = TOTAL - H   # how far the scene sits below the picture's top
FERN_BASE = 394   # the front ferns stand a little above the bottom edge, which the status bar covers

COLOURS = {
    # backdrop, top (deep canopy) to bottom (light between the trunks)
    "sky0": "#052b1b", "sky1": "#063420", "sky2": "#0a4a2c", "sky3": "#116540", "glow": "#1b7d52",
    # far, middle and near pines
    "far": "#15694a", "far_lit": "#19754f",
    "mid": "#0b4f31", "mid_lit": "#10603b", "mid_dark": "#083f27",
    "near": "#06361f", "near_lit": "#0c4f2c", "near_dark": "#03200f",
    # bark, light to dark
    "fbark0": "#5f5f3c", "fbark1": "#4d4a30", "fbark2": "#3c3a28", "fbark3": "#2c2b1f",   # the same, far away
    "bark0": "#a2683c", "bark1": "#7d4a2a", "bark2": "#5c3520", "bark3": "#3d2216", "bark4": "#27140c",
    # ground
    "grass": "#0a4428", "grass_lit": "#1d7a45", "grass_dark": "#062f1b", "fern": "#031c10",
    "dirt": "#4a2e1c", "dirt_lit": "#6b4426",
    # small things
    "bell": "#ff7fb6", "bell_dark": "#c4467f", "cap": "#ff7a66", "cream": "#f8efd8", "spark": "#c8f5d0",
}
NAMES = list(COLOURS)
INDEX = {name: number for number, name in enumerate(NAMES)}
BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]

image = [[INDEX["sky0"]] * W for _ in range(TOTAL)]
rng = random.Random(11)


def put(x: int, y: int, colour: str) -> None:
    y += LIFT
    if 0 <= y < TOTAL:
        image[y][x % W] = INDEX[colour]   # x wraps, which is what makes the picture repeat


def dithered(x: int, y: int, amount: float) -> bool:
    """True for a share of pixels that grows with amount (0 to 1), in an even pattern."""
    return amount * 16 > BAYER[y % 4][x % 4] + 0.5


def wave(x: int, *parts: tuple[float, int, float]) -> float:
    """A bumpy line that ends where it started, so it joins up across the repeat."""
    return sum(size * math.sin(x * 2 * math.pi * count / W + shift) for size, count, shift in parts)


def backdrop() -> None:
    stops = [(0, "sky0"), (120, "sky1"), (190, "sky2"), (255, "sky3"), (320, "glow"), (H, "glow")]
    for y in range(H):
        for (start, colour), (end, following) in zip(stops, stops[1:]):
            if start <= y < end:
                amount = (y - start) / (end - start)
                for x in range(W):
                    put(x, y, following if dithered(x, y, amount) else colour)


def mist(top: int, bottom: int, colour: str, strength: float) -> None:
    for y in range(top, 390):   # past bottom it stays at full strength, down under the ground
        amount = strength * min(1.0, (y - top) / (bottom - top))
        for x in range(W):
            if dithered(x, y, amount):
                put(x, y, colour)


def pine(cx: int, base: int, height: int, spread: float, shades: tuple[str, str, str],
         trunk_width: int, trunk_share: float) -> None:
    """A tall conifer: a trunk, and boughs in tiers that each widen and then step back in."""
    dark, plain, lit = shades
    top = base - height
    foliage_bottom = base - int(height * trunk_share)
    rows = foliage_bottom - top
    tiers = max(4, rows // 13)
    # the trunk first, so the boughs cover its upper part
    reach = max(base + 2, ground_line(cx) + 8)   # always down into the ground, which is drawn over it
    for y in range(top + rows // 3, reach):
        for dx in range(trunk_width):
            x = cx - trunk_width // 2 + dx
            share = dx / max(1, trunk_width - 1)
            put(x, y, "bark1" if share < 0.3 else "bark2" if share < 0.7 else "bark3")
    if trunk_width == 0:
        for y in range(foliage_bottom, reach):
            put(cx, y, dark)
    for y in range(top, foliage_bottom):
        along = (y - top) / rows
        tier = along * tiers
        within = tier - int(tier)
        half = int((1 + spread * along ** 0.85) * (0.45 + 0.55 * within) + rng.random() * 0.9)
        for dx in range(-half, half + 1):
            side = dx / (half + 0.5)
            colour = plain
            if side < -0.3 and within > 0.25:
                colour = lit                      # light falls from the upper left
            if side > 0.4 or (within < 0.2 and tier >= 1):
                colour = dark                     # right side, and under each bough
            put(cx + dx, y, colour)


def row_of_pines(base: int, heights: tuple[int, int], gap: tuple[int, int], spread: float,
                 shades: tuple[str, str, str], trunk_width: int, trunk_share: float) -> None:
    x = rng.randint(0, gap[0])
    while x < W - gap[0] // 2:
        height = rng.randint(*heights)
        pine(x, base + rng.randint(-2, 2), height, spread * height / heights[1] * rng.uniform(0.85, 1.15),
             shades, trunk_width, trunk_share)
        x += rng.randint(*gap)


def ground_line(x: int) -> int:
    return int(364 + wave(x, (3, 3, 0.4), (2, 7, 1.9)))


def ground() -> None:
    for x in range(W):
        top = ground_line(x)
        path = 379 + wave(x, (2.5, 2, 2.2), (1.2, 5, 0.3))       # the middle of the dirt path
        half = 3.2 + wave(x, (0.9, 4, 1.1), (0.6, 9, 2.0))         # half its thickness
        for y in range(top, H):
            colour = "grass"
            if y == top and rng.random() < 0.55:
                colour = "grass_lit"
            elif y > top + 2 and rng.random() < 0.06:
                colour = "grass_dark"
            inside = 1 - (abs(y - path) - half) / 3.5              # 1 on the path, fading to 0 over a few rows
            if inside > 0 and y > top + 3:
                if dithered(x, y, min(1.0, inside)):
                    colour = "dirt_lit" if rng.random() < 0.07 else "dirt"
            put(x, y, colour)
        if rng.random() < 0.3:                     # blades of grass standing above the line
            put(x, top - 1, "grass_lit" if rng.random() < 0.5 else "grass")


BARK = ["bark0", "bark1", "bark2", "bark3", "bark4"]
FAR_BARK = ["fbark0", "fbark1", "fbark2", "fbark3", "fbark3"]


def giant(cx: int, width: int, ladder: list[str] = BARK, base: int | None = None,
          root_rows: int = 44, root_reach: int = 17) -> None:
    """One of the big trees: only its trunk is in the picture, its crown is above it.

    The trunk runs to the very top of the picture and thins out into the dark there,
    so it never ends in a straight cut however tall the window is. At the bottom it
    sweeps out into roots that follow the ground's own curve, so it stands on the
    ground instead of being laid over it.
    """
    front = base is None
    if front:
        base = ground_line(cx) + 3

    def bottom(x: int) -> int:
        """The lowest row of bark in column x: just below the grass line there, a little uneven."""
        if not front:
            return base
        return ground_line(x) + 2 + int(1.5 * (1 + math.sin(x * 0.9 + cx)))

    furrows: dict[int, set[int]] = {}
    for column in range(-width - root_reach, width + root_reach + 1):   # cracks in the bark: broken vertical lines
        rows: set[int] = set()
        if rng.random() < 0.45:
            y = -LIFT - rng.randint(0, 30)
            while y < H:
                length = rng.randint(8, 34)
                rows.update(range(y, y + length))
                y += length + rng.randint(5, 22)
        furrows[column] = rows
    fade_until = -LIFT + 110
    for y in range(-LIFT, base + 8):
        flare = min(1.0, max(0, y - (base - root_rows)) / root_rows)   # the trunk sweeps out into roots at the bottom
        extra = int(flare ** 2.6 * root_reach)
        lean = int(1.6 * math.sin(min(y, base) / 27 + cx))
        left, right = cx - width // 2 - extra + lean, cx + width // 2 + extra + lean
        for x in range(left, right + 1):
            if y > bottom(x):
                continue
            if y < fade_until and dithered(x, y, (fade_until - y) / 110):
                continue                                      # lost in the dark of the canopy
            share = (x - left) / (right - left)
            step = 0 if share < 0.07 else 1 if share < 0.3 else 2 if share < 0.68 else 3
            column = x - lean - cx
            if y in furrows.get(column, ()):
                step += 1
            elif y in furrows.get(column - 1, ()) and share < 0.68:
                step -= 1                                     # the lit edge beside a crack
            if front and y > bottom(x) - 3:
                step += 1                                     # the foot stands in its own shade
            put(x, y, ladder[max(0, min(4, step))])
    if not front:
        return
    spread = width // 2 + root_reach
    for side in (-1, 1):                                      # roots running out over the ground, thinning as they go
        for number in range(2):
            start = cx + side * (spread - 4 - number * 9)
            length = rng.randint(9, 16) - number * 3
            for step in range(length):
                x = start + side * step
                thick = max(1, round(3 * (1 - step / length)))
                surface = ground_line(x) + 2
                for y in range(surface - thick, surface + 1):
                    colour = "bark3" if y == surface else "bark1" if (y == surface - thick and side < 0) else "bark2"
                    put(x, y, colour)
    for x in range(cx + spread - 6, cx + spread + 34):        # soft shade on the grass, falling to the right
        fade = 0.5 * (1 - (x - cx - spread + 6) / 40)
        for y in range(ground_line(x) + 1, ground_line(x) + 6):
            if dithered(x, y, fade) and image[y + LIFT][x % W] in (INDEX["grass"], INDEX["grass_lit"]):
                put(x, y, "grass_dark")
    for x in range(cx - spread - 18, cx + spread + 18):       # a few blades of grass in front of the foot
        if rng.random() < 0.35:
            foot = bottom(x)
            height = rng.randint(1, 3)
            for y in range(foot - height, foot + 1):
                put(x, y, "grass_lit" if y == foot - height else "grass")

def foxglove(x: int, height: int) -> None:
    base = ground_line(x) + rng.randint(2, 8)
    for y in range(base - height, base):
        put(x, y, "grass_lit")
    put(x - 1, base - 2, "grass_lit")
    put(x + 1, base - 4, "grass_lit")
    side = rng.choice((-1, 1))
    y = base - height
    put(x, y - 1, "bell")
    while y < base - height * 0.4:
        put(x + side, y, "bell")
        put(x + side, y + 1, "bell")
        put(x + side * 2, y + 1, "bell_dark")
        side = -side
        y += 2


def mushroom(x: int) -> None:
    base = ground_line(x) + rng.randint(4, 12)
    for dx in range(-2, 3):
        put(x + dx, base - 3, "cap")
    for dx in range(-1, 2):
        put(x + dx, base - 4, "cap")
    put(x - 1, base - 3, "cream")
    put(x + 1, base - 4, "cream")
    put(x, base - 2, "cream")
    put(x, base - 1, "cream")


def fern(x: int, size: int) -> None:
    """A dark clump at the very front, which frames the bottom edge."""
    for frond in range(-3, 4):
        reach = size * (1 - abs(frond) / 5)
        for step in range(int(reach)):
            droop = (step / reach) ** 2 * size * 0.45
            put(x + int(frond * step * 0.42), FERN_BASE - 1 - int(step * 0.9 - droop), "fern")
            put(x + int(frond * step * 0.42), FERN_BASE - int(step * 0.9 - droop), "fern")


def sparks(count: int) -> None:
    for _ in range(count):
        put(rng.randrange(W), rng.randint(250, 355), "spark")


def save(path: Path) -> None:
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    palette = b"".join(bytes.fromhex(COLOURS[name][1:]) for name in NAMES)
    rows = b"".join(b"\x00" + bytes(row) for row in image)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", W, TOTAL, 8, 3, 0, 0, 0))
        + chunk(b"PLTE", palette)
        + chunk(b"IDAT", zlib.compress(rows, 9))
        + chunk(b"IEND", b"")
    )


def main() -> None:
    backdrop()
    row_of_pines(352, (55, 115), (9, 17), 25, ("far", "far", "far_lit"), 0, 0.08)
    mist(318, 356, "glow", 0.7)
    for cx, width in ((34, 28), (166, 34), (240, 24), (402, 32), (462, 24), (584, 30)):   # thick trunks, far off
        giant(cx, width, FAR_BARK, ground_line(cx) + 8, 16, 4)
    mist(300, 362, "sky3", 0.5)
    row_of_pines(358, (120, 195), (28, 46), 41, ("mid_dark", "mid", "mid_lit"), 7, 0.14)
    mist(336, 362, "sky3", 0.45)
    row_of_pines(366, (215, 330), (58, 96), 46, ("near_dark", "near", "near_lit"), 10, 0.2)
    ground()
    for cx, width in ((92, 40), (318, 48), (505, 36)):
        giant(cx, width)
    sparks(26)
    for x in (30, 38, 150, 158, 171, 250, 384, 391, 440, 560, 569, 612):
        foxglove(x, rng.randint(11, 19))
    for x in (60, 205, 276, 420, 470, 590):
        mushroom(x)
    for x in (8, 132, 228, 352, 455, 548, 628):
        fern(x, rng.randint(14, 22))
    out = Path(__file__).resolve().parents[1] / "ui" / "src" / "art" / "forest.png"
    save(out)
    print(f"{out}  {out.stat().st_size} bytes")


if __name__ == "__main__":
    sys.exit(main())
