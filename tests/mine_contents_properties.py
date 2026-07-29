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


RANKING_PATH = (
    BASE_DIR
    / "logs"
    / "emb_dst_ranking"
    / "ranking.json"
)

OUTPUT_DIR = (
    BASE_DIR
    / "logs"
    / "contents_property_mining"
)

RESULT_PATH = OUTPUT_DIR / "property_correlations.json"


MAX_PAIRS = 57
MIN_SUPPORT = 8


def is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def decompress_contents(emb_path: Path) -> bytes:
    reader = EmbReader(emb_path)

    raw = reader.extract_stream(
        "Contents"
    )

    if len(raw) < 5:
        raise ValueError(
            f"Contents слишком маленький: {emb_path.name}"
        )

    expected_size = struct.unpack_from(
        "<I",
        raw,
        0
    )[0]

    decompressed = zlib.decompress(
        raw[4:]
    )

    if len(decompressed) != expected_size:
        print(
            f"Предупреждение для {emb_path.name}: "
            f"ожидалось {expected_size}, "
            f"получено {len(decompressed)}"
        )

    return decompressed


def scan_numeric_records(
    data: bytes
) -> list[dict[str, Any]]:
    """
    Ищет записи предполагаемого формата:

    uint32 property_id
    uint16 flags
    uint16 type
    uint32 count
    payload

    type 2: float32
    type 3: float64
    """

    records = []

    header_size = 12

    for offset in range(
        0,
        len(data) - header_size
    ):
        try:
            property_id, flags, type_code, count = (
                struct.unpack_from(
                    "<IHHI",
                    data,
                    offset
                )
            )
        except struct.error:
            continue

        if property_id == 0:
            continue

        if property_id > 0x00FFFFFF:
            continue

        if flags != 0:
            continue

        if type_code not in (2, 3):
            continue

        if count < 1 or count > 16:
            continue

        if type_code == 2:
            value_size = 4
            format_character = "f"
        else:
            value_size = 8
            format_character = "d"

        payload_size = (
            value_size * count
        )

        payload_offset = (
            offset + header_size
        )

        payload_end = (
            payload_offset + payload_size
        )

        if payload_end > len(data):
            continue

        try:
            values = list(
                struct.unpack_from(
                    "<" + format_character * count,
                    data,
                    payload_offset
                )
            )
        except struct.error:
            continue

        if not all(
            math.isfinite(value)
            and abs(value) < 1e12
            for value in values
        ):
            continue

        # Отбрасываем совсем бессмысленные
        # денормализованные float-значения.
        meaningful = any(
            value == 0
            or abs(value) >= 1e-20
            for value in values
        )

        if not meaningful:
            continue

        records.append(
            {
                "offset": offset,
                "property_id": property_id,
                "property_id_hex": (
                    f"0x{property_id:08X}"
                ),
                "flags": flags,
                "type": type_code,
                "count": count,
                "values": values,
                "header": data[
                    offset:
                    offset + header_size
                ].hex(" "),
                "payload": data[
                    payload_offset:
                    payload_end
                ].hex(" ")
            }
        )

    return records


def build_targets(
    ddd: dict[str, Any],
    dst_bounds: dict[str, int]
) -> dict[str, float]:
    targets = {}

    def add(name: str, value: Any) -> None:
        if is_number(value):
            targets[name] = float(value)

    width_units = dst_bounds["width"]
    height_units = dst_bounds["height"]

    add(
        "dst_width_units",
        width_units
    )

    add(
        "dst_height_units",
        height_units
    )

    add(
        "dst_width_mm",
        width_units / 10
    )

    add(
        "dst_height_mm",
        height_units / 10
    )

    add(
        "ddd_stitch_count",
        ddd.get("stitch_count")
    )

    add(
        "ddd_object_count",
        ddd.get("object_count")
    )

    add(
        "ddd_color_count",
        ddd.get("color_count")
    )

    add(
        "ddd_color_change_count",
        ddd.get("color_change_count")
    )

    add(
        "ddd_stop_count",
        ddd.get("stop_count")
    )

    add(
        "ddd_trim_count",
        ddd.get("trim_count")
    )

    add(
        "ddd_design_left_raw",
        ddd.get("design_left")
    )

    add(
        "ddd_design_right_raw",
        ddd.get("design_right")
    )

    left = ddd.get("design_left")
    right = ddd.get("design_right")

    if is_number(left) and is_number(right):
        width_raw = (
            abs(float(left))
            + abs(float(right))
        )

        add(
            "ddd_width_raw",
            width_raw
        )

        add(
            "ddd_width_mm",
            width_raw / 180
        )

    return targets


