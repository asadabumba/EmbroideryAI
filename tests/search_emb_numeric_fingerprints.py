import json
import math
import struct
import sys
import zlib
from collections import defaultdict
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


from src.ddd_parser import DDDParser
from src.dst_parser import DSTParser
from src.emb_reader import EmbReader


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
    / "ch_korona_numeric_search"
)

RESULT_PATH = OUTPUT_DIR / "numeric_matches.json"


def is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def add_target(
    targets: dict[float, set[str]],
    name: str,
    value: Any
) -> None:
    """Добавляет число для поиска."""

    if not is_number(value):
        return

    numeric_value = float(value)

    targets[numeric_value].add(name)


def build_targets(
    ddd: dict[str, Any],
    dst_header: dict[str, Any],
    dst_bounds: dict[str, int]
) -> dict[float, set[str]]:
    """
    Создаёт набор известных чисел и их вариантов:

    - исходные значения DDD;
    - координаты DST;
    - координаты DST × 18;
    - миллиметры;
    - размеры по границам DDD.
    """

    targets: dict[float, set[str]] = defaultdict(set)

    ddd_fields = [
        "stitch_count",
        "object_count",
        "color_count",
        "color_change_count",
        "stop_count",
        "trim_count",
        "design_left",
        "design_right",
        "design_up",
        "design_down",
        "design_width",
        "design_height",
        "end_x",
        "end_y",
        "longest_stitch",
        "shortest_stitch",
        "sequence_list_size",
    ]

    for field in ddd_fields:
        add_target(
            targets,
            f"ddd_{field}",
            ddd.get(field)
        )

    left = ddd.get("design_left")
    right = ddd.get("design_right")
    up = ddd.get("design_up")
    down = ddd.get("design_down")

    if is_number(left) and is_number(right):
        add_target(
            targets,
            "ddd_width_left_plus_right",
            abs(float(left)) + abs(float(right))
        )

    if is_number(up) and is_number(down):
        add_target(
            targets,
            "ddd_height_up_plus_down",
            abs(float(up)) + abs(float(down))
        )

    dst_values = {
        "header_ST": dst_header.get("ST"),
        "header_CO": dst_header.get("CO"),
        "header_plus_X": dst_header.get("+X"),
        "header_minus_X": dst_header.get("-X"),
        "header_plus_Y": dst_header.get("+Y"),
        "header_minus_Y": dst_header.get("-Y"),
        "min_x": dst_bounds.get("min_x"),
        "max_x": dst_bounds.get("max_x"),
        "min_y": dst_bounds.get("min_y"),
        "max_y": dst_bounds.get("max_y"),
        "width": dst_bounds.get("width"),
        "height": dst_bounds.get("height"),
    }

    for name, value in dst_values.items():

        if not is_number(value):
            continue

        value = float(value)

        add_target(
            targets,
            f"dst_{name}",
            value
        )

        add_target(
            targets,
            f"dst_{name}_x18",
            value * 18
        )

        add_target(
            targets,
            f"dst_{name}_x10",
            value * 10
        )

        add_target(
            targets,
            f"dst_{name}_millimetres",
            value * 0.1
        )

    return dict(targets)


def build_encodings(
    value: float
) -> list[dict[str, Any]]:
    """
    Кодирует одно число разными способами:

    int16/int32;
    little-endian/big-endian;
    float32/float64.
    """

    encodings = []
    seen = set()

    def add_encoding(
        name: str,
        format_code: str,
        packed_value: Any
    ) -> None:

        try:
            encoded = struct.pack(
                format_code,
                packed_value
            )
        except (
            struct.error,
            OverflowError
        ):
            return

        key = (
            name,
            encoded
        )

        if key in seen:
            return

        seen.add(key)

        encodings.append(
            {
                "format": name,
                "bytes": encoded,
            }
        )

    rounded = round(value)

    if math.isclose(
        value,
        rounded,
        abs_tol=1e-9
    ):
        integer = int(rounded)

        add_encoding(
            "int16_le",
            "<h",
            integer
        )
        add_encoding(
            "uint16_le",
            "<H",
            integer
        )
        add_encoding(
            "int16_be",
            ">h",
            integer
        )
        add_encoding(
            "uint16_be",
            ">H",
            integer
        )

        add_encoding(
            "int32_le",
            "<i",
            integer
        )
        add_encoding(
            "uint32_le",
            "<I",
            integer
        )
        add_encoding(
            "int32_be",
            ">i",
            integer
        )
        add_encoding(
            "uint32_be",
            ">I",
            integer
        )

    add_encoding(
        "float32_le",
        "<f",
        value
    )
    add_encoding(
        "float32_be",
        ">f",
        value
    )
    add_encoding(
        "float64_le",
        "<d",
        value
    )
    add_encoding(
        "float64_be",
        ">d",
        value
    )

    return encodings


def find_all(
    data: bytes,
    pattern: bytes,
    limit: int = 20
) -> list[int]:
    """Ищет все позиции байтового шаблона."""

    positions = []
    start = 0

    while len(positions) < limit:

        position = data.find(
            pattern,
            start
        )

        if position == -1:
            break

        positions.append(position)

        start = position + 1

    return positions


