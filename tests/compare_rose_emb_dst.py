import json
import re
import sys
import zlib
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
    / "Rose.EMB"
)

DST_PATH = (
    BASE_DIR
    / "archive"
    / "originals"
    / "dst"
    / "rose.dst"
)

OUTPUT_DIR = (
    BASE_DIR
    / "logs"
    / "rose_emb_dst_comparison"
)

STREAMS_DIR = OUTPUT_DIR / "streams"

SUMMARY_PATH = OUTPUT_DIR / "summary.json"


def format_size(size: int) -> str:
    """Красиво форматирует размер файла."""

    if size < 1024:
        return f"{size} байт"

    if size < 1024 ** 2:
        return f"{size / 1024:.2f} КБ"

    return f"{size / 1024 ** 2:.2f} МБ"


def safe_filename(stream_name: str) -> str:
    """
    Превращает имя OLE-потока в безопасное имя файла.
    """

    result = stream_name

    result = result.replace("\x05", "05_")
    result = result.replace("/", "__")
    result = result.replace("\\", "__")

    result = re.sub(
        r"[^a-zA-Zа-яА-Я0-9_.-]+",
        "_",
        result
    )

    return result.strip("_") or "unnamed_stream"


def try_decompress(data: bytes) -> list[dict[str, Any]]:
    """
    Пытается распаковать поток через zlib.

    Проверяем два варианта:
    1. zlib начинается с первого байта;
    2. первые четыре байта являются служебным заголовком.
    """

    results = []

    attempts = [
        ("zlib_full", data),
        ("zlib_after_4_bytes", data[4:]),
    ]

    for method, candidate in attempts:

        if not candidate:
            continue

        try:
            decompressed = zlib.decompress(candidate)

        except zlib.error:
            continue

        results.append(
            {
                "method": method,
                "data": decompressed,
            }
        )

    return results


def get_stream_basename(stream_name: str) -> str:
    """Возвращает последнее имя из пути OLE-потока."""

    return stream_name.replace("\\", "/").split("/")[-1]


def find_stream(
    stream_names: list[str],
    target_name: str
) -> str | None:
    """
    Ищет поток без учёта регистра и управляющего байта 0x05.
    """

    target = target_name.casefold()

    for stream_name in stream_names:

        basename = get_stream_basename(stream_name)

        normalized = (
            basename
            .replace("\x05", "")
            .casefold()
        )

        if normalized == target:
            return stream_name

    return None


def compare_value(
    title: str,
    emb_value: Any,
    dst_value: Any
) -> dict[str, Any]:
    """Печатает и возвращает сравнение двух значений."""

    same = emb_value == dst_value

    status = "СОВПАДАЕТ" if same else "ОТЛИЧАЕТСЯ"

    print(
        f"{title:<35}"
        f"EMB={str(emb_value):<12}"
        f"DST={str(dst_value):<12}"
        f"{status}"
    )

    return {
        "emb": emb_value,
        "dst": dst_value,
        "same": same,
    }


def get_ddd_dimensions(
    metadata: dict[str, Any]
) -> dict[str, Any]:
    """
    Рассчитывает несколько вариантов размеров из DDD.

    Это нужно, потому что мы пока ещё проверяем,
    в каких единицах Wilcom хранит размеры.
    """

    left = metadata.get("design_left")
    right = metadata.get("design_right")
    up = metadata.get("design_up")
    down = metadata.get("design_down")

    result = {
        "design_width": metadata.get("design_width"),
        "design_height": metadata.get("design_height"),
        "width_from_bounds": None,
        "height_from_bounds": None,
    }

    if isinstance(left, int) and isinstance(right, int):
        result["width_from_bounds"] = abs(right - left)

    if isinstance(up, int) and isinstance(down, int):
        result["height_from_bounds"] = abs(up - down)

    return result


