from __future__ import annotations

import struct
import zlib
from pathlib import Path


SIZE = 256
SCALE = 3
CANVAS = SIZE * SCALE
ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "packaging" / "fnos-native"


def _rgba(hex_color: str) -> tuple[int, int, int, int]:
    hex_color = hex_color.lstrip("#")
    return (
        int(hex_color[0:2], 16),
        int(hex_color[2:4], 16),
        int(hex_color[4:6], 16),
        255,
    )


NAVY = _rgba("#172033")
WHITE = _rgba("#ffffff")
GREEN = _rgba("#22c55e")
TRANSPARENT = (0, 0, 0, 0)


def _inside_rounded_rect(x: float, y: float, size: float, radius: float) -> bool:
    if radius <= x <= size - radius or radius <= y <= size - radius:
        return 0 <= x <= size and 0 <= y <= size
    cx = radius if x < radius else size - radius
    cy = radius if y < radius else size - radius
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius**2


def _inside_rect(x: float, y: float, left: float, top: float, right: float, bottom: float, radius: float = 0) -> bool:
    if not (left <= x <= right and top <= y <= bottom):
        return False
    if radius <= 0:
        return True
    if left + radius <= x <= right - radius or top + radius <= y <= bottom - radius:
        return True
    cx = left + radius if x < left + radius else right - radius
    cy = top + radius if y < top + radius else bottom - radius
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius**2


def _inside_polygon(x: float, y: float, points: list[tuple[float, float]]) -> bool:
    inside = False
    j = len(points) - 1
    for i, point in enumerate(points):
        xi, yi = point
        xj, yj = points[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _distance_to_segment(x: float, y: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx = bx - ax
    dy = by - ay
    if dx == 0 and dy == 0:
        return ((x - ax) ** 2 + (y - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
    px = ax + t * dx
    py = ay + t * dy
    return ((x - px) ** 2 + (y - py) ** 2) ** 0.5


def _inside_stroke(x: float, y: float, points: list[tuple[float, float]], width: float) -> bool:
    radius = width / 2
    return any(
        _distance_to_segment(x, y, ax, ay, bx, by) <= radius
        for (ax, ay), (bx, by) in zip(points, points[1:])
    )


def _pixel(x: float, y: float) -> tuple[int, int, int, int]:
    if not _inside_rounded_rect(x, y, SIZE, 48):
        return TRANSPARENT

    color = NAVY
    x_shape = [
        (62, 56),
        (106, 128),
        (60, 200),
        (92, 200),
        (122, 152),
        (151, 200),
        (194, 200),
        (144, 122),
        (186, 56),
        (154, 56),
        (128, 98),
        (103, 56),
    ]
    if _inside_polygon(x, y, x_shape):
        color = WHITE
    if _inside_stroke(x, y, [(128, 50), (128, 154)], 18):
        color = GREEN
    if _inside_stroke(x, y, [(91, 122), (128, 160), (165, 122)], 18):
        color = GREEN
    if _inside_rect(x, y, 70, 190, 186, 204, 7):
        color = GREEN
    return color


def _render_high_res() -> list[tuple[int, int, int, int]]:
    pixels = []
    for yy in range(CANVAS):
        y = (yy + 0.5) / SCALE
        for xx in range(CANVAS):
            x = (xx + 0.5) / SCALE
            pixels.append(_pixel(x, y))
    return pixels


def _downsample(pixels: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    out = []
    for y in range(SIZE):
        for x in range(SIZE):
            totals = [0, 0, 0, 0]
            for sy in range(SCALE):
                for sx in range(SCALE):
                    px = pixels[(y * SCALE + sy) * CANVAS + x * SCALE + sx]
                    for channel in range(4):
                        totals[channel] += px[channel]
            count = SCALE * SCALE
            out.append(tuple(round(value / count) for value in totals))
    return out


def _write_png(path: Path, pixels: list[tuple[int, int, int, int]]) -> None:
    raw_rows = []
    for y in range(SIZE):
        row = bytearray([0])
        for pixel in pixels[y * SIZE : (y + 1) * SIZE]:
            row.extend(pixel)
        raw_rows.append(bytes(row))
    compressed = zlib.compress(b"".join(raw_rows), 9)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    content = b"\x89PNG\r\n\x1a\n"
    content += chunk(b"IHDR", struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0))
    content += chunk(b"IDAT", compressed)
    content += chunk(b"IEND", b"")
    path.write_bytes(content)


def main() -> None:
    pixels = _downsample(_render_high_res())
    for name in ("ICON.PNG", "ICON_256.PNG"):
        _write_png(OUT_DIR / name, pixels)


if __name__ == "__main__":
    main()
