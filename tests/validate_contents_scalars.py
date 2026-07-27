import json
import math
import re
import struct
import sys
import unicodedata
import zlib
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


from src.ddd_parser import DDDParser
from src.dst_parser import DSTParser
from src.emb_reader import EmbReader


RANKING_PATH = (
    BASE_DIR
    / "logs"
    / "emb_dst_ranking"
    / "ranking.json"
)

OUTPUT_DIR = (
    BASE_DIR
    / "logs"
    / "contents_scalar_validation"
)

RESULT_PATH = OUTPUT_DIR / "scalar_matches.json"


MAX_PAIRS = 30
MIN_SCORE = 99.0


def normalize_name(name: str) -> str:
    value = unicodedata.normalize(
        "NFKC",
        name
    )

    value = value.casefold()
    value = value.replace("ё", "е")

    return re.sub(
        r"[^a-zа-я0-9]+",
        "",
        value
    )


def is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def load_ranking() -> list[dict[str, Any]]:
    if not RANKING_PATH.exists():
        raise FileNotFoundError(
            f"Не найден ranking.json: {RANKING_PATH}"
        )

    return json.loads(
        RANKING_PATH.read_text(
            encoding="utf-8"
        )
    )


def resolve_path(relative_path: str) -> Path:
    return BASE_DIR / Path(relative_path)


def decompress_contents(
    emb_path: Path
) -> bytes:
    reader = EmbReader(
        emb_path
    )

    raw_data = reader.extract_stream(
        "Contents"
    )

    if len(raw_data) <= 4:
        raise ValueError(
            f"Contents слишком маленький: {emb_path.name}"
        )

    expected_size = struct.unpack_from(
        "<I",
        raw_data,
        0
    )[0]

    decompressed = zlib.decompress(
        raw_data[4:]
    )

    if len(decompressed) != expected_size:
        print(
            f"  ПРЕДУПРЕЖДЕНИЕ: "
            f"ожидалось {expected_size}, "
            f"получено {len(decompressed)}"
        )

    return decompressed


def add_target(
    targets: dict[str, float],
    name: str,
    value: Any
) -> None:
    if not is_number(value):
        return

    targets[name] = float(value)


def build_targets(
    ddd: dict[str, Any],
    dst_header: dict[str, Any],
    dst_bounds: dict[str, int]
) -> dict[str, float]:
    """
    Собирает значения, которые могут находиться
    внутри Contents.

    Основные варианты:
    - полные размеры в миллиметрах;
    - половины размеров;
    - отдельные границы;
    - значения DDD в миллиметрах;
    - количество объектов и стежков.
    """

    targets: dict[str, float] = {}

    width = float(
        dst_bounds["width"]
    )

    height = float(
        dst_bounds["height"]
    )

    add_target(
        targets,
        "dst_width_units",
        width
    )

    add_target(
        targets,
        "dst_height_units",
        height
    )

    add_target(
        targets,
        "dst_width_mm",
        width * 0.1
    )

    add_target(
        targets,
        "dst_height_mm",
        height * 0.1
    )

    add_target(
        targets,
        "dst_half_width_mm",
        width * 0.05
    )

    add_target(
        targets,
        "dst_half_height_mm",
        height * 0.05
    )

    for field in (
        "+X",
        "-X",
        "+Y",
        "-Y"
    ):
        value = dst_header.get(field)

        if is_number(value):
            add_target(
                targets,
                f"dst_{field}_units",
                value
            )

            add_target(
                targets,
                f"dst_{field}_mm",
                float(value) * 0.1
            )

    for field in (
        "design_left",
        "design_right",
        "design_up",
        "design_down"
    ):
        value = ddd.get(field)

        if not is_number(value):
            continue

        add_target(
            targets,
            f"ddd_{field}_raw",
            value
        )

        # DDD / 18 = единицы DST,
        # затем ×0.1 = миллиметры.
        add_target(
            targets,
            f"ddd_{field}_mm",
            float(value) / 180.0
        )

    left = ddd.get(
        "design_left"
    )

    right = ddd.get(
        "design_right"
    )

    if (
        is_number(left)
        and is_number(right)
    ):
        width_raw = (
            abs(float(left))
            + abs(float(right))
        )

        add_target(
            targets,
            "ddd_width_raw",
            width_raw
        )

        add_target(
            targets,
            "ddd_width_mm",
            width_raw / 180.0
        )

    up = ddd.get(
        "design_up"
    )

    down = ddd.get(
        "design_down"
    )

    if (
        is_number(up)
        and is_number(down)
    ):
        height_raw = (
            abs(float(up))
            + abs(float(down))
        )

        add_target(
            targets,
            "ddd_height_raw",
            height_raw
        )

        add_target(
            targets,
            "ddd_height_mm",
            height_raw / 180.0
        )

    for field in (
        "stitch_count",
        "object_count",
        "color_count",
        "color_change_count",
        "stop_count",
        "trim_count"
    ):
        add_target(
            targets,
            f"ddd_{field}",
            ddd.get(field)
        )

    return targets


