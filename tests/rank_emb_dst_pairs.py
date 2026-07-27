import csv
import json
import math
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


from src.ddd_parser import DDDParser
from src.dst_parser import DSTParser


EMB_DIR = BASE_DIR / "dataset" / "raw"

DST_DIR = (
    BASE_DIR
    / "archive"
    / "originals"
    / "dst"
)

OUTPUT_DIR = (
    BASE_DIR
    / "logs"
    / "emb_dst_ranking"
)

CSV_PATH = OUTPUT_DIR / "ranking.csv"
JSON_PATH = OUTPUT_DIR / "ranking.json"
ERRORS_PATH = OUTPUT_DIR / "errors.json"


def normalize_name(name: str) -> str:
    """
    Приводит имена файлов к одному виду.

    Например:

    Rose.EMB
    rose.dst
    ROSE .DST

    превращаются в:

    rose
    """

    value = unicodedata.normalize(
        "NFKC",
        name
    )

    value = value.casefold()
    value = value.replace("ё", "е")

    value = re.sub(
        r"[^a-zа-я0-9]+",
        "",
        value
    )

    return value


def is_number(value: Any) -> bool:
    """
    Проверяет, является ли значение числом.

    bool отдельно исключается, потому что в Python
    True и False являются наследниками int.
    """

    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
    )


def parse_signed_number(value: Any) -> int | None:
    """
    Превращает строку DST вида:

    '+    0'
    '-   15'

    в обычное целое число.
    """

    if is_number(value):
        return int(value)

    if not isinstance(value, str):
        return None

    match = re.search(
        r"([+-]?)\s*(\d+)",
        value
    )

    if match is None:
        return None

    sign = -1 if match.group(1) == "-" else 1

    return sign * int(match.group(2))


def relative_error(
    first: float | int | None,
    second: float | int | None
) -> float | None:
    """
    Возвращает относительную ошибку.

    0.00 = полное совпадение
    0.05 = отличие на 5%
    """

    if first is None or second is None:
        return None

    first = float(first)
    second = float(second)

    if first == 0 and second == 0:
        return 0.0

    denominator = max(
        abs(first),
        abs(second),
        1.0
    )

    return abs(first - second) / denominator


def similarity_from_error(
    error: float | None,
    maximum_error: float
) -> float | None:
    """
    Переводит ошибку в значение от 0 до 1.

    При error = 0 получаем 1.
    При error >= maximum_error получаем 0.
    """

    if error is None:
        return None

    return max(
        0.0,
        1.0 - error / maximum_error
    )


def collect_files(
    folder: Path,
    extension: str
) -> list[Path]:

    if not folder.exists():
        raise FileNotFoundError(
            f"Папка не найдена: {folder}"
        )

    return sorted(
        path
        for path in folder.rglob("*")
        if path.is_file()
        and path.suffix.casefold() == extension.casefold()
    )


def build_file_index(
    files: list[Path]
) -> dict[str, list[Path]]:

    index: dict[str, list[Path]] = defaultdict(list)

    for path in files:

        key = normalize_name(
            path.stem
        )

        if key:
            index[key].append(path)

    return dict(index)


def dst_path_priority(path: Path) -> tuple:
    """
    Выбирает основной DST-файл.

    Например, при наличии:

    dst/1000.DST
    dst/.DST/1000.DST

    выбирается первый вариант.
    """

    relative_path = path.relative_to(
        DST_DIR
    )

    parent_parts = [
        part.casefold()
        for part in relative_path.parts[:-1]
    ]

    hidden_folder_penalty = int(
        ".dst" in parent_parts
    )

    return (
        hidden_folder_penalty,
        len(relative_path.parts),
        len(str(relative_path)),
        str(relative_path).casefold()
    )


def select_preferred_dst(
    paths: list[Path]
) -> Path:

    return min(
        paths,
        key=dst_path_priority
    )


def get_ddd_width_raw(
    metadata: dict[str, Any]
) -> float | None:
    """
    Возвращает ширину DDD в исходных единицах Wilcom.

    Сначала используем design_width.

    Если его нет, считаем ширину по расстояниям
    от центра:

    design_left + design_right
    """

    width = metadata.get(
        "design_width"
    )

    if is_number(width):
        return abs(float(width))

    left = metadata.get(
        "design_left"
    )

    right = metadata.get(
        "design_right"
    )

    if not is_number(left) or not is_number(right):
        return None

    return (
        abs(float(left))
        + abs(float(right))
    )


