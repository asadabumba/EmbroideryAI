import bz2
import gzip
import json
import lzma
import math
import struct
import sys
import zlib
from collections import Counter
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


from src.emb_reader import EmbReader
from src.ddd_parser import DDDParser
from src.dst_parser import DSTParser


EMB_PATH = (
    BASE_DIR
    / "dataset"
    / "raw"
    / "ch-korona.EMB"
)

DST_PATH = (
    BASE_DIR
    / "archive"
    / "originals"
    / "dst"
    / "ch-korona.DST"
)

OUTPUT_DIR = (
    BASE_DIR
    / "logs"
    / "ch_korona_probe"
)

RESULT_PATH = OUTPUT_DIR / "probe_result.json"


def calculate_entropy(data: bytes) -> float:
    """
    Рассчитывает энтропию Шеннона.

    Значение около 8 может означать, что данные
    сжаты, зашифрованы или имеют плотную
    бинарную структуру.
    """

    if not data:
        return 0.0

    frequencies = Counter(data)

    entropy = 0.0
    data_length = len(data)

    for count in frequencies.values():
        probability = count / data_length

        entropy -= probability * math.log2(
            probability
        )

    return entropy


def try_decompress(
    data: bytes
) -> list[dict[str, Any]]:
    """
    Пробует распаковать данные несколькими
    распространёнными алгоритмами.
    """

    attempts = [
        (
            "zlib_full",
            lambda: zlib.decompress(data)
        ),
        (
            "zlib_after_4",
            lambda: zlib.decompress(data[4:])
        ),
        (
            "gzip",
            lambda: gzip.decompress(data)
        ),
        (
            "bz2",
            lambda: bz2.decompress(data)
        ),
        (
            "lzma",
            lambda: lzma.decompress(data)
        ),
    ]

    results = []

    for method_name, function in attempts:

        try:
            decompressed = function()

        except Exception:
            continue

        results.append(
            {
                "name": method_name,
                "data": decompressed,
            }
        )

    return results


def pack_commands(
    commands: list[dict[str, Any]],
    mode: str
) -> tuple[bytes, int]:
    """
    Представляет координаты DST в разных
    бинарных форматах.
    """

    output = bytearray()

    for command in commands:

        dx = int(command["dx"])
        dy = int(command["dy"])

        x = int(command["x"])
        y = int(command["y"])

        if mode == "delta_i8_xy":

            if not (
                -128 <= dx <= 127
                and -128 <= dy <= 127
            ):
                raise ValueError(
                    "Смещения не помещаются в int8"
                )

            output.extend(
                struct.pack("<bb", dx, dy)
            )

        elif mode == "delta_i8_yx":

            if not (
                -128 <= dx <= 127
                and -128 <= dy <= 127
            ):
                raise ValueError(
                    "Смещения не помещаются в int8"
                )

            output.extend(
                struct.pack("<bb", dy, dx)
            )

        elif mode == "delta_i16_xy_le":

            output.extend(
                struct.pack("<hh", dx, dy)
            )

        elif mode == "delta_i16_yx_le":

            output.extend(
                struct.pack("<hh", dy, dx)
            )

        elif mode == "delta_i16_xy_be":

            output.extend(
                struct.pack(">hh", dx, dy)
            )

        elif mode == "absolute_i16_xy_le":

            output.extend(
                struct.pack("<hh", x, y)
            )

        elif mode == "absolute_i16_yx_le":

            output.extend(
                struct.pack("<hh", y, x)
            )

        elif mode == "absolute_i16_xy_be":

            output.extend(
                struct.pack(">hh", x, y)
            )

        elif mode == "delta_i32_xy_le":

            output.extend(
                struct.pack("<ii", dx, dy)
            )

        elif mode == "absolute_i32_xy_le":

            output.extend(
                struct.pack("<ii", x, y)
            )

        else:
            raise ValueError(
                f"Неизвестный режим: {mode}"
            )

    record_sizes = {
        "delta_i8_xy": 2,
        "delta_i8_yx": 2,

        "delta_i16_xy_le": 4,
        "delta_i16_yx_le": 4,
        "delta_i16_xy_be": 4,

        "absolute_i16_xy_le": 4,
        "absolute_i16_yx_le": 4,
        "absolute_i16_xy_be": 4,

        "delta_i32_xy_le": 8,
        "absolute_i32_xy_le": 8,
    }

    return bytes(output), record_sizes[mode]