def extract_streams(
    reader: EmbReader,
    stream_names: list[str]
) -> list[dict[str, Any]]:
    """
    Извлекает все потоки Rose.EMB.

    Сохраняет:
    - сырой поток;
    - распакованный поток, если сработал zlib.
    """

    STREAMS_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    inventory = []

    print("\n" + "=" * 80)
    print("ПОТОКИ ROSE.EMB")
    print("=" * 80)

    for index, stream_name in enumerate(stream_names):

        raw_data = reader.extract_stream(
            stream_name
        )

        safe_name = safe_filename(
            stream_name
        )

        raw_path = (
            STREAMS_DIR
            / f"{index:02d}_{safe_name}.bin"
        )

        raw_path.write_bytes(raw_data)

        print(
            f"\n[{index:02d}] {stream_name}"
        )

        print(
            "  Размер:",
            format_size(len(raw_data))
        )

        print(
            "  Первые 32 байта:",
            raw_data[:32].hex(" ")
        )

        stream_info = {
            "index": index,
            "name": stream_name,
            "raw_size": len(raw_data),
            "raw_path": str(
                raw_path.relative_to(BASE_DIR)
            ),
            "first_32_bytes": raw_data[:32].hex(" "),
            "decompressed": [],
        }

        decompressed_versions = try_decompress(
            raw_data
        )

        for version_number, version in enumerate(
            decompressed_versions
        ):

            method = version["method"]
            decompressed_data = version["data"]

            decompressed_path = (
                STREAMS_DIR
                / (
                    f"{index:02d}_{safe_name}"
                    f"__{method}.bin"
                )
            )

            decompressed_path.write_bytes(
                decompressed_data
            )

            print(
                f"  Распакован ({method}):",
                format_size(len(decompressed_data))
            )

            stream_info["decompressed"].append(
                {
                    "method": method,
                    "size": len(decompressed_data),
                    "path": str(
                        decompressed_path.relative_to(
                            BASE_DIR
                        )
                    ),
                    "first_32_bytes": (
                        decompressed_data[:32].hex(" ")
                    ),
                }
            )

        inventory.append(stream_info)

    return inventory


def build_stream_variants(
    reader: EmbReader,
    stream_names: list[str]
) -> list[dict[str, Any]]:
    """
    Собирает сырые и распакованные версии потоков
    для поиска DST-последовательностей.
    """

    variants = []

    for stream_name in stream_names:

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

        for decompressed in try_decompress(raw_data):

            variants.append(
                {
                    "stream": stream_name,
                    "variant": decompressed["method"],
                    "data": decompressed["data"],
                }
            )

    return variants


