from __future__ import annotations

import json
from pathlib import Path

import pytest

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


def test_builder_groups_original_and_translated_variant(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    family_dir = input_dir / "Ghost"
    variant_dir = family_dir / "positioned_variants"
    variant_dir.mkdir(parents=True)
    (family_dir / "original.DST").write_bytes(_valid_dst())
    (variant_dir / "shifted.DST").write_bytes(
        _dst_file(
            bytes((0x01, 0x00, 0x03)),
            bytes((0x81, 0x00, 0x03)),
            bytes((0x00, 0x00, 0xF3)),
        )
    )
    report = tmp_path / "batch_results.csv"
    report.write_text(
        "relative_source_file;relative_output_file;requested_x;requested_y;actual_x;actual_y;status;attempts\n"
        "external/input/Ghost/original.DST;Ghost/positioned_variants/shifted.DST;-10.00;5.00;-10.00;5.00;success;1\n",
        encoding="utf-8-sig",
    )

    result = DatasetBuilder(
        BuildConfig(input_dir=input_dir, output_dir=output_dir, lineage_csv=report)
    ).build()
    records = read_jsonl(output_dir / "manifest.jsonl")

    assert result.validation_error_count == 0
    assert len({record["identity"]["source_design_id"] for record in records}) == 1
    assert {record["augmentation"]["relation"] for record in records} == {
        "original",
        "translated_variant",
    }
    variant = next(
        record
        for record in records
        if record["augmentation"]["relation"] == "translated_variant"
    )
    assert variant["augmentation"]["original_source_path"] == "Ghost/original.DST"
    assert variant["augmentation"]["metadata"][
        "reported_original_source_path"
    ] == "external/input/Ghost/original.DST"


def test_builder_rejects_output_directory_that_contains_input(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    with pytest.raises(ValueError, match="output directory"):
        DatasetBuilder(BuildConfig(input_dir=input_dir, output_dir=tmp_path))


def test_builder_replaces_cached_artifacts_when_source_changes(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    source = input_dir / "sample.DST"
    source.write_bytes(_valid_dst())
    builder = DatasetBuilder(BuildConfig(input_dir=input_dir, output_dir=output_dir))

    builder.build()
    first_record = read_jsonl(output_dir / "manifest.jsonl")[0]
    source.write_bytes(
        _dst_file(
            bytes((0x01, 0x00, 0x03)),
            bytes((0x81, 0x00, 0x03)),
            bytes((0x00, 0x00, 0xF3)),
        )
    )
    second = builder.build()
    second_record = read_jsonl(output_dir / "manifest.jsonl")[0]

    assert second.built_count == 1
    assert second.reused_count == 0
    assert first_record["identity"]["design_id"] != second_record["identity"][
        "design_id"
    ]
    assert len(list((output_dir / "records").glob("*.json"))) == 1
    assert len(list((output_dir / "previews").glob("*.png"))) == 1


def test_builder_groups_formats_from_pair_metadata(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / "family-a.dst").write_bytes(_valid_dst())
    (input_dir / "family-b.dst").write_bytes(
        _dst_file(
            bytes((0x01, 0x00, 0x03)),
            bytes((0x81, 0x00, 0x03)),
            bytes((0x00, 0x00, 0xF3)),
        )
    )
    pairs = tmp_path / "pairs.json"
    pairs.write_text(
        json.dumps(
            {
                "pairs": [
                    {
                        "normalized_name": "family",
                        "emb_file": "input/family-a.dst",
                        "dst_file": "input/family-b.dst",
                        "quality_score": 99.0,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = DatasetBuilder(
        BuildConfig(
            input_dir=input_dir,
            output_dir=output_dir,
            pair_metadata=pairs,
        )
    ).build()
    records = read_jsonl(output_dir / "manifest.jsonl")

    assert result.validation_error_count == 0
    assert len({record["identity"]["source_design_id"] for record in records}) == 1
    assert {
        record["augmentation"]["relation"] for record in records
    } == {"paired_format"}
    assert all(
        record["source_metadata"]["pair_metadata"]["quality_score"] == 99.0
        for record in records
    )


def test_builder_rebuilds_corrupt_cached_record(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / "sample.DST").write_bytes(_valid_dst())
    builder = DatasetBuilder(BuildConfig(input_dir=input_dir, output_dir=output_dir))
    builder.build()
    record_path = next((output_dir / "records").glob("*.json"))
    cached = json.loads(record_path.read_text(encoding="utf-8"))
    cached["geometry"]["width"] = 999.0
    del cached["identity"]["source_path"]
    record_path.write_text(json.dumps(cached), encoding="utf-8")

    result = builder.build()
    repaired = json.loads(record_path.read_text(encoding="utf-8"))

    assert result.built_count == 1
    assert result.reused_count == 0
    assert repaired["geometry"]["width"] != 999.0