def get_ddd_height_raw(
    metadata: dict[str, Any]
) -> float | None:

    height = metadata.get(
        "design_height"
    )

    if is_number(height):
        return abs(float(height))

    up = metadata.get(
        "design_up"
    )

    down = metadata.get(
        "design_down"
    )

    if not is_number(up) or not is_number(down):
        return None

    return (
        abs(float(up))
        + abs(float(down))
    )


def wilcom_to_dst_units(
    value: float | int | None
) -> float | None:
    """
    Переводит внутренние координаты Wilcom DDD
    в единицы Tajima DST.

    Коэффициент 18 найден сравнением одинаковых
    дизайнов EMB и DST.
    """

    if value is None:
        return None

    return float(value) / 18.0


def compare_stitch_count(
    ddd_stitch_count: int | None,
    dst_header_count: int | None,
) -> dict[str, Any]:
    """
    Строго сравнивает количество стежков DDD
    только со значением ST из заголовка DST.

    Другие варианты не подбираются.
    """

    error = relative_error(
        ddd_stitch_count,
        dst_header_count,
    )

    return {
        "comparison": "header_ST",
        "dst_value": dst_header_count,
        "relative_error": error,
    }


def evaluate_colors(
    metadata: dict[str, Any],
    dst_color_changes: int | None
) -> dict[str, Any]:
    """
    Проверяет оба возможных совпадения:

    DDD color_change_count == DST CO

    DDD color_count == DST CO + 1
    """

    ddd_color_changes = metadata.get(
        "color_change_count"
    )

    ddd_color_count = metadata.get(
        "color_count"
    )

    change_match = None
    color_count_match = None

    if (
        is_number(ddd_color_changes)
        and dst_color_changes is not None
    ):
        change_match = (
            int(ddd_color_changes)
            == int(dst_color_changes)
        )

    if (
        is_number(ddd_color_count)
        and dst_color_changes is not None
    ):
        color_count_match = (
            int(ddd_color_count)
            == int(dst_color_changes) + 1
        )

    available = [
        value
        for value in (
            change_match,
            color_count_match
        )
        if value is not None
    ]

    if not available:
        similarity = None
    else:
        similarity = (
            sum(int(value) for value in available)
            / len(available)
        )

    return {
        "ddd_color_changes": ddd_color_changes,
        "ddd_color_count": ddd_color_count,
        "dst_color_changes": dst_color_changes,
        "change_match": change_match,
        "color_count_match": color_count_match,
        "similarity": similarity,
    }


def evaluate_end_position(
    metadata: dict[str, Any],
    dst_header: dict[str, Any],
    dst_width: int,
    dst_height: int
) -> dict[str, Any]:
    """
    Сравнивает конечную позицию дизайна.

    DDD предположительно хранит 0.01 мм,
    DST — 0.1 мм.
    """

    ddd_end_x = metadata.get(
        "end_x"
    )

    ddd_end_y = metadata.get(
        "end_y"
    )

    if is_number(ddd_end_x):
        ddd_end_x_dst = float(ddd_end_x) / 10
    else:
        ddd_end_x_dst = None

    if is_number(ddd_end_y):
        ddd_end_y_dst = float(ddd_end_y) / 10
    else:
        ddd_end_y_dst = None

    dst_end_x = parse_signed_number(
        dst_header.get("AX")
    )

    dst_end_y = parse_signed_number(
        dst_header.get("AY")
    )

    if (
        ddd_end_x_dst is None
        or ddd_end_y_dst is None
        or dst_end_x is None
        or dst_end_y is None
    ):
        return {
            "ddd_x": ddd_end_x_dst,
            "ddd_y": ddd_end_y_dst,
            "dst_x": dst_end_x,
            "dst_y": dst_end_y,
            "distance": None,
            "relative_error": None,
            "similarity": None,
        }

    distance = math.hypot(
        ddd_end_x_dst - dst_end_x,
        ddd_end_y_dst - dst_end_y
    )

    design_size = max(
        dst_width,
        dst_height,
        1
    )

    normalized_error = (
        distance / design_size
    )

    similarity = similarity_from_error(
        normalized_error,
        maximum_error=0.02
    )

    return {
        "ddd_x": ddd_end_x_dst,
        "ddd_y": ddd_end_y_dst,
        "dst_x": dst_end_x,
        "dst_y": dst_end_y,
        "distance": distance,
        "relative_error": normalized_error,
        "similarity": similarity,
    }


