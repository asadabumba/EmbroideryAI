from __future__ import annotations

import random

import pytest

from src.dst_parser import DSTParser


def _reference_dx(b0: int, b1: int, b2: int) -> int:
    return (
        ((b2 >> 2) & 1) * 81 - ((b2 >> 3) & 1) * 81
        + ((b1 >> 2) & 1) * 27 - ((b1 >> 3) & 1) * 27
        + ((b0 >> 2) & 1) * 9 - ((b0 >> 3) & 1) * 9
        + ((b1 >> 0) & 1) * 3 - ((b1 >> 1) & 1) * 3
        + ((b0 >> 0) & 1) - ((b0 >> 1) & 1)
    )


def _reference_dy_cartesian(b0: int, b1: int, b2: int) -> int:
    # В проекте используется декартова система: положительный Y вверх.
    return (
        ((b2 >> 5) & 1) * 81 - ((b2 >> 4) & 1) * 81
        + ((b1 >> 5) & 1) * 27 - ((b1 >> 4) & 1) * 27
        + ((b0 >> 5) & 1) * 9 - ((b0 >> 4) & 1) * 9
        + ((b1 >> 7) & 1) * 3 - ((b1 >> 6) & 1) * 3
        + ((b0 >> 7) & 1) - ((b0 >> 6) & 1)
    )


def _dst_file(*commands: bytes, header_lines: list[str] | None = None) -> bytes:
    lines = header_lines or [
        "LA:TEST",
        f"ST:{len(commands):7d}",
        "CO:  0",
        "+X:    0",
        "-X:    0",
        "+Y:    0",
        "-Y:    0",
        "AX:+    0",
        "AY:+    0",
    ]
    header = ("\r".join(lines) + "\r\x1a").encode("ascii")
    return header.ljust(DSTParser.HEADER_SIZE, b" ") + b"".join(commands)


def test_decode_matches_independent_reference_on_random_bytes() -> None:
    parser = DSTParser(bytes(DSTParser.HEADER_SIZE))
    rng = random.Random(20260727)

    for _ in range(20_000):
        b0 = rng.randrange(256)
        b1 = rng.randrange(256)
        b2 = rng.randrange(256)
        assert parser.decode_dx(b0, b1, b2) == _reference_dx(b0, b1, b2)
        assert parser.decode_dy(b0, b1, b2) == _reference_dy_cartesian(b0, b1, b2)


@pytest.mark.parametrize(
    ("b2", "expected"),
    [
        (0x03, "stitch"),
        (0x83, "jump"),
        (0x43, "sequin_mode"),
        (0xC3, "color_change"),
        (0xF3, "end"),
    ],
)
def test_command_masks(b2: int, expected: str) -> None:
    assert DSTParser.command_type(b2) == expected


def test_parse_cumulative_coordinates() -> None:
    # 0x81,0x00,0x03 => dx=+1, dy=+1.
    data = _dst_file(
        bytes((0x81, 0x00, 0x03)),
        bytes((0x81, 0x00, 0x03)),
        bytes((0x00, 0x00, 0xF3)),
    )
    commands = DSTParser(data).parse()
    assert [(c["x"], c["y"], c["type"]) for c in commands] == [
        (1, 1, "stitch"),
        (2, 2, "stitch"),
        (2, 2, "end"),
    ]


@pytest.mark.xfail(
    strict=True,
    reason="Текущий read_header() не превращает AX/AY с внутренними пробелами в int.",
)
def test_header_parsing() -> None:
    data = _dst_file(
        bytes((0, 0, 0xF3)),
        header_lines=["LA:ROSE", "ST:   1", "CO:  0", "AX:+    0"],
    )
    header = DSTParser(data).read_header()
    assert header["LA"] == "ROSE"
    assert header["ST"] == 1
    assert header["CO"] == 0
    assert header["AX"] == 0


@pytest.mark.xfail(
    strict=True,
    reason="Текущий get_bounds() не включает стартовую точку (0, 0).",
)
def test_bounds_include_origin() -> None:
    data = _dst_file(
        bytes((0x81, 0x00, 0x03)),
        bytes((0x81, 0x00, 0x03)),
        bytes((0x00, 0x00, 0xF3)),
    )
    bounds = DSTParser(data).get_bounds(DSTParser(data).parse())
    assert bounds == {
        "min_x": 0,
        "max_x": 2,
        "min_y": 0,
        "max_y": 2,
        "width": 2,
        "height": 2,
    }


@pytest.mark.xfail(
    strict=True,
    reason="Текущий parser не хранит состояние sequin mode и считает eject обычным jump.",
)
def test_sequin_eject_is_stateful() -> None:
    data = _dst_file(
        bytes((0x00, 0x00, 0x43)),  # включить sequin mode
        bytes((0x81, 0x00, 0x83)),  # в этом режиме это sequin eject
        bytes((0x00, 0x00, 0xF3)),
    )
    commands = DSTParser(data).parse()
    assert commands[1]["type"] == "sequin_eject"