def build_dst_representations(
    dst_data: bytes,
    commands: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Создаёт разные варианты представления
    команд и координат DST.
    """

    representations = [
        {
            "name": "raw_dst_commands",
            "data": dst_data[
                DSTParser.HEADER_SIZE:
            ],
            "record_size": 3,
        }
    ]

    modes = [
        "delta_i8_xy",
        "delta_i8_yx",

        "delta_i16_xy_le",
        "delta_i16_yx_le",
        "delta_i16_xy_be",

        "absolute_i16_xy_le",
        "absolute_i16_yx_le",
        "absolute_i16_xy_be",

        "delta_i32_xy_le",
        "absolute_i32_xy_le",
    ]

    for mode in modes:

        try:
            packed_data, record_size = (
                pack_commands(
                    commands,
                    mode
                )
            )

        except (
            ValueError,
            struct.error
        ):
            continue

        representations.append(
            {
                "name": mode,
                "data": packed_data,
                "record_size": record_size,
            }
        )

    return representations


def build_stream_variants(
    reader: EmbReader
) -> list[dict[str, Any]]:
    """
    Получает сырые и распакованные версии
    всех потоков EMB.
    """

    variants = []

    for stream_name in reader.list_streams():

        raw_data = reader.extract_stream(
            stream_name
        )

        variants.append(
            {
                "stream": stream_name,
                "variant": "raw",
                "data": raw_data,
            }
        )

        decompressed_versions = try_decompress(
            raw_data
        )

        for decompressed in decompressed_versions:

            variants.append(
                {
                    "stream": stream_name,
                    "variant": decompressed["name"],
                    "data": decompressed["data"],
                }
            )

    return variants


def search_integer(
    data: bytes,
    value: int
) -> list[dict[str, Any]]:
    """
    Ищет число внутри бинарных данных
    в нескольких форматах.
    """

    formats = [
        ("uint16_le", "<H"),
        ("int16_le", "<h"),
        ("uint16_be", ">H"),
        ("int16_be", ">h"),

        ("uint32_le", "<I"),
        ("int32_le", "<i"),
        ("uint32_be", ">I"),
        ("int32_be", ">i"),
    ]

    matches = []

    for format_name, format_code in formats:

        try:
            encoded = struct.pack(
                format_code,
                value
            )

        except struct.error:
            continue

        start_position = 0

        while True:

            position = data.find(
                encoded,
                start_position
            )

            if position == -1:
                break

            matches.append(
                {
                    "format": format_name,
                    "offset": position,
                    "bytes": encoded.hex(" "),
                }
            )

            start_position = position + 1

    return matches


def search_coordinate_fragments(
    representations: list[dict[str, Any]],
    stream_variants: list[dict[str, Any]],
    first_stitch_index: int
) -> list[dict[str, Any]]:
    """
    Ищет последовательности координат DST
    внутри потоков EMB.
    """

    matches = []

    start_indices = [
        0,
        first_stitch_index,
        10,
        50,
        100,
    ]

    record_counts = [
        4,
        8,
        16,
        32,
    ]

    for representation in representations:

        record_size = representation[
            "record_size"
        ]

        representation_data = representation[
            "data"
        ]

        for start_index in start_indices:

            for record_count in record_counts:

                start = (
                    start_index
                    * record_size
                )

                fragment_length = (
                    record_count
                    * record_size
                )

                fragment = representation_data[
                    start:
                    start + fragment_length
                ]

                if len(fragment) != fragment_length:
                    continue

                for stream_variant in stream_variants:

                    position = stream_variant[
                        "data"
                    ].find(fragment)

                    if position == -1:
                        continue

                    matches.append(
                        {
                            "representation": (
                                representation["name"]
                            ),
                            "start_command": start_index,
                            "command_count": record_count,
                            "stream": (
                                stream_variant["stream"]
                            ),
                            "stream_variant": (
                                stream_variant["variant"]
                            ),
                            "emb_offset": position,
                            "fragment": (
                                fragment[:32].hex(" ")
                            ),
                        }
                    )

    return matches


def safe_int(
    value: Any
) -> int | None:
    """
    Безопасно превращает значение в int.
    """

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return int(value)

    return None


def main():

    if not EMB_PATH.exists():
        raise FileNotFoundError(
            f"EMB не найден: {EMB_PATH}"
        )

    if not DST_PATH.exists():
        raise FileNotFoundError(
            f"DST не найден: {DST_PATH}"
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    print("=" * 80)
    print("ИССЛЕДОВАНИЕ CH-KORONA")
    print("=" * 80)

    reader = EmbReader(
        EMB_PATH
    )

    ddd_metadata = DDDParser(
        EMB_PATH
    ).parse()

    dst_data = DST_PATH.read_bytes()

    dst_parser = DSTParser(
        dst_data
    )

    dst_header = dst_parser.read_header()

    commands = dst_parser.parse()

    bounds = dst_parser.get_bounds(
        commands
    )

    command_types = dst_parser.count_types(
        commands
    )

    first_stitch_index = next(
        (
            index
            for index, command
            in enumerate(commands)
            if command["type"] == "stitch"
        ),
        0
    )

    print("\nDDD:")

    for key, value in sorted(
        ddd_metadata.items()
    ):
        print(
            f"{key:<30}: {value}"
        )

    print("\nDST:")

    print(
        "Заголовок:",
        dst_header
    )

    print(
        "Команд:",
        len(commands)
    )

    print(
        "Типы команд:",
        command_types
    )

    print(
        "Первый stitch:",
        first_stitch_index
    )

    print(
        "Границы:",
        bounds
    )

    stream_variants = build_stream_variants(
        reader
    )

    print("\n" + "=" * 80)
    print("ПОТОКИ И ВАРИАНТЫ")
    print("=" * 80)

    stream_analysis = []

    for variant in stream_variants:

        data = variant["data"]

        entropy = calculate_entropy(
            data
        )

        print(
            repr(variant["stream"]),
            variant["variant"],
            "размер:",
            len(data),
            "энтропия:",
            f"{entropy:.4f}"
        )

        stream_analysis.append(
            {
                "stream": variant["stream"],
                "variant": variant["variant"],
                "size": len(data),
                "entropy": entropy,
                "first_64_bytes": (
                    data[:64].hex(" ")
                ),
                "last_64_bytes": (
                    data[-64:].hex(" ")
                ),
            }
        )

    representations = build_dst_representations(
        dst_data,
        commands
    )

    print("\n" + "=" * 80)
    print("ПРЕДСТАВЛЕНИЯ DST")
    print("=" * 80)

    for representation in representations:

        print(
            representation["name"],
            "размер:",
            len(representation["data"]),
            "запись:",
            representation["record_size"],
            "байт"
        )

    fragment_matches = search_coordinate_fragments(
        representations,
        stream_variants,
        first_stitch_index
    )

    print("\n" + "=" * 80)
    print("СОВПАДЕНИЯ КООРДИНАТНЫХ ФРАГМЕНТОВ")
    print("=" * 80)

    if not fragment_matches:
        print(
            "Точных совпадений не найдено"
        )

    else:
        for match in fragment_matches:
            print(match)

    important_values = {
        "stitch_count": safe_int(
            ddd_metadata.get(
                "stitch_count"
            )
        ),
        "object_count": safe_int(
            ddd_metadata.get(
                "object_count"
            )
        ),
        "color_count": safe_int(
            ddd_metadata.get(
                "color_count"
            )
        ),
        "dst_width": int(
            bounds["width"]
        ),
        "dst_height": int(
            bounds["height"]
        ),
    }

    integer_matches = []

    print("\n" + "=" * 80)
    print("ПОИСК ВАЖНЫХ ЧИСЕЛ")
    print("=" * 80)

    for variant in stream_variants:

        for value_name, value in (
            important_values.items()
        ):

            if value is None:
                continue

            matches = search_integer(
                variant["data"],
                value
            )

            if not matches:
                continue

            result = {
                "stream": variant["stream"],
                "variant": variant["variant"],
                "value_name": value_name,
                "value": value,
                "matches": matches[:50],
                "total_matches": len(matches),
            }

            integer_matches.append(
                result
            )

            print(
                repr(variant["stream"]),
                variant["variant"],
                value_name,
                "=",
                value,
                "совпадений:",
                len(matches)
            )

            for match in matches[:10]:

                print(
                    "   ",
                    match
                )

    result = {
        "emb": str(
            EMB_PATH.relative_to(BASE_DIR)
        ),
        "dst": str(
            DST_PATH.relative_to(BASE_DIR)
        ),
        "ddd_metadata": ddd_metadata,
        "dst_header": dst_header,
        "dst_bounds": bounds,
        "dst_command_count": len(commands),
        "dst_command_types": command_types,
        "first_stitch_index": (
            first_stitch_index
        ),
        "streams": stream_analysis,
        "coordinate_fragment_matches": (
            fragment_matches
        ),
        "integer_matches": integer_matches,
    }

    RESULT_PATH.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
            default=str
        ),
        encoding="utf-8"
    )

    print("\n" + "=" * 80)
    print("ГОТОВО")
    print("=" * 80)

    print(
        "Результат сохранён:"
    )

    print(RESULT_PATH)


if __name__ == "__main__":
    main()