def calculate_match_metrics(
    stitch_similarity: float | None,
    width_similarity: float | None,
    height_similarity: float | None,
    color_similarity: float | None,
) -> dict[str, float]:
    """
    Возвращает три оценки:

    evidence_score:
        итоговые доказательства из всех возможных;

    quality_score:
        качество совпадения только по доступным данным;

    coverage_percent:
        доля признаков, для которых были данные.
    """

    components = [
        (stitch_similarity, 50),
        (width_similarity, 15),
        (height_similarity, 15),
        (color_similarity, 15),
    ]

    total_weight = sum(
        weight
        for _, weight in components
    )

    available_weight = 0.0
    earned_weight = 0.0

    for similarity, weight in components:
        if similarity is None:
            continue

        similarity = max(
            0.0,
            min(1.0, float(similarity)),
        )

        available_weight += weight
        earned_weight += similarity * weight

    if total_weight == 0:
        evidence_score = 0.0
        coverage_percent = 0.0
    else:
        evidence_score = (
            earned_weight / total_weight * 100
        )

        coverage_percent = (
            available_weight / total_weight * 100
        )

    if available_weight == 0:
        quality_score = 0.0
    else:
        quality_score = (
            earned_weight / available_weight * 100
        )

    return {
        "evidence_score": round(
            evidence_score,
            2,
        ),
        "quality_score": round(
            quality_score,
            2,
        ),
        "coverage_percent": round(
            coverage_percent,
            2,
        ),
    }


def calculate_score(
    stitch_similarity: float | None,
    width_similarity: float | None,
    height_similarity: float | None,
    color_similarity: float | None,
) -> float:
    """
    Оставлено для совместимости со старыми тестами.
    """

    metrics = calculate_match_metrics(
        stitch_similarity=stitch_similarity,
        width_similarity=width_similarity,
        height_similarity=height_similarity,
        color_similarity=color_similarity,
    )

    return metrics["evidence_score"]

def is_strict_candidate(
    stitch_relative_error: float | None,
    width_relative_error: float | None,
    color_change_match: bool | None,
    color_count_match: bool | None,
) -> bool:
    """
    Строгий кандидат должен одновременно иметь:

    - отличие по стежкам не больше 0.1%;
    - отличие по ширине не больше 1%;
    - точное совпадение количества смен цветов;
    - точное совпадение количества цветов.
    """

    return (
        stitch_relative_error is not None
        and stitch_relative_error <= 0.001
        and width_relative_error is not None
        and width_relative_error <= 0.01
        and color_change_match is True
        and color_count_match is True
    )


def get_verdict(
    score: float,
    strict_candidate: bool,
) -> str:
    """
    Итоговый вывод по паре.

    Строгий кандидат определяется отдельными
    проверенными условиями, а не только score.
    """

    if strict_candidate:
        return "СТРОГИЙ КАНДИДАТ"

    if score >= 70:
        return "ВОЗМОЖНО ОДИН ДИЗАЙН"

    if score >= 50:
        return "СЛАБОЕ СОВПАДЕНИЕ"

    return "РАЗНЫЕ ДИЗАЙНЫ"

