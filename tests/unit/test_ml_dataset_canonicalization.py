from __future__ import annotations

from pathlib import Path

import pytest

from src.ml_dataset.canonicalize import (
    canonicalize_design,
    deterministic_design_id,
    deterministic_source_design_id,
)
from src.ml_dataset.serialization import read_json, read_jsonl, read_record, write_record


def _commands(x_offset: int = 0, y_offset: int = 0) -> list[dict[str, object]]:
    return [
        {"index": 0, "type": "stitch", "dx": 10, "dy": 0, "x": 10 + x_offset, "y": y_offset},
        {"index": 1, "type": "jump", "dx": 0, "dy": 5, "x": 10 + x_offset, "y": 5 + y_offset},
        {"index": 2, "type": "color_change", "dx": 0, "dy": 0, "x": 10 + x_offset, "y": 5 + y_offset},
        {"index": 3, "type": "stitch", "dx": 10, "dy": 5, "x": 20 + x_offset, "y": 10 + y_offset},
        {"index": 4, "type": "end", "dx": 0, "dy": 0, "x": 20 + x_offset, "y": 10 + y_offset},
    ]


def _record(x_offset: int = 0, y_offset: int = 0):
    return canonicalize_design(
        source_path="family/design.dst",
        source_format="dst",
        content_sha256="ab" * 32,
        commands=_commands(x_offset, y_offset),
        source_design_key="family/original.emb",
        unit_mm=0.1,
    )


def test_canonical_geometry_deltas_and_statistics() -> None:
    record = _record()
    assert record.geometry["absolute_stitch_coordinates"] == [[1.0, 0.0], [2.0, 1.0]]
    assert record.geometry["stitch_deltas"] == [[1.0, 0.0], [1.0, 0.5]]
    assert record.geometry["bounding_box"] == {
        "min_x": 1.0,
        "min_y": 0.0,
        "max_x": 2.0,
        "max_y": 1.0,
    }
    assert record.geometry["width"] == 1.0
    assert record.geometry["height"] == 1.0
    assert record.stitch["stitch_count"] == 2
    assert record.stitch["jump_count"] == 1
    assert record.stitch["trim_count"] is None
    assert record.stitch["color_change_count"] == 1
    assert record.statistics["command_frequencies"]["stitch"] == 2
    assert len(record.stitch["color_blocks"]) == 2


def test_coordinate_normalization_is_translation_invariant() -> None:
    assert _record().geometry["normalized_stitch_coordinates"] == _record(100, -45).geometry[
        "normalized_stitch_coordinates"
    ]


def test_deterministic_ids() -> None:
    assert deterministic_design_id("DST", "00" * 32) == deterministic_design_id("dst", "00" * 32)
    assert deterministic_source_design_id(r"Ghost\Original.EMB") == deterministic_source_design_id(
        "ghost/original.emb"
    )
    assert _record().design_id == _record().design_id


def test_serialization_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "record.json"
    expected = _record()
    write_record(path, expected)
    assert read_record(path).to_dict() == expected.to_dict()


def test_serialization_rejects_non_finite_numbers(tmp_path: Path) -> None:
    record = _record()
    record.geometry["width"] = float("nan")
    with pytest.raises(ValueError, match="Out of range float"):
        write_record(tmp_path / "invalid.json", record)


def test_deserialization_rejects_non_standard_numeric_constants(tmp_path: Path) -> None:
    json_path = tmp_path / "invalid.json"
    jsonl_path = tmp_path / "invalid.jsonl"
    json_path.write_text('{"value": NaN}', encoding="utf-8")
    jsonl_path.write_text('{"value": Infinity}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="non-standard JSON numeric constant: NaN"):
        read_json(json_path)
    with pytest.raises(ValueError, match="non-standard JSON numeric constant: Infinity"):
        read_jsonl(jsonl_path)
