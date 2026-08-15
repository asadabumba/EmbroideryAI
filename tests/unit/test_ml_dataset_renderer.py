from __future__ import annotations

from pathlib import Path

import pytest

from src.ml_dataset.canonicalize import canonicalize_design
from src.ml_dataset.rendering import render_preview


def _record(with_stitches: bool = True):
    commands = []
    if with_stitches:
        commands = [
            {"index": 0, "type": "stitch", "dx": 10, "dy": 0, "x": 10, "y": 0},
            {"index": 1, "type": "color_change", "dx": 0, "dy": 0, "x": 10, "y": 0},
            {"index": 2, "type": "stitch", "dx": 0, "dy": 10, "x": 10, "y": 10},
            {"index": 3, "type": "end", "dx": 0, "dy": 0, "x": 10, "y": 10},
        ]
    return canonicalize_design(
        source_path="sample.dst",
        source_format="dst",
        content_sha256="12" * 32,
        commands=commands,
    )


def test_renderer_is_deterministic_and_headless(tmp_path: Path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    render_preview(_record(), first, width=64, height=48, padding=4)
    render_preview(_record(), second, width=64, height=48, padding=4)
    assert first.read_bytes() == second.read_bytes()
    assert first.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_renderer_rejects_empty_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no renderable"):
        render_preview(_record(False), tmp_path / "empty.png")