def analyze_pair(
    emb_path: Path,
    dst_path: Path
) -> dict[str, Any]:

    ddd_metadata = DDDParser(
        emb_path
    ).parse()

    dst_data = dst_path.read_bytes()

    dst_parser = DSTParser(
        dst_data
    )

    dst_header = dst_parser.read_header()
    dst_commands = dst_parser.parse()

    dst_bounds = dst_parser.get_bounds(
        dst_commands
    )

    dst_types = dst_parser.count_types(
        dst_commands
    )

    ddd_stitch_count = ddd_metadata.get(
        "stitch_count"
    )

    if not is_number(ddd_stitch_count):
        ddd_stitch_count = None
    else:
        ddd_stitch_count = int(
            ddd_stitch_count
        )

    dst_header_count = parse_signed_number(
        dst_header.get("ST")
    )

    stitch_comparison = compare_stitch_count(
        ddd_stitch_count=ddd_stitch_count,
        dst_header_count=dst_header_count,
    )

    stitch_similarity = similarity_from_error(
        stitch_comparison[
            "relative_error"
        ],
        maximum_error=0.05
    )

    ddd_width_raw = get_ddd_width_raw(
        ddd_metadata
    )

    ddd_height_raw = get_ddd_height_raw(
        ddd_metadata
    )

    ddd_width_dst = wilcom_to_dst_units(
        ddd_width_raw
    )

    ddd_height_dst = wilcom_to_dst_units(
        ddd_height_raw
    )

    dst_width = dst_bounds["width"]
    dst_height = dst_bounds["height"]

    width_error = relative_error(
        ddd_width_dst,
        dst_width
    )

    height_error = relative_error(
        ddd_height_dst,
        dst_height
    )

    width_similarity = similarity_from_error(
        width_error,
        maximum_error=0.05
    )

    height_similarity = similarity_from_error(
        height_error,
        maximum_error=0.05
    )

    dst_color_changes = parse_signed_number(
        dst_header.get("CO")
    )

    colors = evaluate_colors(
        metadata=ddd_metadata,
        dst_color_changes=dst_color_changes
    )

    end_position = evaluate_end_position(
        metadata=ddd_metadata,
        dst_header=dst_header,
        dst_width=dst_width,
        dst_height=dst_height
    )

    match_metrics = calculate_match_metrics(
        stitch_similarity=stitch_similarity,
        width_similarity=width_similarity,
        height_similarity=height_similarity,
        color_similarity=colors["similarity"],
    )

    score = match_metrics["evidence_score"]

    strict_candidate = is_strict_candidate(
        stitch_relative_error=stitch_comparison[
            "relative_error"
        ],
        width_relative_error=width_error,
        color_change_match=colors[
            "change_match"
        ],
        color_count_match=colors[
            "color_count_match"
        ],
    )

    return {
        "score": score,

        "quality_score": match_metrics[
            "quality_score"
        ],

        "coverage_percent": match_metrics[
            "coverage_percent"
        ],

        "strict_candidate": strict_candidate,

        "verdict": get_verdict(
            score=score,
            strict_candidate=strict_candidate,
        ),

        "normalized_name": normalize_name(
            emb_path.stem
        ),

        "emb_file": str(
            emb_path.relative_to(BASE_DIR)
        ),

        "dst_file": str(
            dst_path.relative_to(BASE_DIR)
        ),

        "ddd_stitch_count": (
            ddd_stitch_count
        ),

        "dst_header_st": (
            dst_header_count
        ),

        "dst_command_count": len(
            dst_commands
        ),

        "dst_stitch_commands": (
            dst_types.get("stitch", 0)
        ),

        "stitch_comparison_used": (
            stitch_comparison["comparison"]
        ),

        "stitch_relative_error": (
            stitch_comparison[
                "relative_error"
            ]
        ),

        "ddd_width_raw": (
            ddd_width_raw
        ),

        "ddd_width_dst_units": (
            ddd_width_dst
        ),

        "dst_width": dst_width,

        "width_relative_error": (
            width_error
        ),

        "ddd_height_raw": (
            ddd_height_raw
        ),

        "ddd_height_dst_units": (
            ddd_height_dst
        ),

        "dst_height": dst_height,

        "height_relative_error": (
            height_error
        ),

        "ddd_color_count": (
            colors["ddd_color_count"]
        ),

        "ddd_color_changes": (
            colors["ddd_color_changes"]
        ),

        "dst_color_changes": (
            colors["dst_color_changes"]
        ),

        "color_change_match": (
            colors["change_match"]
        ),

        "color_count_match": (
            colors["color_count_match"]
        ),

        "ddd_end_x_dst_units": (
            end_position["ddd_x"]
        ),

        "ddd_end_y_dst_units": (
            end_position["ddd_y"]
        ),

        "dst_end_x": (
            end_position["dst_x"]
        ),

        "dst_end_y": (
            end_position["dst_y"]
        ),

        "end_distance": (
            end_position["distance"]
        ),

        "machine": ddd_metadata.get(
            "machine"
        ),

        "ddd_object_count": (
            ddd_metadata.get(
                "object_count"
            )
        ),

        "ddd_trim_count": (
            ddd_metadata.get(
                "trim_count"
            )
        ),

        "dst_jump_count": (
            dst_types.get("jump", 0)
        ),

        "dst_value_used": stitch_comparison["dst_value"],
    }


