from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.ml_dataset.lineage import LineageIndex, PairMetadataIndex


def test_lineage_index_matches_unique_path_suffix(tmp_path: Path) -> None:
    path = tmp_path / "lineage.csv"
    path.write_text(
        "relative_source_file;relative_output_file;requested_x;requested_y;actual_x;actual_y;status;attempts\n"
        "family/original.EMB;exports/family/shifted.EMB;1.0;-2.0;1.0;-2.0;success;1\n",
        encoding="utf-8-sig",
    )

    lineage = LineageIndex.from_csv(path).lookup("family/shifted.EMB")
    assert lineage.relation == "translated_variant"
    assert lineage.source_design_key == "family/original.EMB"


def test_lineage_index_rejects_duplicate_output_rows(tmp_path: Path) -> None:
    path = tmp_path / "lineage.csv"
    header = (
        "relative_source_file;relative_output_file;requested_x;requested_y;"
        "actual_x;actual_y;status;attempts\n"
    )
    row = "family/original.EMB;family/shifted.EMB;1.0;-2.0;1.0;-2.0;success;1\n"
    path.write_text(header + row + row, encoding="utf-8-sig")

    with pytest.raises(ValueError, match="duplicate successful lineage output path"):
        LineageIndex.from_csv(path)


def test_pair_metadata_rejects_duplicate_file_mapping(tmp_path: Path) -> None:
    path = tmp_path / "pairs.json"
    row = {
        "normalized_name": "family",
        "emb_file": "dataset/raw/family.EMB",
        "dst_file": "archive/family.DST",
    }
    path.write_text(json.dumps({"pairs": [row, row]}), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate pair metadata path"):
        PairMetadataIndex.from_json(path)


def test_lineage_index_rejects_ambiguous_suffix_lookup(tmp_path: Path) -> None:
    path = tmp_path / "lineage.csv"
    path.write_text(
        "relative_source_file;relative_output_file;requested_x;requested_y;actual_x;actual_y;status;attempts\n"
        "one/original.EMB;one/shared/shifted.EMB;1;2;1;2;success;1\n"
        "two/original.EMB;two/shared/shifted.EMB;1;2;1;2;success;1\n",
        encoding="utf-8-sig",
    )

    index = LineageIndex.from_csv(path)
    with pytest.raises(ValueError, match="ambiguous lineage path"):
        index.lookup("shared/shifted.EMB")


def test_pair_metadata_rejects_incorrect_declared_count(tmp_path: Path) -> None:
    path = tmp_path / "pairs.json"
    path.write_text(
        json.dumps({"pair_count": 1, "pairs": []}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="pair_count"):
        PairMetadataIndex.from_json(path)
