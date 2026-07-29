from pathlib import Path
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

    expected_size = struct.unpack_from(
        "<I",
        raw,
        0,
    )[0]

    data = zlib.decompress(raw[4:])

    if len(data) != expected_size:
        raise ValueError(
            f"Неверный размер Contents: {path.name}"
        )

    return data


def format_hex(data: bytes) -> str:
    return " ".join(
        f"{value:02x}"
        for value in data
    )


def diff_marker(
    old: bytes,
    new: bytes,
) -> str:
    markers = []

    for old_byte, new_byte in zip(old, new):
        if old_byte == new_byte:
            markers.append("  ")
        else:
            markers.append("^^")

    return " ".join(markers)


def main() -> None:
    original = read_contents(ORIGINAL)
    shifted = read_contents(SHIFTED)

    start = 6768
    end = 6976
    line_size = 16

    print("=" * 100)
    print("CONTENT REGION")
    print("=" * 100)

    for offset in range(
        start,
        end,
        line_size,
    ):
        old_chunk = original[
            offset:offset + line_size
        ]

        new_chunk = shifted[
            offset:offset + line_size
        ]

        print()
        print(
            f"{offset:04d} OLD:",
            format_hex(old_chunk),
        )

        print(
            f"{offset:04d} NEW:",
            format_hex(new_chunk),
        )

        print(
            "          ",
            diff_marker(
                old_chunk,
                new_chunk,
            ),
        )


if __name__ == "__main__":
    main()