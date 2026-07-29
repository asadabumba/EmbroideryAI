from itertools import combinations
from pathlib import Path
import json
import statistics
import struct
import zlib

import olefile


BASE_DIR = Path(__file__).resolve().parents[1]

DATASET_DIR = (
    BASE_DIR
    / "dataset"
    / "raw"
)

INPUT_PATH = (
    BASE_DIR
    / "logs"
    / "controlled_shift"
    / "position_duplicate_groups.json"
)

OUTPUT_PATH = (
    BASE_DIR
    / "logs"
    / "controlled_shift"
    / "duplicate_contents_diffs.json"
)


def read_contents(path: Path) -> bytes:
    with olefile.OleFileIO(str(path)) as ole:
        if not ole.exists("Contents"):
            raise ValueError(
                "Поток Contents отсутствует"
            )

        raw = ole.openstream(
            "Contents"
        ).read()

    if len(raw) < 5:
        raise ValueError(
            "Contents слишком короткий"
        )

    expected_size = struct.unpack_from(
        "<I",
        raw,
        0,
    )[0]

    data = zlib.decompress(
        raw[4:]
    )

    if len(data) != expected_size:
        raise ValueError(
            f"Ожидалось {expected_size}, "
            f"получено {len(data)}"
        )

    return data


def find_changed_offsets(
    first: bytes,
    second: bytes,
) -> list[int]:
    common_length = min(
        len(first),
        len(second),
    )

    changed = [
        offset
        for offset in range(common_length)
        if first[offset] != second[offset]
    ]

    # Добавляем остаток более длинного файла.
    if len(first) != len(second):
        changed.extend(
            range(
                common_length,
                max(
                    len(first),
                    len(second),
                ),
            )
        )

    return changed


def make_ranges(
    offsets: list[int],
) -> list[tuple[int, int]]:
    if not offsets:
        return []

    ranges = []

    start = offsets[0]
    previous = offsets[0]

    for offset in offsets[1:]:
        if offset == previous + 1:
            previous = offset
            continue

        ranges.append(
            (start, previous + 1)
        )

        start = offset
        previous = offset

    ranges.append(
        (start, previous + 1)
    )

    return ranges


def read_signed_int16(
    data: bytes,
    offset: int,
) -> int:
    return struct.unpack_from(
        "<h",
        data,
        offset,
    )[0]


