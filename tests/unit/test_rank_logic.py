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


def test_stitch_comparison_uses_header_st_only() -> None:
    result = ranker.compare_stitch_count(
        ddd_stitch_count=100,
        dst_header_count=110,
    )

    assert result["comparison"] == "header_ST"
    assert result["dst_value"] == 110
    assert result["relative_error"] == pytest.approx(
        10 / 110
    )

def test_score_excludes_end_position() -> None:
    score = ranker.calculate_score(
        stitch_similarity=1.0,
        width_similarity=1.0,
        height_similarity=None,
        color_similarity=1.0,
    )

    assert score == pytest.approx(
        84.21,
        abs=0.01,
    )

def test_match_metrics_separate_quality_and_coverage() -> None:
    metrics = ranker.calculate_match_metrics(
        stitch_similarity=1.0,
        width_similarity=1.0,
        height_similarity=None,
        color_similarity=1.0,
    )

    assert metrics["evidence_score"] == pytest.approx(
        84.21,
        abs=0.01,
    )

    assert metrics["quality_score"] == pytest.approx(
        100.0,
    )

    assert metrics["coverage_percent"] == pytest.approx(
        84.21,
        abs=0.01,
    )

def test_strict_candidate_requires_all_signals() -> None:
    assert ranker.is_strict_candidate(
        stitch_relative_error=0.001,
        width_relative_error=0.01,
        color_change_match=True,
        color_count_match=True,
    )

    assert not ranker.is_strict_candidate(
        stitch_relative_error=0.002,
        width_relative_error=0.01,
        color_change_match=True,
        color_count_match=True,
    )

    assert not ranker.is_strict_candidate(
        stitch_relative_error=0.001,
        width_relative_error=None,
        color_change_match=True,
        color_count_match=True,
    )

    assert not ranker.is_strict_candidate(
        stitch_relative_error=0.001,
        width_relative_error=0.01,
        color_change_match=False,
        color_count_match=True,
    )

def test_verdict_prioritizes_strict_candidate() -> None:
    assert ranker.get_verdict(
        score=40.0,
        strict_candidate=True,
    ) == "СТРОГИЙ КАНДИДАТ"

    assert ranker.get_verdict(
        score=75.0,
        strict_candidate=False,
    ) == "ВОЗМОЖНО ОДИН ДИЗАЙН"

    assert ranker.get_verdict(
        score=55.0,
        strict_candidate=False,
    ) == "СЛАБОЕ СОВПАДЕНИЕ"

    assert ranker.get_verdict(
        score=30.0,
        strict_candidate=False,
    ) == "РАЗНЫЕ ДИЗАЙНЫ"