def linear_regression(
    target_values: list[float],
    property_values: list[float]
) -> dict[str, float] | None:
    """
    Строит зависимость:

    property = slope * target + intercept

    Постоянные свойства отбрасываются, потому что
    их нельзя считать корреляцией с целевым полем.
    """

    if len(target_values) < 2:
        return None

    if len(target_values) != len(property_values):
        return None

    mean_x = sum(target_values) / len(
        target_values
    )

    mean_y = sum(property_values) / len(
        property_values
    )

    variance_x = sum(
        (value - mean_x) ** 2
        for value in target_values
    )

    variance_y = sum(
        (value - mean_y) ** 2
        for value in property_values
    )

    epsilon = 1e-12

    # Целевое поле не меняется между файлами.
    if variance_x <= epsilon:
        return None

    # Само найденное свойство всегда одинаковое.
    # Например, во всех файлах равно 0.
    if variance_y <= epsilon:
        return None

    covariance = sum(
        (x - mean_x) * (y - mean_y)
        for x, y in zip(
            target_values,
            property_values
        )
    )

    slope = covariance / variance_x

    intercept = (
        mean_y
        - slope * mean_x
    )

    predicted_values = [
        slope * value + intercept
        for value in target_values
    ]

    residual_error = sum(
        (actual - predicted) ** 2
        for actual, predicted in zip(
            property_values,
            predicted_values
        )
    )

    r_squared = (
        1.0
        - residual_error / variance_y
    )

    rmse = math.sqrt(
        residual_error
        / len(property_values)
    )

    return {
        "slope": slope,
        "intercept": intercept,
        "r_squared": r_squared,
        "rmse": rmse,
        "target_min": min(target_values),
        "target_max": max(target_values),
        "property_min": min(property_values),
        "property_max": max(property_values),
    }


def analyze_file(
    ranking_row: dict[str, Any]
) -> dict[str, Any]:
    emb_path = (
        BASE_DIR
        / ranking_row["emb_file"]
    )

    dst_path = (
        BASE_DIR
        / ranking_row["dst_file"]
    )

    ddd = DDDParser(
        emb_path
    ).parse()

    dst_parser = DSTParser(
        dst_path.read_bytes()
    )

    commands = dst_parser.parse()

    bounds = dst_parser.get_bounds(
        commands
    )

    contents = decompress_contents(
        emb_path
    )

    records = scan_numeric_records(
        contents
    )

    targets = build_targets(
        ddd,
        bounds
    )

    return {
        "name": emb_path.stem,
        "emb_file": str(
            emb_path.relative_to(BASE_DIR)
        ),
        "dst_file": str(
            dst_path.relative_to(BASE_DIR)
        ),
        "score": ranking_row.get("score"),
        "targets": targets,
        "record_count": len(records),
        "records": records
    }


def build_property_groups(
    files: list[dict[str, Any]]
) -> dict[
    tuple[int, int, int],
    dict[str, list[float]]
]:
    """
    Группирует значения по:

    property_id
    type
    индекс значения внутри записи
    """

    groups = defaultdict(
        lambda: defaultdict(list)
    )

    for file_data in files:
        file_name = file_data["name"]

        local_values = defaultdict(list)

        for record in file_data["records"]:
            for value_index, value in enumerate(
                record["values"]
            ):
                key = (
                    record["property_id"],
                    record["type"],
                    value_index
                )

                local_values[key].append(
                    float(value)
                )

        for key, values in local_values.items():
            # Берём только свойства, которые
            # встретились в файле ровно один раз.
            if len(values) != 1:
                continue

            groups[key][file_name].append(
                values[0]
            )

    return groups


