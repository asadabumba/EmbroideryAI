from collections import Counter
from pathlib import Path
import json
import struct
import zlib

import olefile


BASE_DIR = Path(__file__).resolve().parents[1]

DATASET_DIR = (
    BASE_DIR
    / "dataset"
    / "raw"
)

OUTPUT_PATH = (
    BASE_DIR
    / "logs"
    / "controlled_shift"
    / "contents_position_candidates.json"
)


PREFIX = b"\x01\x01"

SUFFIX = (
    b"\x01\x00\x00\x00"
    b"\x0e\x01"
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


def find_candidates(
    data: bytes,
) -> list[dict]:
    results = []

    for offset in range(
        2,
        len(data) - 8,
    ):
        if (
            data[offset - 2:offset]
            != PREFIX
        ):
            continue

        if (
            data[offset + 2:offset + 8]
            != SUFFIX
        ):
            continue

        signed_value = struct.unpack_from(
            "<h",
            data,
            offset,
        )[0]

        unsigned_value = struct.unpack_from(
            "<H",
            data,
            offset,
        )[0]

        context_start = max(
            0,
            offset - 8,
        )

        context_end = min(
            len(data),
            offset + 12,
        )

        results.append(
            {
                "offset": offset,
                "signed_int16": signed_value,
                "unsigned_int16": unsigned_value,
                "context": data[
                    context_start:context_end
                ].hex(" "),
            }
        )

    return results


def main() -> None:
    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    emb_files = sorted(
        path
        for path in DATASET_DIR.iterdir()
        if (
            path.is_file()
            and path.suffix.lower() == ".emb"
        )
    )

    files_with_one = []
    files_with_multiple = []
    files_without = []
    errors = []

    value_counter = Counter()

    for index, path in enumerate(
        emb_files,
        start=1,
    ):
        try:
            contents = read_contents(
                path
            )

            candidates = find_candidates(
                contents
            )

            record = {
                "file": path.name,
                "contents_size": len(contents),
                "candidate_count": len(candidates),
                "candidates": candidates,
            }

            if len(candidates) == 1:
                files_with_one.append(
                    record
                )

                value_counter[
                    candidates[0][
                        "signed_int16"
                    ]
                ] += 1

            elif len(candidates) > 1:
                files_with_multiple.append(
                    record
                )

            else:
                files_without.append(
                    path.name
                )

        except Exception as error:
            errors.append(
                {
                    "file": path.name,
                    "error": str(error),
                }
            )

        if index % 100 == 0:
            print(
                f"Обработано: "
                f"{index}/{len(emb_files)}"
            )

    result = {
        "total_emb_files": len(emb_files),
        "files_with_exactly_one_candidate": (
            len(files_with_one)
        ),
        "files_with_multiple_candidates": (
            len(files_with_multiple)
        ),
        "files_without_candidates": (
            len(files_without)
        ),
        "error_count": len(errors),
        "files_with_one_candidate": (
            files_with_one
        ),
        "files_with_multiple_candidates": (
            files_with_multiple
        ),
        "files_without_candidates": (
            files_without
        ),
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
    print("РЕЗУЛЬТАТ СКАНИРОВАНИЯ")
    print("=" * 80)

    print(
        "Всего EMB:",
        len(emb_files),
    )

    print(
        "Ровно один кандидат:",
        len(files_with_one),
    )

    print(
        "Несколько кандидатов:",
        len(files_with_multiple),
    )

    print(
        "Кандидатов нет:",
        len(files_without),
    )

    print(
        "Ошибок:",
        len(errors),
    )

    print()
    print("Самые частые значения:")

    for value, count in (
        value_counter.most_common(20)
    ):
        print(
            value,
            "—",
            count,
            "файлов",
        )

    print()
    print("Контрольные файлы:")

    for record in (
        files_with_one
        + files_with_multiple
    ):
        if "2 мишки-страз" not in record["file"]:
            continue

        print()
        print(record["file"])

        for candidate in record["candidates"]:
            print(
                " offset:",
                candidate["offset"],
                "value:",
                candidate["signed_int16"],
            )

    print()
    print(
        "Полный результат:",
        OUTPUT_PATH,
    )


if __name__ == "__main__":
    main()