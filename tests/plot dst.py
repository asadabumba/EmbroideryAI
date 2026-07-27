from pathlib import Path

import matplotlib.pyplot as plt

from src.dst_parser import DSTParser


BASE_DIR = Path(__file__).resolve().parent.parent

DST_PATH = (
    BASE_DIR
    / "archive"
    / "originals"
    / "dst"
    / "rose.dst"
)

OUTPUT_DIR = BASE_DIR / "logs"
OUTPUT_PATH = OUTPUT_DIR / "rose_dst.png"


def build_stitch_segments(commands):
    """
    Создаёт отдельные линии стежков.

    Jump, смена цвета и конец файла разрывают линию,
    поэтому перемещения без вышивания не рисуются.
    """

    segments = []
    current_segment = []

    previous_x = 0.0
    previous_y = 0.0

    for command in commands:
        current_x = command["x_mm"]
        current_y = command["y_mm"]

        if command["type"] == "stitch":
            if not current_segment:
                current_segment.append(
                    (previous_x, previous_y)
                )

            current_segment.append(
                (current_x, current_y)
            )

        else:
            if len(current_segment) >= 2:
                segments.append(current_segment)

            current_segment = []

        previous_x = current_x
        previous_y = current_y

    if len(current_segment) >= 2:
        segments.append(current_segment)

    return segments


def main():
    if not DST_PATH.exists():
        raise FileNotFoundError(
            f"DST-файл не найден: {DST_PATH}"
        )

    data = DST_PATH.read_bytes()

    parser = DSTParser(data)

    header = parser.read_header()
    commands = parser.parse()
    bounds = parser.get_bounds(commands)

    segments = build_stitch_segments(commands)

    print("Файл:", DST_PATH.name)
    print("Название:", header.get("LA"))
    print("Команд:", len(commands))
    print("Линий стежков:", len(segments))

    print(
        "Размер:",
        f"{bounds['width'] * parser.UNIT_MM:.1f} × "
        f"{bounds['height'] * parser.UNIT_MM:.1f} мм"
    )

    fig, ax = plt.subplots(figsize=(10, 10))

    for segment in segments:
        x_values = [
            point[0]
            for point in segment
        ]

        y_values = [
            point[1]
            for point in segment
        ]

        ax.plot(
            x_values,
            y_values,
            linewidth=0.5
        )

    ax.set_title(
        f"{header.get('LA', DST_PATH.stem)} — DST preview"
    )

    ax.set_xlabel("X, мм")
    ax.set_ylabel("Y, мм")

    ax.set_aspect(
        "equal",
        adjustable="box"
    )

    ax.grid(
        True,
        linewidth=0.3
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    fig.tight_layout()

    fig.savefig(
        OUTPUT_PATH,
        dpi=200,
        bbox_inches="tight"
    )

    print("Изображение сохранено:")
    print(OUTPUT_PATH)

    plt.show()


if __name__ == "__main__":
    main()