def build_encodings(
    value: float
) -> list[dict[str, Any]]:
    """
    Используем только 4- и 8-байтовые форматы.

    Двухбайтовые совпадения дают слишком много
    случайного шума.
    """

    result = []
    seen = set()

    def add(
        name: str,
        format_code: str,
        packed_value: Any
    ) -> None:
        try:
            data = struct.pack(
                format_code,
                packed_value
            )
        except (
            struct.error,
            OverflowError
        ):
            return

        if data in seen:
            return

        seen.add(data)

        result.append(
            {
                "format": name,
                "data": data
            }
        )

    rounded = round(value)

    if math.isclose(
        value,
        rounded,
        abs_tol=1e-9
    ):
        integer = int(rounded)

        add(
            "int32_le",
            "<i",
            integer
        )

        if integer >= 0:
            add(
                "uint32_le",
                "<I",
                integer
            )

        add(
            "int32_be",
            ">i",
            integer
        )

        if integer >= 0:
            add(
                "uint32_be",
                ">I",
                integer
            )

    add(
        "float32_le",
        "<f",
        value
    )

    add(
        "float32_be",
        ">f",
        value
    )

    add(
        "float64_le",
        "<d",
        value
    )

    add(
        "float64_be",
        ">d",
        value
    )

    return result


def find_all(
    data: bytes,
    pattern: bytes,
    limit: int = 100
) -> list[int]:
    positions = []
    start = 0

    while len(positions) < limit:
        position = data.find(
            pattern,
            start
        )

        if position == -1:
            break

        positions.append(
            position
        )

        start = position + 1

    return positions


def get_context(
    data: bytes,
    offset: int,
    pattern_length: int,
    radius: int = 20
) -> dict[str, Any]:
    start = max(
        0,
        offset - radius
    )

    end = min(
        len(data),
        offset + pattern_length + radius
    )

    before = data[
        max(0, offset - 8):
        offset
    ]

    after = data[
        offset + pattern_length:
        offset + pattern_length + 8
    ]

    return {
        "start": start,
        "end": end,
        "hex": data[start:end].hex(" "),
        "before_8": before.hex(" "),
        "after_8": after.hex(" ")
    }


def analyze_pair(
    ranking_row: dict[str, Any]
) -> dict[str, Any]:
    emb_path = resolve_path(
        ranking_row["emb_file"]
    )

    dst_path = resolve_path(
        ranking_row["dst_file"]
    )

    if not emb_path.exists():
        raise FileNotFoundError(
            emb_path
        )

    if not dst_path.exists():
        raise FileNotFoundError(
            dst_path
        )

    ddd = DDDParser(
        emb_path
    ).parse()

    dst_parser = DSTParser(
        dst_path.read_bytes()
    )

    dst_header = dst_parser.read_header()

    dst_commands = dst_parser.parse()

    dst_bounds = dst_parser.get_bounds(
        dst_commands
    )

    contents = decompress_contents(
        emb_path
    )

    targets = build_targets(
        ddd,
        dst_header,
        dst_bounds
    )

    matches = []

    for target_name, value in targets.items():
        # Ноль и единица дают слишком много шума.
        if abs(value) <= 1:
            continue

        for encoding in build_encodings(
            value
        ):
            pattern = encoding["data"]

            positions = find_all(
                contents,
                pattern
            )

            for position in positions:
                matches.append(
                    {
                        "target": target_name,
                        "value": value,
                        "format": encoding["format"],
                        "pattern": pattern.hex(" "),
                        "offset": position,
                        "context": get_context(
                            contents,
                            position,
                            len(pattern)
                        )
                    }
                )

    return {
        "score": ranking_row.get(
            "score"
        ),
        "name": normalize_name(
            emb_path.stem
        ),
        "emb_file": str(
            emb_path.relative_to(BASE_DIR)
        ),
        "dst_file": str(
            dst_path.relative_to(BASE_DIR)
        ),
        "contents_size": len(contents),
        "ddd": ddd,
        "dst_header": dst_header,
        "dst_bounds": dst_bounds,
        "targets": targets,
        "matches": matches
    }


