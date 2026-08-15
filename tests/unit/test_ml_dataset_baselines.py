import hashlib

from src.ml_dataset.baselines import run_baselines
from src.ml_dataset.canonicalize import canonicalize_design


def _record(name: str, offset: int):
    return canonicalize_design(
        source_path=f"{name}.dst",
        source_format="dst",
        content_sha256=hashlib.sha256(name.encode()).hexdigest(),
        source_design_key="one-family",
        commands=[
            {"index": 0, "type": "stitch", "dx": 1, "dy": 1, "x": 1 + offset, "y": 1},
            {"index": 1, "type": "stitch", "dx": 1, "dy": 0, "x": 2 + offset, "y": 1},
            {"index": 2, "type": "end", "dx": 0, "dy": 0, "x": 2 + offset, "y": 1},
        ],
    )


def test_baselines_reconstruct_and_compare_normalized_trajectories() -> None:
    report = run_baselines([_record("a", 0), _record("b", 10)])
    assert report["trajectory_records"] == 2
    assert report["normalized_reconstruction"]["max_error_mm"] == 0.0
    assert report["translation_invariance"]["comparable_variant_pairs"] == 1
    assert (
        report["translation_invariance"]["comparisons"][0][
            "mean_normalized_point_distance"
        ]
        == 0.0
    )
