from pathlib import Path
import sys
from typing import Any

import olefile


def find_base_dir() -> Path:
    current_file = Path(__file__).resolve()

    for parent in current_file.parents:
        if (
            parent / "src" / "ddd_parser.py"
        ).exists():
            return parent

    raise RuntimeError(
        "Не удалось найти корень проекта"
    )


BASE_DIR = find_base_dir()

sys.path.insert(
    0,
    str(BASE_DIR),
)

from src.ddd_parser import DDDParser


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


def read_all_properties(
    path: Path,
) -> tuple[
    dict[int, Any],
    dict[int, str],
]:
    parser = DDDParser(path)

    with olefile.OleFileIO(
        str(path)
    ) as ole:
        raw_data = ole.openstream(
            parser.STREAM_NAME
        ).read()

        properties = ole.getproperties(
            parser.STREAM_NAME
        )

    property_names = (
        parser._parse_property_names(
            raw_data
        )
    )

    return properties, property_names


def format_value(value: Any) -> str:
    if isinstance(value, bytes):
        preview = value[:64].hex(" ")

        return (
            f"bytes(len={len(value)}, "
            f"hex={preview})"
        )

    return repr(value)


def main() -> None:
    original, original_names = (
        read_all_properties(ORIGINAL)
    )

    shifted, shifted_names = (
        read_all_properties(SHIFTED)
    )

    all_property_ids = sorted(
        set(original)
        | set(shifted)
    )

    changed_count = 0

    print("=" * 80)
    print("ИЗМЕНЁННЫЕ СЫРЫЕ СВОЙСТВА DDD")
    print("=" * 80)

    for property_id in all_property_ids:
        old_value = original.get(property_id)
        new_value = shifted.get(property_id)

        if old_value == new_value:
            continue

        changed_count += 1

        property_name = (
            original_names.get(property_id)
            or shifted_names.get(property_id)
            or "<неизвестное свойство>"
        )

        print()
        print("PROPERTY ID:", property_id)
        print(
            "PROPERTY HEX:",
            f"0x{property_id:08X}",
        )
        print("NAME:", property_name)
        print(
            "OLD TYPE:",
            type(old_value).__name__,
        )
        print(
            "NEW TYPE:",
            type(new_value).__name__,
        )
        print(
            "OLD:",
            format_value(old_value),
        )
        print(
            "NEW:",
            format_value(new_value),
        )

        if (
            isinstance(old_value, (int, float))
            and isinstance(new_value, (int, float))
        ):
            print(
                "DELTA:",
                new_value - old_value,
            )

    print()
    print("=" * 80)
    print(
        "Всего изменённых свойств:",
        changed_count,
    )


if __name__ == "__main__":
    main()