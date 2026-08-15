from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import Iterable

from .schema import DesignRecord


PALETTE = (
    (31, 78, 121),
    (196, 72, 67),
    (89, 161, 79),
    (242, 142, 43),
    (176, 122, 161),
    (237, 201, 72),
    (118, 183, 178),
)


def _chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def _png_bytes(width: int, height: int, pixels: bytearray) -> bytes:
    rows = b"".join(
        b"\x00" + bytes(pixels[row * width * 3 : (row + 1) * width * 3])
        for row in range(height)
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(rows, level=9))
        + _chunk(b"IEND", b"")
    )


def _line_points(x0: int, y0: int, x1: int, y1: int) -> Iterable[tuple[int, int]]:
    dx = abs(x1 - x0)
    sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0)
    sy = 1 if y0 < y1 else -1
    error = dx + dy
    while True:
        yield x0, y0
        if x0 == x1 and y0 == y1:
            break
        twice = 2 * error
        if twice >= dy:
            error += dy
            x0 += sx
        if twice <= dx:
            error += dx
            y0 += sy


def render_preview(
    record: DesignRecord,
    output_path: Path,
    *,
    width: int = 256,
    height: int = 256,
    padding: int = 8,
    color_blocks: bool = True,
    show_jumps: bool = False,
) -> Path:
    if width < 2 or height < 2:
        raise ValueError("preview dimensions must be at least 2x2")
    if padding < 0 or padding * 2 >= min(width, height):
        raise ValueError("padding leaves no drawable area")

    events = record.stitch.get("command_sequence", [])
    segments: list[
        tuple[tuple[float, float], tuple[float, float], tuple[int, int, int]]
    ] = []
    current = (0.0, 0.0)
    block_index = 0
    for event in events:
        event_type = event.get("type")
        if event_type == "color_change":
            block_index += 1
            continue
        if event_type not in {"stitch", "jump", "sequin_eject"}:
            continue
        if not isinstance(event.get("x"), (int, float)) or not isinstance(
            event.get("y"), (int, float)
        ):
            continue
        target = (float(event["x"]), float(event["y"]))
        if event_type == "stitch" or show_jumps:
            color = (
                PALETTE[block_index % len(PALETTE)]
                if color_blocks
                else PALETTE[0]
            )
            segments.append((current, target, color))
        current = target
    if not segments:
        raise ValueError("record has no renderable stitch path")

    points = [point for start, target, _ in segments for point in (start, target)]
    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)
    span_x = max_x - min_x
    span_y = max_y - min_y
    drawable_width = width - padding * 2 - 1
    drawable_height = height - padding * 2 - 1
    scale = min(
        drawable_width / span_x if span_x else float("inf"),
        drawable_height / span_y if span_y else float("inf"),
    )
    if scale == float("inf"):
        scale = 1.0
    used_width = span_x * scale
    used_height = span_y * scale
    offset_x = padding + (drawable_width - used_width) / 2.0
    offset_y = padding + (drawable_height - used_height) / 2.0

    def project(x: float, y: float) -> tuple[int, int]:
        return (
            round(offset_x + (x - min_x) * scale),
            round(height - 1 - (offset_y + (y - min_y) * scale)),
        )

    pixels = bytearray([255] * width * height * 3)
    for start, target, color in segments:
        x0, y0 = project(*start)
        x1, y1 = project(*target)
        for x, y in _line_points(x0, y0, x1, y1):
            if 0 <= x < width and 0 <= y < height:
                position = (y * width + x) * 3
                pixels[position : position + 3] = bytes(color)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.tmp")
    temporary.write_bytes(_png_bytes(width, height, pixels))
    temporary.replace(output_path)
    return output_path