def print_top_results(
    results: list[dict[str, Any]],
    limit: int = 30
) -> None:

    print("\n" + "=" * 120)
    print("ЛУЧШИЕ СОВПАДЕНИЯ EMB ↔ DST")
    print("=" * 120)

    for position, result in enumerate(
        results[:limit],
        start=1
    ):

        stitch_error = result[
            "stitch_relative_error"
        ]

        width_error = result[
            "width_relative_error"
        ]

        height_error = result[
            "height_relative_error"
        ]

        def as_percent(
            value: float | None
        ) -> str:

            if value is None:
                return "нет данных"

            return f"{value * 100:.2f}%"

        print(
            f"\n{position:02d}. "
            f"{result['normalized_name']}"
        )

        print(
            f"    SCORE: {result['score']:.2f} "
            f"— {result['verdict']}"
        )

        print(
            f"    EMB: {result['emb_file']}"
        )

        print(
            f"    DST: {result['dst_file']}"
        )

        print(
            "    Стежки:",
            result["ddd_stitch_count"],
            "↔",
            result["dst_value_used"],
            f"(ошибка {as_percent(stitch_error)})"
        )

        print(
            "    Ширина:",
            result["ddd_width_dst_units"],
            "↔",
            result["dst_width"],
            f"(ошибка {as_percent(width_error)})"
        )

        print(
            "    Высота:",
            result["ddd_height_dst_units"],
            "↔",
            result["dst_height"],
            f"(ошибка {as_percent(height_error)})"
        )

        print(
            "    Цвета:",
            result["ddd_color_count"],
            "цветов /",
            result["ddd_color_changes"],
            "смен ↔",
            result["dst_color_changes"],
            "смен"
        )





def main():

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    emb_files = collect_files(
        EMB_DIR,
        ".emb"
    )

    dst_files = collect_files(
        DST_DIR,
        ".dst"
    )

    emb_index = build_file_index(
        emb_files
    )

    dst_index = build_file_index(
        dst_files
    )

    shared_names = sorted(
        set(emb_index)
        & set(dst_index)
    )

    print("EMB файлов:", len(emb_files))
    print("DST файлов:", len(dst_files))

    print(
        "Совпадающих нормализованных имён:",
        len(shared_names)
    )

    results = []
    errors = []

    total_pairs = sum(
        len(emb_index[name])
        for name in shared_names
    )

    processed = 0

    for normalized_name in shared_names:

        preferred_dst = select_preferred_dst(
            dst_index[normalized_name]
        )

        for emb_path in emb_index[
            normalized_name
        ]:

            processed += 1

            print(
                f"[{processed}/{total_pairs}] "
                f"{emb_path.name}"
            )

            try:
                result = analyze_pair(
                    emb_path=emb_path,
                    dst_path=preferred_dst
                )

                results.append(result)

            except Exception as error:
                errors.append(
                    {
                        "normalized_name": (
                            normalized_name
                        ),
                        "emb_file": str(
                            emb_path.relative_to(
                                BASE_DIR
                            )
                        ),
                        "dst_file": str(
                            preferred_dst.relative_to(
                                BASE_DIR
                            )
                        ),
                        "error_type": type(
                            error
                        ).__name__,
                        "error": str(error),
                    }
                )

                print(
                    "  ОШИБКА:",
                    type(error).__name__,
                    str(error)
                )

    results.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    if results:

        fieldnames = list(
            results[0].keys()
        )

        with CSV_PATH.open(
            "w",
            encoding="utf-8-sig",
            newline=""
        ) as csv_file:

            writer = csv.DictWriter(
                csv_file,
                fieldnames=fieldnames
            )

            writer.writeheader()
            writer.writerows(results)

    JSON_PATH.write_text(
        json.dumps(
            results,
            ensure_ascii=False,
            indent=2,
            default=str
        ),
        encoding="utf-8"
    )

    ERRORS_PATH.write_text(
        json.dumps(
            errors,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print_top_results(
        results,
        limit=30
    )

    strict_matches = [
        result
        for result in results
        if result["strict_candidate"]
    ]

    print("\n" + "=" * 120)
    print("ИТОГ")
    print("=" * 120)

    print(
        "Успешно проверено:",
        len(results)
    )

    print(
        "Ошибок:",
        len(errors)
    )

    print(
        "Строгих кандидатов:",
        len(strict_matches)
    )

    print("\nCSV:")
    print(CSV_PATH)

    print("\nJSON:")
    print(JSON_PATH)

    print("\nОшибки:")
    print(ERRORS_PATH)




if __name__ == "__main__":
    main()