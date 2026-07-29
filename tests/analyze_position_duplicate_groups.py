from collections import defaultdict
from pathlib import Path
from typing import Any
import json
import sys


BASE_DIR = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(BASE_DIR),
)

from src.ddd_parser import DDDParser


INPUT_PATH = (
    BASE_DIR
    / "logs"
    / "controlled_shift"
    / "contents_position_candidates.json"
)

OUTPUT_PATH = (
    BASE_DIR
    / "logs"
    / "controlled_shift"
    / "position_duplicate_groups.json"
)

DATASET_DIR = (
    BASE_DIR
    / "dataset"
    / "raw"
)


def freeze(value: Any) -> Any:
    """
    Превращает значения метаданных
    в hashable-форму для группировки.
    """

    if isinstance(value, dict):
        return tuple(
            sorted(
                (
                    key,
                    freeze(item),
                )
                for key, item in value.items()
            )
        )

    if isinstance(value, list):
        return tuple(
            freeze(item)
            for item in value
        )

    if isinstance(value, bytes):
        return value.hex()

    return value


def make_ddd_signature(
    metadata: dict[str, Any],
) -> tuple:
    """
    Используем все распознанные DDD-поля,
    кроме имени файла.
    """

    return tuple(
        sorted(
            (
                key,
                freeze(value),
            )
            for key, value
            in metadata.items()
            if key != "filename"
        )
    )


def main() -> None:
    source = json.loads(
        INPUT_PATH.read_text(
            encoding="utf-8",
        )
    )

    groups = defaultdict(list)
    errors = []

    records = source[
        "files_with_one_candidate"
    ]

    for index, record in enumerate(
        records,
        start=1,
    ):
        filename = record["file"]
        emb_path = DATASET_DIR / filename

        try:
            metadata = DDDParser(
                emb_path
            ).parse()

            candidate = record[
                "candidates"
            ][0]

            signature = make_ddd_signature(
                metadata
            )

            groups[signature].append(
                {
                    "file": filename,
                    "position_value": (
                        candidate[
                            "signed_int16"
                        ]
                    ),
                    "position_offset": (
                        candidate["offset"]
                    ),
                    "ddd": {
                        key: value
                        for key, value
                        in metadata.items()
                        if key != "filename"
                    },
                }
            )

        except Exception as error:
            errors.append(
                {
                    "file": filename,
                    "error": str(error),
                }
            )

        if index % 100 == 0:
            print(
                f"Обработано: "
                f"{index}/{len(records)}"
            )

    duplicate_groups = []

    for items in groups.values():
        if len(items) < 2:
            continue

        values = [
            item["position_value"]
            for item in items
        ]

        duplicate_groups.append(
            {
                "file_count": len(items),
                "different_values": len(
                    set(values)
                ),
                "minimum_value": min(values),
                "maximum_value": max(values),
                "value_range": (
                    max(values) - min(values)
                ),
                "files": items,
            }
        )

    varying_groups = [
        group
        for group in duplicate_groups
        if group["different_values"] > 1
    ]

    varying_groups.sort(
        key=lambda group: (
            group["value_range"],
            group["file_count"],
        ),
        reverse=True,
    )

    result = {
        "analyzed_files": len(records),
        "error_count": len(errors),
        "exact_ddd_duplicate_groups": (
            len(duplicate_groups)
        ),
        "duplicate_groups_with_different_position": (
            len(varying_groups)
        ),
        "varying_groups": varying_groups,
        "errors": errors,
    }

    OUTPUT_PATH.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("=" * 80)
    print("АНАЛИЗ ОДИНАКОВЫХ DDD-ДИЗАЙНОВ")
    print("=" * 80)

    print(
        "Обработано файлов:",
        len(records),
    )

    print(
        "Групп с одинаковыми DDD:",
        len(duplicate_groups),
    )

    print(
        "Из них с разным position_value:",
        len(varying_groups),
    )

    print(
        "Ошибок:",
        len(errors),
    )

    print()
    print("КОНТРОЛЬНАЯ ПАРА")
    print("-" * 80)

    control_names = {
        "2 мишки-страз.EMB",
        "2 мишки-страз_x.EMB",
    }

    control_found = False

    for group in duplicate_groups:
        filenames = {
            item["file"]
            for item in group["files"]
        }

        if control_names <= filenames:
            control_found = True

            print(
                "Пара находится в одной "
                "DDD-группе: ДА"
            )

            for item in group["files"]:
                if item["file"] in control_names:
                    print(
                        item["file"],
                        "->",
                        item["position_value"],
                    )

            break

    if not control_found:
        print(
            "Пара находится в одной "
            "DDD-группе: НЕТ"
        )

    print()
    print("ПЕРВЫЕ ГРУППЫ С РАЗНЫМИ ЗНАЧЕНИЯМИ")
    print("-" * 80)

    for group_number, group in enumerate(
        varying_groups[:20],
        start=1,
    ):
        print()
        print(
            "ГРУППА:",
            group_number,
        )

        print(
            "Файлов:",
            group["file_count"],
        )

        print(
            "Диапазон:",
            group["minimum_value"],
            "->",
            group["maximum_value"],
            "разница:",
            group["value_range"],
        )

        for item in group["files"][:15]:
            print(
                " ",
                item["position_value"],
                item["file"],
            )

    print()
    print(
        "Полный результат:",
        OUTPUT_PATH,
    )


if __name__ == "__main__":
    main()