def get_context(
    data: bytes,
    offset: int,
    pattern_length: int,
    radius: int = 24
) -> dict[str, Any]:
    """Возвращает байты рядом с совпадением."""

    start = max(
        0,
        offset - radius
    )

    end = min(
        len(data),
        offset + pattern_length + radius
    )

    return {
        "start": start,
        "end": end,
        "hex": data[start:end].hex(" "),
    }


def build_stream_variants(
    reader: EmbReader
) -> list[dict[str, Any]]:
    """
    Берём только полезные варианты.

    Сырой Contents не анализируем, потому что
    он является сжатым потоком.
    """

    variants = []

    ddd_data = reader.extract_stream(
        DDDParser.STREAM_NAME
    )

    variants.append(
        {
            "stream": "WilcomDesignInformationDDD",
            "variant": "raw",
            "data": ddd_data,
        }
    )

    contents_raw = reader.extract_stream(
        "Contents"
    )

    contents_data = zlib.decompress(
        contents_raw[4:]
    )

    variants.append(
        {
            "stream": "Contents",
            "variant": "decompressed",
            "data": contents_data,
        }
    )

    design_document = reader.extract_stream(
        "DesignDocument"
    )

    variants.append(
        {
            "stream": "DesignDocument",
            "variant": "raw",
            "data": design_document,
        }
    )

    return variants


def match_priority(match: dict[str, Any]) -> tuple:
    """
    Сначала показываем длинные представления
    и крупные числа — у них меньше случайных
    совпадений.
    """

    return (
        -match["pattern_length"],
        -abs(match["value"]),
        match["stream"],
        match["offset"],
    )


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

    reader = EmbReader(
        EMB_PATH
    )

    ddd = DDDParser(
        EMB_PATH
    ).parse()

    dst_parser = DSTParser(
        DST_PATH.read_bytes()
    )

    dst_header = dst_parser.read_header()
    dst_commands = dst_parser.parse()

    dst_bounds = dst_parser.get_bounds(
        dst_commands
    )

    targets = build_targets(
        ddd,
        dst_header,
        dst_bounds
    )

    variants = build_stream_variants(
        reader
    )

    matches = []

    print("=" * 90)
    print("ЧИСЛОВЫЕ ОТПЕЧАТКИ CH-KORONA")
    print("=" * 90)

    print("\nКонтрольные значения:")

    print(
        "DST width:",
        dst_bounds["width"]
    )
    print(
        "DST width × 18:",
        dst_bounds["width"] * 18
    )
    print(
        "DST height:",
        dst_bounds["height"]
    )
    print(
        "DST height × 18:",
        dst_bounds["height"] * 18
    )

    for variant in variants:

        stream_data = variant["data"]

        print(
            "\nПроверяется:",
            variant["stream"],
            variant["variant"],
            "размер:",
            len(stream_data)
        )

        for value, names in targets.items():

            for encoding in build_encodings(value):

                pattern = encoding["bytes"]

                positions = find_all(
                    stream_data,
                    pattern
                )

                for position in positions:

                    match = {
                        "stream": variant["stream"],
                        "variant": variant["variant"],
                        "names": sorted(names),
                        "value": value,
                        "format": encoding["format"],
                        "pattern": pattern.hex(" "),
                        "pattern_length": len(pattern),
                        "offset": position,
                        "context": get_context(
                            stream_data,
                            position,
                            len(pattern)
                        ),
                    }

                    matches.append(match)

    matches.sort(
        key=match_priority
    )

    print("\n" + "=" * 90)
    print("НАИБОЛЕЕ ИНТЕРЕСНЫЕ СОВПАДЕНИЯ")
    print("=" * 90)

    displayed = 0

    for match in matches:

        # Убираем большую часть шума от 0 и 1.
        if (
            abs(match["value"]) <= 1
            and match["pattern_length"] < 4
        ):
            continue

        print(
            f"\n{match['stream']} "
            f"({match['variant']})"
        )

        print(
            "  Названия:",
            ", ".join(match["names"])
        )

        print(
            "  Значение:",
            match["value"]
        )

        print(
            "  Формат:",
            match["format"]
        )

        print(
            "  Offset:",
            match["offset"]
        )

        print(
            "  Байты:",
            match["pattern"]
        )

        print(
            "  Контекст:",
            match["context"]["hex"]
        )

        displayed += 1

        if displayed >= 150:
            print(
                "\nВывод ограничен первыми 150 "
                "совпадениями."
            )
            break

    result = {
        "emb": str(
            EMB_PATH.relative_to(BASE_DIR)
        ),
        "dst": str(
            DST_PATH.relative_to(BASE_DIR)
        ),
        "ddd": ddd,
        "dst_header": dst_header,
        "dst_bounds": dst_bounds,
        "targets": [
            {
                "value": value,
                "names": sorted(names),
            }
            for value, names in targets.items()
        ],
        "matches": matches,
    }

    RESULT_PATH.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print("\n" + "=" * 90)
    print("ИТОГ")
    print("=" * 90)

    print(
        "Всего найдено совпадений:",
        len(matches)
    )

    print(
        "Результат:",
        RESULT_PATH
    )


if __name__ == "__main__":
    main()