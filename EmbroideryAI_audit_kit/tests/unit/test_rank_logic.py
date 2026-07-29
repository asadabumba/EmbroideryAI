from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "rank_emb_dst_pairs.py"
SPEC = importlib.util.spec_from_file_location("rank_emb_dst_pairs", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
ranker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ranker)


def test_parse_signed_number() -> None:
    assert ranker.parse_signed_number("+    7") == 7
    assert ranker.parse_signed_number("-   15") == -15
    assert ranker.parse_signed_number(4) == 4
    assert ranker.parse_signed_number(None) is None


def test_empirical_scale_function() -> None:
    assert ranker.wilcom_to_dst_units(1800) == 100
    assert ranker.wilcom_to_dst_units(None) is None


def test_best_stitch_comparison_is_optimistic_by_design() -> None:
    result = ranker.select_best_stitch_comparison(
        ddd_stitch_count=100,
        dst_header_count=110,
        dst_command_count=110,
        dst_stitch_count=100,
    )
    assert result["comparison"] == "stitch_commands"
    assert result["relative_error"] == 0


@pytest.mark.xfail(
    strict=True,
    reason="Текущий score перенормирует отсутствующие признаки и может дать 100 при неполной проверке.",
)
def test_missing_features_reduce_confidence() -> None:
    score = ranker.calculate_score(
        stitch_similarity=1.0,
        width_similarity=1.0,
        height_similarity=None,
        color_similarity=1.0,
        end_similarity=None,
    )
    assert score < 100
