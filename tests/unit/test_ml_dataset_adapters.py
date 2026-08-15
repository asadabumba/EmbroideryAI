from __future__ import annotations

from pathlib import Path

from src.dst_parser import DSTParser
from src.ml_dataset.adapters import parse_dst


def _write_dst(
    path: Path,
    commands: list[bytes],
    *,
    declared_commands: int,
    declared_color_changes: int,
) -> None:
    header = (
        "LA:TEST\r"
        f"ST:{declared_commands:7d}\r"
        f"CO:{declared_color_changes:3d}\r"
        "+X:    1\r-X:    0\r+Y:    1\r-Y:    0\r"
        "AX:+    0\rAY:+    0\r\x1a"
    ).encode("ascii")
    path.write_bytes(
        header.ljust(DSTParser.HEADER_SIZE, b" ") + b"".join(commands)
    )


def test_dst_adapter_reports_header_count_mismatches(tmp_path: Path) -> None:
    path = tmp_path / "mismatch.dst"
    _write_dst(
        path,
        [bytes((0x81, 0x00, 0x03)), bytes((0x00, 0x00, 0xF3))],
        declared_commands=99,
        declared_color_changes=2,
    )

    parsed = parse_dst(path)
    codes = {diagnostic["code"] for diagnostic in parsed.diagnostics}
    assert "header_command_count_mismatch" in codes
    assert "header_color_change_count_mismatch" in codes


def test_dst_adapter_reports_missing_end_and_trailing_bytes(tmp_path: Path) -> None:
    path = tmp_path / "malformed.dst"
    _write_dst(
        path,
        [bytes((0x81, 0x00, 0x03))],
        declared_commands=1,
        declared_color_changes=0,
    )
    path.write_bytes(path.read_bytes() + b"x")

    parsed = parse_dst(path)
    codes = {diagnostic["code"] for diagnostic in parsed.diagnostics}
    assert "missing_end_command" in codes
    assert "trailing_command_bytes" in codes