def search_dst_fragments(
    dst_data: bytes,
    stream_variants: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Ищет точные фрагменты DST-команд внутри потоков EMB.

    Если совпадений нет — это нормально.
    EMB может хранить координаты в другом формате.
    """

    command_data = dst_data[
        DSTParser.HEADER_SIZE:
    ]

    fragment_length = 48

    candidate_offsets = [
        0,
        300 * 3,
        1000 * 3,
        3000 * 3,
        max(
            0,
            len(command_data) // 2
            - fragment_length // 2
        ),
    ]

    found = []

    print("\n" + "=" * 80)
    print("ПОИСК ФРАГМЕНТОВ DST ВНУТРИ EMB")
    print("=" * 80)

    for source_offset in candidate_offsets:

        source_offset -= source_offset % 3

        fragment = command_data[
            source_offset:
            source_offset + fragment_length
        ]

        if len(fragment) < fragment_length:
            continue

        fragment_found = False

        print(
            f"\nDST offset {source_offset}: "
            f"{fragment[:12].hex(' ')} ..."
        )

        for variant in stream_variants:

            position = variant["data"].find(
                fragment
            )

            if position == -1:
                continue

            fragment_found = True

            result = {
                "dst_offset": source_offset,
                "stream": variant["stream"],
                "variant": variant["variant"],
                "emb_offset": position,
                "length": fragment_length,
            }

            found.append(result)

            print(
                "  НАЙДЕНО:",
                variant["stream"],
                f"({variant['variant']})",
                "offset:",
                position
            )

        if not fragment_found:
            print(
                "  Точного совпадения нет"
            )

    return found


def main():

    print("=" * 80)
    print("СРАВНЕНИЕ ROSE.EMB И ROSE.DST")
    print("=" * 80)

    if not EMB_PATH.exists():
        raise FileNotFoundError(
            f"EMB-файл не найден: {EMB_PATH}"
        )

    if not DST_PATH.exists():
        raise FileNotFoundError(
            f"DST-файл не найден: {DST_PATH}"
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # ---------------------------------------------------------
    # Читаем EMB
    # ---------------------------------------------------------

    emb_reader = EmbReader(
        EMB_PATH
    )

    emb_basic_metadata = (
        emb_reader.get_metadata()
    )

    ddd_metadata = DDDParser(
        EMB_PATH
    ).parse()

    stream_names = (
        emb_reader.list_streams()
    )

    # ---------------------------------------------------------
    # Читаем DST
    # ---------------------------------------------------------

    dst_data = DST_PATH.read_bytes()

    dst_parser = DSTParser(
        dst_data
    )

    dst_header = (
        dst_parser.read_header()
    )

    dst_commands = (
        dst_parser.parse()
    )

    dst_bounds = (
        dst_parser.get_bounds(
            dst_commands
        )
    )

    dst_command_types = (
        dst_parser.count_types(
            dst_commands
        )
    )

    # ---------------------------------------------------------
    # Основная информация
    # ---------------------------------------------------------

    print("\nEMB файл:")
    print(EMB_PATH)

    print(
        "Размер:",
        format_size(
            emb_basic_metadata["size_bytes"]
        )
    )

    print("\nDST файл:")
    print(DST_PATH)

    print(
        "Размер:",
        format_size(len(dst_data))
    )

    print("\nПотоков в EMB:")
    print(len(stream_names))

    for stream_name in stream_names:
        print(" -", repr(stream_name))

    # ---------------------------------------------------------
    # DDD metadata
    # ---------------------------------------------------------

    print("\n" + "=" * 80)
    print("МЕТАДАННЫЕ DDD")
    print("=" * 80)

    for key, value in sorted(
        ddd_metadata.items()
    ):
        print(
            f"{key:<30}: {value}"
        )

    # ---------------------------------------------------------
    # DST metadata
    # ---------------------------------------------------------

    print("\n" + "=" * 80)
    print("МЕТАДАННЫЕ DST")
    print("=" * 80)

    for key, value in dst_header.items():
        print(
            f"{key:<10}: {value}"
        )

    print("\nТипы команд:")

    for key, value in dst_command_types.items():
        print(
            f"{key:<20}: {value}"
        )

    print("\nГраницы DST:")

    for key, value in dst_bounds.items():
        print(
            f"{key:<20}: {value}"
        )

    # ---------------------------------------------------------
    # Сравнение
    # ---------------------------------------------------------

    print("\n" + "=" * 80)
    print("СРАВНЕНИЕ EMB И DST")
    print("=" * 80)

    comparisons = {}

    comparisons["stitch_count_vs_header"] = compare_value(
        "Количество: DDD vs DST ST",
        ddd_metadata.get("stitch_count"),
        dst_header.get("ST")
    )

    comparisons["stitch_count_vs_commands"] = compare_value(
        "DDD vs все DST-команды",
        ddd_metadata.get("stitch_count"),
        len(dst_commands)
    )

    comparisons["stitch_count_vs_stitches"] = compare_value(
        "DDD vs команды stitch",
        ddd_metadata.get("stitch_count"),
        dst_command_types.get("stitch", 0)
    )

    comparisons["color_changes"] = compare_value(
        "Смены цвета",
        ddd_metadata.get(
            "color_change_count"
        ),
        dst_header.get("CO")
    )

    comparisons["end_x"] = compare_value(
        "Конечная координата X",
        ddd_metadata.get("end_x"),
        dst_header.get("AX")
    )

    comparisons["end_y"] = compare_value(
        "Конечная координата Y",
        ddd_metadata.get("end_y"),
        dst_header.get("AY")
    )

    ddd_dimensions = get_ddd_dimensions(
        ddd_metadata
    )

    print("\nРазмеры из DDD:")

    for key, value in ddd_dimensions.items():
        print(
            f"{key:<25}: {value}"
        )

    print("\nРазмеры из DST:")

    print(
        "width:",
        dst_bounds["width"]
    )

    print(
        "height:",
        dst_bounds["height"]
    )

    if isinstance(
        ddd_dimensions["design_width"],
        (int, float)
    ):
        comparisons["width"] = compare_value(
            "Ширина дизайна",
            ddd_dimensions["design_width"],
            dst_bounds["width"]
        )

    if isinstance(
        ddd_dimensions["design_height"],
        (int, float)
    ):
        comparisons["height"] = compare_value(
            "Высота дизайна",
            ddd_dimensions["design_height"],
            dst_bounds["height"]
        )

    if isinstance(
        ddd_dimensions["width_from_bounds"],
        (int, float)
    ):
        comparisons["width_from_bounds"] = (
            compare_value(
                "Ширина по границам DDD",
                ddd_dimensions[
                    "width_from_bounds"
                ],
                dst_bounds["width"]
            )
        )

    if isinstance(
        ddd_dimensions["height_from_bounds"],
        (int, float)
    ):
        comparisons["height_from_bounds"] = (
            compare_value(
                "Высота по границам DDD",
                ddd_dimensions[
                    "height_from_bounds"
                ],
                dst_bounds["height"]
            )
        )

    # ---------------------------------------------------------
    # Извлекаем потоки EMB
    # ---------------------------------------------------------

    stream_inventory = extract_streams(
        emb_reader,
        stream_names
    )

    contents_stream = find_stream(
        stream_names,
        "Contents"
    )

    design_document_stream = find_stream(
        stream_names,
        "DesignDocument"
    )

    ddd_stream = find_stream(
        stream_names,
        "WilcomDesignInformationDDD"
    )

    print("\n" + "=" * 80)
    print("КЛЮЧЕВЫЕ ПОТОКИ")
    print("=" * 80)

    print(
        "DDD:",
        repr(ddd_stream)
    )

    print(
        "Contents:",
        repr(contents_stream)
    )

    print(
        "DesignDocument:",
        repr(design_document_stream)
    )

    # ---------------------------------------------------------
    # Ищем фрагменты DST внутри EMB
    # ---------------------------------------------------------

    stream_variants = build_stream_variants(
        emb_reader,
        stream_names
    )

    dst_fragment_matches = (
        search_dst_fragments(
            dst_data,
            stream_variants
        )
    )

    # ---------------------------------------------------------
    # Сохраняем итог
    # ---------------------------------------------------------

    summary = {
        "emb": {
            "path": str(
                EMB_PATH.relative_to(BASE_DIR)
            ),
            "basic_metadata": emb_basic_metadata,
            "ddd_metadata": ddd_metadata,
            "ddd_dimensions": ddd_dimensions,
            "streams": stream_inventory,
            "key_streams": {
                "ddd": ddd_stream,
                "contents": contents_stream,
                "design_document": (
                    design_document_stream
                ),
            },
        },
        "dst": {
            "path": str(
                DST_PATH.relative_to(BASE_DIR)
            ),
            "header": dst_header,
            "command_count": len(
                dst_commands
            ),
            "command_types": dst_command_types,
            "bounds": dst_bounds,
        },
        "comparisons": comparisons,
        "exact_dst_fragment_matches": (
            dst_fragment_matches
        ),
    }

    SUMMARY_PATH.write_text(
        json.dumps(
            summary,
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
        "Результаты сохранены:"
    )

    print(SUMMARY_PATH)

    print(
        "\nИзвлечённые потоки:"
    )

    print(STREAMS_DIR)


if __name__ == "__main__":
    main()