from pathlib import Path
import json
import math
import struct
import zlib

import olefile


BASE_DIR = Path(__file__).resolve().parents[1]

DATASET_DIR = (
    BASE_DIR
    / "dataset"
    / "raw"
)

INPUT_JSON = (
    BASE_DIR
    / "logs"
    / "controlled_shift"
    / "contents_position_candidates.json"
)

OUTPUT_JSON = (
    BASE_DIR
    / "logs"
    / "controlled_shift"
    / "contents_xy_candidates.json"
)

UNITS_PER_MM = 60.0

# В нашем контрольном файле Y расположен
# через 67 байт после начала X.
Y_OFFSET_DELTA = 67


def read_contents(path: Path) -> bytes:
    with olefile.OleFileIO(str(path)) as ole:
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


def read_signed_int24_le(
    data: bytes,
    offset: int,
) -> int:
    raw_value = int.from_bytes(
        data[offset:offset + 3],
        byteorder="little",
        signed=False,
    )

    # Знаковое расширение 24-битного числа.
    if raw_value & 0x800000:
        raw_value -= 1 << 24

    return raw_value


def main() -> None:
    source = json.loads(
        INPUT_JSON.read_text(
            encoding="utf-8",
        )
    )

    results = []
    errors = []

    x_mismatches = 0
    y_signature_matches = 0
    y_zero_count = 0

    for index, record in enumerate(
        source["files_with_one_candidate"],
        start=1,
    ):
        filename = record["file"]
        path = DATASET_DIR / filename

        try:
            data = read_contents(path)

            candidate = record[
                "candidates"
            ][0]

            x_offset = candidate["offset"]
            y_offset = (
                x_offset
                + Y_OFFSET_DELTA
            )

            if y_offset + 7 > len(data):
                raise ValueError(
                    "Y-поле выходит за границы Contents"
                )

            x_value = struct.unpack_from(
                "<h",
                data,
                x_offset,
            )[0]

            y_value = read_signed_int24_le(
                data,
                y_offset,
            )

            if (
                x_value
                != candidate["signed_int16"]
            ):
                x_mismatches += 1

            # Сигнатура из контрольного файла:
            #
            # 01 [Y Y Y] 00 00 E0 10
            y_prefix_ok = (
                data[y_offset - 1]
                == 0x01
            )

            y_suffix_ok = (
                data[
                    y_offset + 3:
                    y_offset + 7
                ]
                == b"\x00\x00\xe0\x10"
            )

            y_signature_ok = (
                y_prefix_ok
                and y_suffix_ok
            )

            if y_signature_ok:
                y_signature_matches += 1

            if y_value == 0:
                y_zero_count += 1

            results.append(
                {
                    "file": filename,
                    "contents_size": len(data),
                    "x_offset": x_offset,
                    "y_offset": y_offset,
                    "x_raw": x_value,
                    "y_raw": y_value,
                    "x_mm": (
                        x_value
                        / UNITS_PER_MM
                    ),
                    "y_mm": (
                        y_value
                        / UNITS_PER_MM
                    ),
                    "y_signature_ok": (
                        y_signature_ok
                    ),
                    "y_context": data[
                        y_offset - 8:
                        y_offset + 12
                    ].hex(" "),
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
                f"{index}/"
                f"{len(source['files_with_one_candidate'])}"
            )

    result = {
        "units_per_mm": UNITS_PER_MM,
        "y_offset_delta": Y_OFFSET_DELTA,
        "file_count": len(results),
        "x_mismatches": x_mismatches,
        "y_signature_matches": (
            y_signature_matches
        ),
        "y_zero_count": y_zero_count,
        "error_count": len(errors),
        "files": results,
        "errors": errors,
    }

    OUTPUT_JSON.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("=" * 80)
    print("ПРОВЕРКА ПОЛЕЙ X И Y")
    print("=" * 80)

    print(
        "Обработано файлов:",
        len(results),
    )

    print(
        "Несовпадений X с прошлым сканером:",
        x_mismatches,
    )

    print(
        "Совпадений сигнатуры Y:",
        y_signature_matches,
        "из",
        len(results),
    )

    print(
        "Файлов с Y = 0:",
        y_zero_count,
    )

    print(
        "Ошибок:",
        len(errors),
    )

    controls = {
        record["file"]: record
        for record in results
        if record["file"] in {
            "2 мишки-страз.EMB",
            "2 мишки-страз_x.EMB",
        }
    }

    original = controls.get(
        "2 мишки-страз.EMB"
    )

    shifted = controls.get(
        "2 мишки-страз_x.EMB"
    )

    if original and shifted:
        dx_raw = (
            shifted["x_raw"]
            - original["x_raw"]
        )

        dy_raw = (
            shifted["y_raw"]
            - original["y_raw"]
        )

        dx_mm = (
            dx_raw
            / UNITS_PER_MM
        )

        dy_mm = (
            dy_raw
            / UNITS_PER_MM
        )

        length_mm = math.hypot(
            dx_mm,
            dy_mm,
        )

        print()
        print("КОНТРОЛЬНОЕ ПЕРЕМЕЩЕНИЕ")
        print("-" * 80)

        print(
            "Исходные X/Y:",
            original["x_raw"],
            original["y_raw"],
        )

        print(
            "Новые X/Y:",
            shifted["x_raw"],
            shifted["y_raw"],
        )

        print(
            "DX raw:",
            dx_raw,
        )

        print(
            "DY raw:",
            dy_raw,
        )

        print(
            "DX мм:",
            round(dx_mm, 6),
        )

        print(
            "DY мм:",
            round(dy_mm, 6),
        )

        print(
            "Длина перемещения:",
            round(length_mm, 6),
            "мм",
        )

    print()
    print(
        "Результат:",
        OUTPUT_JSON,
    )


if __name__ == "__main__":
    main()