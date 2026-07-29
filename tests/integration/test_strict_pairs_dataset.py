import json
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[2]

STRICT_PAIRS_PATH = (
    BASE_DIR
    / "dataset"
    / "paired"
    / "strict_pairs.json"
)

RANKING_PATH = (
    BASE_DIR
    / "logs"
    / "emb_dst_ranking"
    / "ranking.json"
)


def load_json(path: Path) -> Any:
    assert path.exists(), (
        f"Файл не найден: {path}"
    )

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def test_strict_pairs_dataset_matches_ranking() -> None:
    dataset = load_json(
        STRICT_PAIRS_PATH
    )

    ranking = load_json(
        RANKING_PATH
    )

    assert dataset["schema_version"] == 1

    pairs = dataset["pairs"]

    expected_rows = [
        row
        for row in ranking
        if row.get("strict_candidate") is True
    ]

    assert dataset["pair_count"] == len(pairs)
    assert len(pairs) == len(expected_rows)

    actual_keys = {
        (
            pair["emb_file"],
            pair["dst_file"],
        )
        for pair in pairs
    }

    expected_keys = {
        (
            row["emb_file"],
            row["dst_file"],
        )
        for row in expected_rows
    }

    assert len(actual_keys) == len(pairs)
    assert actual_keys == expected_keys

    sorted_pairs = sorted(
        pairs,
        key=lambda pair: (
            str(pair["normalized_name"]),
            str(pair["emb_file"]),
            str(pair["dst_file"]),
        ),
    )

    assert pairs == sorted_pairs

    for pair in pairs:
        emb_path = (
            BASE_DIR
            / pair["emb_file"]
        )

        dst_path = (
            BASE_DIR
            / pair["dst_file"]
        )

        assert emb_path.exists(), emb_path
        assert dst_path.exists(), dst_path

        assert (
            pair["stitch_relative_error"]
            <= 0.001
        )

        assert (
            pair["width_relative_error"]
            <= 0.01
        )

        assert (
            pair["ddd_color_changes"]
            == pair["dst_color_changes"]
        )

        assert (
            pair["ddd_color_count"]
            == pair["dst_color_changes"] + 1
        )