def main() -> None:
    source = json.loads(
        INPUT_PATH.read_text(
            encoding="utf-8",
        )
    )

    results = []
    errors = []

    skipped_different_offsets = 0
    skipped_same_values = 0
    skipped_different_lengths = 0

    for group_number, group in enumerate(
        source["varying_groups"],
        start=1,
    ):
        for first, second in combinations(
            group["files"],
            2,
        ):
            if (
                first["position_value"]
                == second["position_value"]
            ):
                skipped_same_values += 1
                continue

            first_offset = first[
                "position_offset"
            ]

            second_offset = second[
                "position_offset"
            ]

            if first_offset != second_offset:
                skipped_different_offsets += 1
                continue

            try:
                first_data = read_contents(
                    DATASET_DIR / first["file"]
                )

                second_data = read_contents(
                    DATASET_DIR / second["file"]
                )

                same_length = (
                    len(first_data)
                    == len(second_data)
                )

                if not same_length:
                    skipped_different_lengths += 1

                changed_offsets = (
                    find_changed_offsets(
                        first_data,
                        second_data,
                    )
                )

                changed_ranges = make_ranges(
                    changed_offsets
                )

                field_offset = first_offset

                first_raw_value = (
                    read_signed_int16(
                        first_data,
                        field_offset,
                    )
                )

                second_raw_value = (
                    read_signed_int16(
                        second_data,
                        field_offset,
                    )
                )

                field_bytes_changed = (
                    first_data[
                        field_offset:
                        field_offset + 2
                    ]
                    != second_data[
                        field_offset:
                        field_offset + 2
                    ]
                )

                ranges_near_field = []

                for start, end in changed_ranges:
                    distance = min(
                        abs(start - field_offset),
                        abs(end - field_offset),
                    )

                    if distance <= 128:
                        ranges_near_field.append(
                            {
                                "start": start,
                                "end": end,
                                "length": end - start,
                                "relative_start": (
                                    start - field_offset
                                ),
                                "relative_end": (
                                    end - field_offset
                                ),
                            }
                        )

                results.append(
                    {
                        "group_number": (
                            group_number
                        ),
                        "first_file": (
                            first["file"]
                        ),
                        "second_file": (
                            second["file"]
                        ),
                        "contents_size_first": (
                            len(first_data)
                        ),
                        "contents_size_second": (
                            len(second_data)
                        ),
                        "same_length": same_length,
                        "field_offset": (
                            field_offset
                        ),
                        "first_position_value": (
                            first_raw_value
                        ),
                        "second_position_value": (
                            second_raw_value
                        ),
                        "position_delta": (
                            second_raw_value
                            - first_raw_value
                        ),
                        "delta_divided_by_60": (
                            (
                                second_raw_value
                                - first_raw_value
                            )
                            / 60.0
                        ),
                        "field_bytes_changed": (
                            field_bytes_changed
                        ),
                        "changed_byte_count": (
                            len(changed_offsets)
                        ),
                        "changed_range_count": (
                            len(changed_ranges)
                        ),
                        "changed_ranges": [
                            {
                                "start": start,
                                "end": end,
                                "length": end - start,
                                "relative_to_field": (
                                    start
                                    - field_offset
                                ),
                            }
                            for start, end
                            in changed_ranges
                        ],
                        "ranges_near_field": (
                            ranges_near_field
                        ),
                    }
                )

            except Exception as error:
                errors.append(
                    {
                        "first_file": (
                            first["file"]
                        ),
                        "second_file": (
                            second["file"]
                        ),
                        "error": str(error),
                    }
                )

    OUTPUT_PATH.write_text(
        json.dumps(
            {
                "comparison_count": (
                    len(results)
                ),
                "skipped_same_values": (
                    skipped_same_values
                ),
                "skipped_different_offsets": (
                    skipped_different_offsets
                ),
                "skipped_different_lengths": (
                    skipped_different_lengths
                ),
                "error_count": len(errors),
                "comparisons": results,
                "errors": errors,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=" * 80)
    print("СРАВНЕНИЕ CONTENTS В DDD-ГРУППАХ")
    print("=" * 80)

    print(
        "Выполнено сравнений:",
        len(results),
    )

    print(
        "Пропущено из-за разных offset:",
        skipped_different_offsets,
    )

    print(
        "Пропущено из-за разных размеров:",
        skipped_different_lengths,
    )

    print(
        "Ошибок:",
        len(errors),
    )

    if results:
        field_changed_count = sum(
            result["field_bytes_changed"]
            for result in results
        )

        changed_counts = [
            result["changed_byte_count"]
            for result in results
        ]

        print()
        print(
            "Поле изменилось:",
            field_changed_count,
            "из",
            len(results),
        )

        print(
            "Медиана изменённых байтов:",
            statistics.median(
                changed_counts
            ),
        )

        print(
            "Минимум изменённых байтов:",
            min(changed_counts),
        )

        print(
            "Максимум изменённых байтов:",
            max(changed_counts),
        )

    print()
    print("СРАВНЕНИЯ")
    print("-" * 80)

    for result in results:
        print()
        print(
            result["first_file"],
            "<->",
            result["second_file"],
        )

        print(
            "Значения:",
            result[
                "first_position_value"
            ],
            "->",
            result[
                "second_position_value"
            ],
        )

        print(
            "Дельта:",
            result["position_delta"],
            "| /60:",
            round(
                result[
                    "delta_divided_by_60"
                ],
                4,
            ),
        )

        print(
            "Изменено байтов:",
            result["changed_byte_count"],
        )

        print(
            "Изменено диапазонов:",
            result[
                "changed_range_count"
            ],
        )

        print(
            "Диапазоны рядом с полем:",
            result[
                "ranges_near_field"
            ],
        )

    print()
    print(
        "Полный результат:",
        OUTPUT_PATH,
    )


if __name__ == "__main__":
    main()