import json
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]

RANKING_PATH = (
    BASE_DIR
    / "logs"
    / "emb_dst_ranking"
    / "ranking.json"
)

OUTPUT_PATH = (
    BASE_DIR
    / "dataset"
    / "paired"
    / "strict_pairs.json"
)


def load_ranking() -> list[dict[str, Any]]:
    if not RANKING_PATH.exists():
        raise FileNotFoundError(
            f"Файл рейтинга не найден: {RANKING_PATH}"
        )

    data = json.loads(
        RANKING_PATH.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(data, list):
        raise TypeError(
            "ranking.json должен содержать список пар"
        )

    return data


def build_strict_pairs(
    ranking: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    strict_pairs = []

    for row in ranking:
        if row.get("strict_candidate") is not True:
            continue

        emb_relative = row.get("emb_file")
        dst_relative = row.get("dst_file")

        if not isinstance(emb_relative, str):
            raise ValueError(
                "У строгой пары отсутствует emb_file"
            )

        if not isinstance(dst_relative, str):
            raise ValueError(
                "У строгой пары отсутствует dst_file"
            )

        emb_path = BASE_DIR / emb_relative
        dst_path = BASE_DIR / dst_relative

        if not emb_path.exists():
            raise FileNotFoundError(
                f"EMB-файл не найден: {emb_path}"
            )

        if not dst_path.exists():
            raise FileNotFoundError(
                f"DST-файл не найден: {dst_path}"
            )

        strict_pairs.append(
            {
                "normalized_name": row.get(
                    "normalized_name"
                ),
                "emb_file": emb_relative,
                "dst_file": dst_relative,

                "ddd_stitch_count": row.get(
                    "ddd_stitch_count"
                ),
                "dst_header_st": row.get(
                    "dst_header_st"
                ),
                "stitch_relative_error": row.get(
                    "stitch_relative_error"
                ),

                "ddd_width_dst_units": row.get(
                    "ddd_width_dst_units"
                ),
                "dst_width": row.get(
                    "dst_width"
                ),
                "width_relative_error": row.get(
                    "width_relative_error"
                ),

                "ddd_color_count": row.get(
                    "ddd_color_count"
                ),
                "ddd_color_changes": row.get(
                    "ddd_color_changes"
                ),
                "dst_color_changes": row.get(
                    "dst_color_changes"
                ),

                "quality_score": row.get(
                    "quality_score"
                ),
                "coverage_percent": row.get(
                    "coverage_percent"
                ),
                "machine": row.get("machine"),
            }
        )

    strict_pairs.sort(
        key=lambda pair: (
            str(pair["normalized_name"]),
            str(pair["emb_file"]),
            str(pair["dst_file"]),
        )
    )

    return strict_pairs


def validate_unique_pairs(
    pairs: list[dict[str, Any]],
) -> None:
    seen = set()

    for pair in pairs:
        key = (
            pair["emb_file"],
            pair["dst_file"],
        )

        if key in seen:
            raise ValueError(
                f"Обнаружена повторная пара: {key}"
            )

        seen.add(key)


def main() -> None:
    ranking = load_ranking()
    strict_pairs = build_strict_pairs(ranking)

    validate_unique_pairs(strict_pairs)

    output = {
        "schema_version": 1,
        "source_ranking": str(
            RANKING_PATH.relative_to(BASE_DIR)
        ),
        "pair_count": len(strict_pairs),
        "pairs": strict_pairs,
    }

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_PATH.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "Экспортировано строгих пар:",
        len(strict_pairs),
    )
    print("Файл:", OUTPUT_PATH)


if __name__ == "__main__":
    main()
