from __future__ import annotations

import hashlib

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
    assert "unknown_command" in codes
