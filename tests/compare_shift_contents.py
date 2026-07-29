from pathlib import Path
import difflib
import struct
import zlib

import olefile


BASE_DIR = Path(__file__).resolve().parents[1]

ORIGINAL = (
    BASE_DIR
    / "dataset"
    / "raw"
    / "2 мишки-страз.EMB"
)

SHIFTED = (
    BASE_DIR
    / "dataset"
    / "raw"
    / "2 мишки-страз_x.EMB"
)


def read_contents(path: Path) -> bytes:
    with olefile.OleFileIO(str(path)) as ole:
        raw = ole.openstream("Contents").read()

    if len(raw) < 5:
        raise ValueError(
            f"Поток Contents слишком короткий: {path}"
        )

    expected_size = struct.unpack_from(
        "<I",
        raw,
        0,
    )[0]

    decompressed = zlib.decompress(
        raw[4:]
    )

    if len(decompressed) != expected_size:
        raise ValueError(
            f"Неверная длина Contents в {path.name}: "
            f"ожидалось {expected_size}, "
            f"получено {len(decompressed)}"
        )

    return decompressed


def common_prefix_length(
    first: bytes,
    second: bytes,
) -> int:
    limit = min(
        len(first),
        len(second),
    )

    position = 0

    while (
        position < limit
        and first[position] == second[position]
    ):
        position += 1

    return position


def common_suffix_length(
    first: bytes,
    second: bytes,
    prefix_length: int,
) -> int:
    maximum = min(
        len(first),
        len(second),
    ) - prefix_length

    suffix = 0

    while (
        suffix < maximum
        and first[-1 - suffix]
        == second[-1 - suffix]
    ):
        suffix += 1

    return suffix


def main() -> None:
    original = read_contents(
        ORIGINAL
    )

    shifted = read_contents(
        SHIFTED
    )

    prefix = common_prefix_length(
        original,
        shifted,
    )

    suffix = common_suffix_length(
        original,
        shifted,
        prefix,
    )

    print("=" * 80)
    print("СРАВНЕНИЕ РАСПАКОВАННОГО CONTENTS")
    print("=" * 80)

    print(
        "Размер оригинала:",
        len(original),
    )
    print(
        "Размер после сдвига:",
        len(shifted),
    )
    print(
        "Общий префикс:",
        prefix,
    )
    print(
        "Общий суффикс:",
        suffix,
    )

    matcher = difflib.SequenceMatcher(
        None,
        original,
        shifted,
        autojunk=False,
    )

    changed_blocks = [
        opcode
        for opcode in matcher.get_opcodes()
        if opcode[0] != "equal"
    ]

    print(
        "Изменённых блоков:",
        len(changed_blocks),
    )

    print("\nПЕРВЫЕ ИЗМЕНЁННЫЕ БЛОКИ")
    print("-" * 80)

    for (
        operation,
        old_start,
        old_end,
        new_start,
        new_end,
    ) in changed_blocks[:30]:
        old_data = original[
            old_start:old_end
        ]

        new_data = shifted[
            new_start:new_end
        ]

        print()
        print("Операция:", operation)
        print(
            "Старый диапазон:",
            old_start,
            "-",
            old_end,
        )
        print(
            "Новый диапазон:",
            new_start,
            "-",
            new_end,
        )
        print(
            "OLD:",
            old_data[:64].hex(" "),
        )
        print(
            "NEW:",
            new_data[:64].hex(" "),
        )
        print("\n" + "=" * 80)
        print("ЧИСЛОВАЯ ПРОВЕРКА")
        print("=" * 80)

        for target in (6854, 6921):
            print()
            print("TARGET:", target)

            context_start = target - 12
            context_end = target + 16

            print(
                "OLD CONTEXT:",
                original[
                    context_start:context_end
                ].hex(" "),
            )

            print(
                "NEW CONTEXT:",
                shifted[
                    context_start:context_end
                ].hex(" "),
            )

            for offset in range(
                    target - 3,
                    target + 2,
            ):
                old_i16 = struct.unpack_from(
                    "<h",
                    original,
                    offset,
                )[0]

                new_i16 = struct.unpack_from(
                    "<h",
                    shifted,
                    offset,
                )[0]

                old_i32 = struct.unpack_from(
                    "<i",
                    original,
                    offset,
                )[0]

                new_i32 = struct.unpack_from(
                    "<i",
                    shifted,
                    offset,
                )[0]

                print()
                print("OFFSET:", offset)

                print(
                    "RAW OLD:",
                    original[offset:offset + 4].hex(" "),
                )

                print(
                    "RAW NEW:",
                    shifted[offset:offset + 4].hex(" "),
                )

                print(
                    "INT16:",
                    old_i16,
                    "->",
                    new_i16,
                    "DELTA:",
                    new_i16 - old_i16,
                )

                print(
                    "INT32:",
                    old_i32,
                    "->",
                    new_i32,
                    "DELTA:",
                    new_i32 - old_i32,
                )


if __name__ == "__main__":
    main()