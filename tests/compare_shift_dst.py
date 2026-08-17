from itertools import zip_longest
from pathlib import Path
import hashlib
import sys


BASE_DIR = Path(__file__).resolve().parents[1]

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.dst_parser import DSTParser


ORIGINAL = (
    BASE_DIR
    / "dataset"
    / "experiments"
    / "dst"
    / "base"
    / "design.DST"
)

SHIFTED = (
    BASE_DIR
    / "dataset"
    / "experiments"
    / "dst"
    / "x14"
    / "design.DST"
)


def short_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:12]


def print_header_diff(
    old_header: dict,
    new_header: dict,
) -> None:
    print("\nHEADER DIFFERENCES:")

    changed = 0

    for key in sorted(set(old_header) | set(new_header)):
        old_value = old_header.get(key)
        new_value = new_header.get(key)

        if old_value == new_value:
            continue

        changed += 1
        print(
            f"{key}: "
            f"{old_value!r} -> {new_value!r}"
        )

    if changed == 0:
        print("Заголовки одинаковые.")


def command_signature(command: dict | None):
    if command is None:
        return None

    return (
        command["dx"],
        command["dy"],
        command["type"],
    )


def main() -> None:
    print("ORIGINAL EXISTS:", ORIGINAL.exists())
    print("SHIFTED EXISTS:", SHIFTED.exists())

    old_data = ORIGINAL.read_bytes()
    new_data = SHIFTED.read_bytes()

    print("=" * 80)
    print("COMPARE ORIGINAL DST VS SHIFTED DST")
    print("=" * 80)

    print(
        "OLD:",
        len(old_data),
        short_hash(old_data),
    )
    print(
        "NEW:",
        len(new_data),
        short_hash(new_data),
    )
    print(
        "FILES IDENTICAL:",
        old_data == new_data,
    )

    old_parser = DSTParser(old_data)
    new_parser = DSTParser(new_data)

    old_header = old_parser.read_header()
    new_header = new_parser.read_header()

    print_header_diff(
        old_header,
        new_header,
    )

    old_commands = old_parser.parse()
    new_commands = new_parser.parse()

    print("\nCOMMAND COUNTS:")
    print("OLD:", len(old_commands))
    print("NEW:", len(new_commands))

    print("\nBOUNDS:")
    print(
        "OLD:",
        old_parser.get_bounds(old_commands),
    )
    print(
        "NEW:",
        new_parser.get_bounds(new_commands),
    )

    changed_commands = []

    for index, (old, new) in enumerate(
        zip_longest(
            old_commands,
            new_commands,
        )
    ):
        if (
            command_signature(old)
            == command_signature(new)
        ):
            continue

        changed_commands.append(
            (index, old, new)
        )

    print(
        "\nCHANGED COMMANDS:",
        len(changed_commands),
    )

    for index, old, new in changed_commands[:20]:
        print("\nINDEX:", index)

        if old is None:
            print("OLD: отсутствует")
        else:
            print(
                "OLD:",
                "type=", old["type"],
                "dx=", old["dx"],
                "dy=", old["dy"],
                "x=", old["x"],
                "y=", old["y"],
                "x_mm=", old["x_mm"],
                "y_mm=", old["y_mm"],
                "raw=", old["raw"],
            )

        if new is None:
            print("NEW: отсутствует")
        else:
            print(
                "NEW:",
                "type=", new["type"],
                "dx=", new["dx"],
                "dy=", new["dy"],
                "x=", new["x"],
                "y=", new["y"],
                "x_mm=", new["x_mm"],
                "y_mm=", new["y_mm"],
                "raw=", new["raw"],
            )


if __name__ == "__main__":
    main()