def calculate_correlations(
    files: list[dict[str, Any]],
    groups: dict[
        tuple[int, int, int],
        dict[str, list[float]]
    ]
) -> list[dict[str, Any]]:
    file_index = {
        file_data["name"]: file_data
        for file_data in files
    }

    results = []

    for (
        property_id,
        type_code,
        value_index
    ), values_by_file in groups.items():

        support = len(
            values_by_file
        )

        if support < MIN_SUPPORT:
            continue

        target_names = set()

        for file_name in values_by_file:
            target_names.update(
                file_index[
                    file_name
                ]["targets"].keys()
            )

        for target_name in target_names:
            target_values = []
            property_values = []
            examples = []

            for file_name, values in (
                values_by_file.items()
            ):
                target = file_index[
                    file_name
                ]["targets"].get(
                    target_name
                )

                if target is None:
                    continue

                property_value = values[0]

                target_values.append(
                    float(target)
                )

                property_values.append(
                    float(property_value)
                )

                examples.append(
                    {
                        "file": file_name,
                        "target": target,
                        "property": property_value
                    }
                )

            if len(target_values) < MIN_SUPPORT:
                continue

            regression = linear_regression(
                target_values,
                property_values
            )

            if regression is None:
                continue

            # Нулевая зависимость нам неинтересна.
            if abs(regression["slope"]) < 1e-10:
                continue

            # Отбрасываем отрицательные и бессмысленные связи.
            if regression["r_squared"] <= 0:
                continue

            results.append(
                {
                    "property_id": property_id,
                    "property_id_hex": (
                        f"0x{property_id:08X}"
                    ),
                    "type": type_code,
                    "value_index": value_index,
                    "target": target_name,
                    "support": len(target_values),
                    "slope": regression["slope"],
                    "intercept": (
                        regression["intercept"]
                    ),
                    "r_squared": regression["r_squared"],
                    "rmse": regression["rmse"],
                    "property_min": regression["property_min"],
                    "property_max": regression["property_max"],
                    "examples": examples[:10]
                }
            )

    results.sort(
        key=lambda item: (
            item["r_squared"],
            item["support"]
        ),
        reverse=True
    )

    return results


def main():
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    if not RANKING_PATH.exists():
        raise FileNotFoundError(
            RANKING_PATH
        )

    ranking = json.loads(
        RANKING_PATH.read_text(
            encoding="utf-8"
        )
    )

    selected = [
        row
        for row in ranking
        if row.get("strict_candidate") is True
    ][:MAX_PAIRS]

    print(
        "Выбрано файлов:",
        len(selected)
    )

    files = []
    errors = []

    for index, row in enumerate(
        selected,
        start=1
    ):
        print(
            f"[{index}/{len(selected)}] "
            f"{row['emb_file']}"
        )

        try:
            file_result = analyze_file(
                row
            )

            files.append(
                file_result
            )

            print(
                "  найдено записей:",
                file_result["record_count"]
            )

        except Exception as error:
            errors.append(
                {
                    "emb_file": row.get(
                        "emb_file"
                    ),
                    "error_type": type(
                        error
                    ).__name__,
                    "error": str(error)
                }
            )

            print(
                "  ОШИБКА:",
                type(error).__name__,
                error
            )

    groups = build_property_groups(
        files
    )

    correlations = calculate_correlations(
        files,
        groups
    )

    print("\n" + "=" * 100)
    print("ЛУЧШИЕ СВЯЗИ PROPERTY_ID С ИЗВЕСТНЫМИ ПОЛЯМИ")
    print("=" * 100)

    displayed = 0

    for result in correlations:
        if result["r_squared"] < 0.90:
            continue

        print(
            f"\n{result['property_id_hex']} "
            f"type={result['type']} "
            f"index={result['value_index']}"
        )

        print(
            "  поле:",
            result["target"]
        )

        print(
            "  файлов:",
            result["support"]
        )

        print(
            "  R²:",
            f"{result['r_squared']:.8f}"
        )

        print(
            "  RMSE:",
            f"{result['rmse']:.8f}"
        )

        print(
            "  диапазон свойства:",
            f"{result['property_min']} .. "
            f"{result['property_max']}"
        )

        print(
            "  формула:",
            f"property = "
            f"{result['slope']:.8f} * target "
            f"+ {result['intercept']:.8f}"
        )

        for example in result[
            "examples"
        ][:5]:
            print(
                "   ",
                example
            )

        displayed += 1

        if displayed >= 40:
            break

    output = {
        "settings": {
            "strict_candidates_only": True,
            "maximum_pairs": MAX_PAIRS,
            "minimum_support": MIN_SUPPORT,
        },
        "files": files,
        "correlations": correlations,
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