from collections import Counter
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

OUTPUT_DIR = (
    BASE_DIR
    / "logs"
    / "controlled_shift"
)


def read_design_icon(path: Path) -> bytes:
    with olefile.OleFileIO(str(path)) as ole:
        raw = ole.openstream(
            "DESIGN_ICON"
        ).read()

    if len(raw) < 5:
        raise ValueError(
            f"DESIGN_ICON слишком короткий: {path}"
        )

    expected_size = struct.unpack_from(
        "<I",
        raw,
        0,
    )[0]

    bmp = zlib.decompress(
        raw[4:]
    )

    if len(bmp) != expected_size:
        raise ValueError(
            f"Неверный размер DESIGN_ICON: "
            f"ожидалось {expected_size}, "
            f"получено {len(bmp)}"
        )

    if bmp[:2] != b"BM":
        raise ValueError(
            f"После распаковки получен не BMP: "
            f"{path.name}"
        )

    return bmp


def parse_8bit_bmp(
    bmp: bytes,
) -> tuple[
    int,
    int,
    list[list[int]],
]:
    pixel_offset = struct.unpack_from(
        "<I",
        bmp,
        10,
    )[0]

    width = struct.unpack_from(
        "<i",
        bmp,
        18,
    )[0]

    raw_height = struct.unpack_from(
        "<i",
        bmp,
        22,
    )[0]

    bits_per_pixel = struct.unpack_from(
        "<H",
        bmp,
        28,
    )[0]

    if bits_per_pixel != 8:
        raise ValueError(
            f"Ожидался 8-bit BMP, "
            f"получено {bits_per_pixel} бит"
        )

    height = abs(raw_height)

    row_size = (
        (width * bits_per_pixel + 31)
        // 32
        * 4
    )

    rows = []

    for row_index in range(height):
        start = (
            pixel_offset
            + row_index * row_size
        )

        row = list(
            bmp[start:start + width]
        )

        rows.append(row)

    # BMP обычно хранит строки снизу вверх.
    if raw_height > 0:
        rows.reverse()

    return width, height, rows


def most_common_pixel(
    pixels: list[list[int]],
) -> int:
    values = [
        value
        for row in pixels
        for value in row
    ]

    return Counter(values).most_common(1)[0][0]


def foreground_points(
    pixels: list[list[int]],
    background: int,
) -> set[tuple[int, int]]:
    points = set()

    for y, row in enumerate(pixels):
        for x, value in enumerate(row):
            if value != background:
                points.add((x, y))

    return points


def bounding_box(
    points: set[tuple[int, int]],
):
    if not points:
        return None

    xs = [
        point[0]
        for point in points
    ]

    ys = [
        point[1]
        for point in points
    ]

    return (
        min(xs),
        min(ys),
        max(xs),
        max(ys),
    )


def center_of_box(box):
    if box is None:
        return None

    left, top, right, bottom = box

    return (
        (left + right) / 2,
        (top + bottom) / 2,
    )


def best_mask_shift(
    original_points: set[tuple[int, int]],
    shifted_points: set[tuple[int, int]],
    width: int,
    height: int,
):
    best_result = None

    for dy in range(-40, 41):
        for dx in range(-40, 41):
            moved = {
                (x + dx, y + dy)
                for x, y in original_points
                if (
                    0 <= x + dx < width
                    and 0 <= y + dy < height
                )
            }

            intersection = len(
                moved & shifted_points
            )

            union = len(
                moved | shifted_points
            )

            score = (
                intersection / union
                if union
                else 0
            )

            result = {
                "dx": dx,
                "dy": dy,
                "intersection": intersection,
                "union": union,
                "iou": score,
            }

            if (
                best_result is None
                or result["iou"]
                > best_result["iou"]
            ):
                best_result = result

    return best_result


def main() -> None:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    original_bmp = read_design_icon(
        ORIGINAL
    )

    shifted_bmp = read_design_icon(
        SHIFTED
    )

    original_output = (
        OUTPUT_DIR
        / "original_design_icon.bmp"
    )

    shifted_output = (
        OUTPUT_DIR
        / "shifted_design_icon.bmp"
    )

    original_output.write_bytes(
        original_bmp
    )

    shifted_output.write_bytes(
        shifted_bmp
    )

    (
        original_width,
        original_height,
        original_pixels,
    ) = parse_8bit_bmp(
        original_bmp
    )

    (
        shifted_width,
        shifted_height,
        shifted_pixels,
    ) = parse_8bit_bmp(
        shifted_bmp
    )

    if (
        original_width != shifted_width
        or original_height != shifted_height
    ):
        raise ValueError(
            "Размеры изображений отличаются"
        )

    original_background = (
        most_common_pixel(
            original_pixels
        )
    )

    shifted_background = (
        most_common_pixel(
            shifted_pixels
        )
    )

    original_foreground = (
        foreground_points(
            original_pixels,
            original_background,
        )
    )

    shifted_foreground = (
        foreground_points(
            shifted_pixels,
            shifted_background,
        )
    )

    original_box = bounding_box(
        original_foreground
    )

    shifted_box = bounding_box(
        shifted_foreground
    )

    original_center = center_of_box(
        original_box
    )

    shifted_center = center_of_box(
        shifted_box
    )

    changed_pixels = 0

    for y in range(original_height):
        for x in range(original_width):
            if (
                original_pixels[y][x]
                != shifted_pixels[y][x]
            ):
                changed_pixels += 1

    best_shift = best_mask_shift(
        original_foreground,
        shifted_foreground,
        original_width,
        original_height,
    )

    print("=" * 80)
    print("СРАВНЕНИЕ DESIGN_ICON")
    print("=" * 80)

    print(
        "Размер:",
        original_width,
        "x",
        original_height,
    )

    print(
        "Размер BMP оригинала:",
        len(original_bmp),
    )

    print(
        "Размер BMP после сдвига:",
        len(shifted_bmp),
    )

    print(
        "Изменено пикселей:",
        changed_pixels,
        "из",
        original_width * original_height,
    )

    print(
        "Фон оригинала:",
        original_background,
    )

    print(
        "Фон нового:",
        shifted_background,
    )

    print(
        "Foreground оригинала:",
        len(original_foreground),
        "пикселей",
    )

    print(
        "Foreground нового:",
        len(shifted_foreground),
        "пикселей",
    )

    print()
    print(
        "Границы оригинала:",
        original_box,
    )

    print(
        "Границы нового:",
        shifted_box,
    )

    print(
        "Центр оригинала:",
        original_center,
    )

    print(
        "Центр нового:",
        shifted_center,
    )

    if (
        original_center is not None
        and shifted_center is not None
    ):
        print(
            "Сдвиг центра:",
            (
                shifted_center[0]
                - original_center[0]
            ),
            (
                shifted_center[1]
                - original_center[1]
            ),
        )

    print()
    print("Лучшее совмещение масок:")
    print(
        "DX:",
        best_shift["dx"],
    )
    print(
        "DY:",
        best_shift["dy"],
    )
    print(
        "IoU:",
        round(
            best_shift["iou"],
            6,
        ),
    )

    print()
    print(
        "Картинки сохранены в:",
        OUTPUT_DIR,
    )


if __name__ == "__main__":
    main()