def print_pair_result(
    result: dict[str, Any]
) -> None:
    print("\n" + "=" * 90)

    print(
        result["name"],
        "SCORE:",
        result["score"]
    )

    print(
        "EMB:",
        result["emb_file"]
    )

    print(
        "DST:",
        result["dst_file"]
    )

    print(
        "DST размер:",
        f"{result['dst_bounds']['width'] * 0.1:.1f} × "
        f"{result['dst_bounds']['height'] * 0.1:.1f} мм"
    )

    print(
        "Contents:",
        result["contents_size"],
        "байт"
    )

    if not result["matches"]:
        print(
            "Значимых совпадений нет"
        )
        return

    print(
        "Совпадения:"
    )

    for match in result["matches"]:
        print(
            f"  {match['target']:<25}"
            f"{match['value']:<14}"
            f"{match['format']:<12}"
            f"offset={match['offset']}"
        )

        print(
            "    before:",
            match["context"]["before_8"]
        )

        print(
            "    after: ",
            match["context"]["after_8"]
        )


def build_summary(
    results: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Ищем свойства, которые встречаются
    сразу в нескольких разных EMB-файлах.
    """

    counter = Counter()

    examples: dict[
        tuple[str, str],
        list[dict[str, Any]]
    ] = defaultdict(list)

    for result in results:
        unique_in_file = set()

        for match in result["matches"]:
            key = (
                match["target"],
                match["format"]
            )

            unique_in_file.add(key)

            examples[key].append(
                {
                    "name": result["name"],
                    "value": match["value"],
                    "offset": match["offset"],
                    "before_8": (
                        match["context"][
                            "before_8"
                        ]
                    ),
                    "after_8": (
                        match["context"][
                            "after_8"
                        ]
                    )
                }
            )

        for key in unique_in_file:
            counter[key] += 1

    summary = []

    for (
        target,
        format_name
    ), file_count in counter.most_common():

        summary.append(
            {
                "target": target,
                "format": format_name,
                "file_count": file_count,
                "examples": examples[
                    (target, format_name)
                ][:20]
            }
        )

    return summary


def main():
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    ranking = load_ranking()

    selected = [
        row
        for row in ranking
        if float(
            row.get("score", 0)
        ) >= MIN_SCORE
    ][:MAX_PAIRS]

    print(
        "Выбрано пар:",
        len(selected)
    )

    results = []
    errors = []

    for index, row in enumerate(
        selected,
        start=1
    ):
        print(
            f"\n[{index}/{len(selected)}] "
            f"{row['emb_file']}"
        )

        try:
            result = analyze_pair(
                row
            )

            results.append(
                result
            )

            print_pair_result(
                result
            )

        except Exception as error:
            errors.append(
                {
                    "emb_file": row.get(
                        "emb_file"
                    ),
                    "dst_file": row.get(
                        "dst_file"
                    ),
                    "error_type": type(
                        error
                    ).__name__,
                    "error": str(error)
                }
            )

            print(
                "ОШИБКА:",
                type(error).__name__,
                error
            )

    summary = build_summary(
        results
    )

    print("\n" + "=" * 90)
    print("СВОДКА ПО ВСЕМ ФАЙЛАМ")
    print("=" * 90)

    for item in summary[:30]:
        print(
            f"{item['target']:<28}"
            f"{item['format']:<14}"
            f"файлов: {item['file_count']}"
        )

    output = {
        "settings": {
            "minimum_score": MIN_SCORE,
            "maximum_pairs": MAX_PAIRS
        },
        "results": results,
        "summary": summary,
        "errors": errors
    }

    RESULT_PATH.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
            default=str
        ),
        encoding="utf-8"
    )

    print("\nРезультат сохранён:")

    print(RESULT_PATH)


if __name__ == "__main__":
    main()