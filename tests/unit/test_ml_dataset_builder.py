from __future__ import annotations

import json
from pathlib import Path

from src.dst_parser import DSTParser
from src.ml_dataset.builder import BuildConfig, DatasetBuilder
from src.ml_dataset.serialization import read_jsonl


def _dst_file(*commands: bytes) -> bytes:
    header = (
        "LA:TEST\r"
        f"ST:{len(commands):7d}\r"
        "CO:  0\r"
        "+X:    2\r-X:    0\r+Y:    2\r-Y:    0\r"
        "AX:+    0\rAY:+    0\r\x1a"
    ).encode("ascii")
    return header.ljust(DSTParser.HEADER_SIZE, b" ") + b"".join(commands)


def _valid_dst() -> bytes:
    return _dst_file(
        bytes((0x81, 0x00, 0x03)),
        bytes((0x81, 0x00, 0x03)),
        bytes((0x00, 0x00, 0xF3)),
    )


def test_builder_is_resumable_and_deterministic(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / "sample.DST").write_bytes(_valid_dst())

    builder = DatasetBuilder(BuildConfig(input_dir=input_dir, output_dir=output_dir))
    first = builder.build()
    manifest_bytes = (output_dir / "manifest.jsonl").read_bytes()
    preview_bytes = next((output_dir / "previews").glob("*.png")).read_bytes()
    second = builder.build()

    assert first.record_count == 1
    assert first.built_count == 1
    assert first.reused_count == 0
    assert second.record_count == 1
    assert second.built_count == 0
    assert second.reused_count == 1
    assert (output_dir / "manifest.jsonl").read_bytes() == manifest_bytes
    assert next((output_dir / "previews").glob("*.png")).read_bytes() == preview_bytes
    assert json.loads((output_dir / "validation.json").read_text(encoding="utf-8"))["is_valid"]

    next((output_dir / "previews").glob("*.png")).unlink()
    third = builder.build()
    assert third.reused_count == 1
    assert next((output_dir / "previews").glob("*.png")).read_bytes() == preview_bytes


def test_builder_logs_malformed_files_without_losing_valid_files(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / "good.dst").write_bytes(_valid_dst())
    (input_dir / "bad.dst").write_bytes(b"too short")

    result = DatasetBuilder(BuildConfig(input_dir=input_dir, output_dir=output_dir)).build()
    failures = read_jsonl(output_dir / "failed.jsonl")
    records = read_jsonl(output_dir / "manifest.jsonl")

    assert result.discovered_count == 2
    assert result.record_count == 1
    assert result.failed_count == 1
    assert len(records) == 1
    assert failures[0]["source_path"] == "bad.dst"
    assert failures[0]["error_type"] == "ValueError"


def test_builder_applies_csv_lineage_to_group_variants(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    variant_dir = input_dir / "Ghost" / "positioned_variants"
    variant_dir.mkdir(parents=True)
    (variant_dir / "shifted.DST").write_bytes(_valid_dst())
    report = tmp_path / "batch_results.csv"
    report.write_text(
        "relative_source_file;relative_output_file;requested_x;requested_y;actual_x;actual_y;status;attempts\n"
        "Ghost/original.EMB;Ghost/positioned_variants/shifted.DST;-10.00;5.00;-10.00;5.00;success;1\n",
        encoding="utf-8-sig",
    )

    DatasetBuilder(
        BuildConfig(input_dir=input_dir, output_dir=output_dir, lineage_csv=report)
    ).build()
    record = read_jsonl(output_dir / "manifest.jsonl")[0]
    assert record["augmentation"]["relation"] == "translated_variant"
    assert record["augmentation"]["original_source_path"] == "Ghost/original.EMB"
    assert record["augmentation"]["x_translation"] == -10.0
    assert record["augmentation"]["y_translation"] == 5.0
