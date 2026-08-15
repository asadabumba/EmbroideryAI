from __future__ import annotations

import hashlib
from pathlib import Path

from src.ml_dataset.canonicalize import canonicalize_design
from src.ml_dataset.splitting import (
    assign_grouped_splits,
    leakage_overlaps,
    records_by_split,
)
from src.ml_dataset.validation import validate_dataset


def _record(name: str, source: str, *, relation: str = "original"):
    return canonicalize_design(
        source_path=f"{name}.dst",
        source_format="dst",
        content_sha256=hashlib.sha256(name.encode()).hexdigest(),
        commands=[
            {"index": 0, "type": "stitch", "dx": 1, "dy": 1, "x": 1, "y": 1},
            {"index": 1, "type": "end", "dx": 0, "dy": 0, "x": 1, "y": 1},
        ],
        source_design_key=source,
        augmentation={
            "relation": relation,
            "original_source_path": source,
            "x_translation": 0.0 if relation == "translated_variant" else None,
            "y_translation": 0.0 if relation == "translated_variant" else None,
        },
    )


def test_grouped_split_is_deterministic_and_keeps_variants_together() -> None:
    records = [_record(f"design-{index}", f"family-{index}") for index in range(10)]
    records += [
        _record("family-0-shift-a", "family-0", relation="translated_variant"),
        _record("family-0-shift-b", "family-0", relation="translated_variant"),
    ]
    first = assign_grouped_splits(records, seed=17)
    second = assign_grouped_splits(list(reversed(records)), seed=17)
    assert first == second
    splits = records_by_split(records, first)
    assert leakage_overlaps(splits) == {}
    family_zero_splits = {
        split_name
        for split_name, values in splits.items()
        if any(record.identity["source_design_key"] == "family-0" for record in values)
    }
    assert len(family_zero_splits) == 1
    assert {name: len({record.source_design_id for record in values}) for name, values in splits.items()} == {
        "train": 8,
        "validation": 1,
        "test": 1,
    }


def test_leakage_validator_detects_cross_split_group() -> None:
    original = _record("original", "same-family")
    variant = _record("variant", "same-family", relation="translated_variant")
    report = validate_dataset(
        [original, variant],
        splits={"train": [original], "validation": [variant], "test": []},
    )
    assert any(issue.code == "split_leakage" for issue in report.issues)
    assert not report.is_valid


def test_validator_detects_invalid_coordinates_and_commands() -> None:
    record = _record("bad", "bad")
    record.geometry["absolute_stitch_coordinates"][0][0] = float("nan")
    record.stitch["command_sequence"][0]["type"] = "mystery"
    report = validate_dataset([record])
    codes = {issue.code for issue in report.issues}
    assert "invalid_coordinate" in codes
    assert "non_finite_value" in codes
    assert "unknown_command" in codes


def test_validator_detects_corrupt_canonical_invariants() -> None:
    record = _record("bad-invariants", "bad-invariants")
    record.geometry["normalized_stitch_coordinates"] = [[2.0, 0.0]]
    record.geometry["stitch_deltas"] = []
    record.geometry["bounding_box"]["max_x"] = 99.0
    record.stitch["stitch_count"] = 4
    record.stitch["command_sequence"][-1]["index"] = 8
    record.statistics["command_frequencies"] = {}

    codes = {issue.code for issue in validate_dataset([record]).issues}
    assert {
        "invalid_normalized_coordinate",
        "stitch_delta_mismatch",
        "inconsistent_bounding_box",
        "inconsistent_stitch_count",
        "invalid_command_index",
        "inconsistent_command_frequencies",
    } <= codes


def test_validator_detects_inconsistent_translation_grouping() -> None:
    record = _record("variant", "family-a", relation="translated_variant")
    record.augmentation["original_source_path"] = "family-b"
    report = validate_dataset([record])
    assert any(issue.code == "inconsistent_translation_lineage" for issue in report.issues)


def test_validator_reports_missing_identity_without_crashing() -> None:
    record = _record("missing-id", "missing-id")
    del record.identity["design_id"]
    del record.identity["source_path"]

    report = validate_dataset([record])
    assert not report.is_valid
    assert any(issue.code == "corrupt_identity" for issue in report.issues)


def test_validator_detects_missing_declared_preview(tmp_path: Path) -> None:
    record = _record("missing-preview", "missing-preview")
    record.rendering["preview_path"] = "previews/missing.png"
    report = validate_dataset([record], output_root=tmp_path)
    assert any(issue.code == "missing_preview_file" for issue in report.issues)


def test_validator_detects_duplicate_and_missing_split_records() -> None:
    first = _record("first", "first")
    second = _record("second", "second")
    report = validate_dataset(
        [first, second],
        splits={"train": [first, first], "validation": [], "test": []},
    )
    codes = {issue.code for issue in report.issues}
    assert "duplicate_split_record" in codes
    assert "missing_split_record" in codes
