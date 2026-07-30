from __future__ import annotations

import argparse
import csv
import os
import random
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from decimal import (
    Decimal,
    InvalidOperation,
    ROUND_CEILING,
    ROUND_FLOOR,
    ROUND_HALF_UP,
)
from pathlib import Path


CSV_COLUMNS = [
    "file",
    "x",
    "y",
    "output_file",
]
DEFAULT_OUTPUT_SUBDIR = "positioned_variants"
COORDINATE_QUANTUM = Decimal("0.01")
HUNDRED = Decimal("100")


@dataclass(frozen=True)
class VariantRow:
    file: str
    x: str
    y: str
    output_file: str


def as_decimal(
    value: Decimal | str | int,
    name: str = "значение",
) -> Decimal:
    if isinstance(value, Decimal):
        number = value
    else:
        try:
            number = Decimal(str(value))
        except InvalidOperation as error:
            raise ValueError(
                f"Некорректное числовое {name}: {value!r}"
            ) from error

    if not number.is_finite():
        raise ValueError(
            f"{name} должно быть конечным числом: {value!r}"
        )

    return number


def normalize_zero(
    value: Decimal,
) -> Decimal:
    return Decimal("0") if value == 0 else value


def quantize_coordinate(
    value: Decimal | str | int,
) -> Decimal:
    quantized = as_decimal(
        value,
        "координаты",
    ).quantize(
        COORDINATE_QUANTUM,
        rounding=ROUND_HALF_UP,
    )
    return normalize_zero(quantized)


def format_coordinate(
    value: Decimal | str | int,
) -> str:
    return format(
        quantize_coordinate(value),
        ".2f",
    )


def encode_coordinate_for_filename(
    value: Decimal | str | int,
) -> str:
    formatted = format_coordinate(value)

    if formatted.startswith("-"):
        formatted = f"m{formatted[1:]}"
    elif formatted.startswith("+"):
        formatted = formatted[1:]

    return formatted.replace(".", "_")


def validate_output_subdir(
    output_subdir: str,
) -> Path:
    output_subdir = output_subdir.strip()

    if not output_subdir:
        raise ValueError(
            "output-subdir не может быть пустым."
        )

    relative_path = Path(output_subdir)

    if not relative_path.parts:
        raise ValueError(
            "output-subdir должен содержать имя папки."
        )

    if relative_path.is_absolute() or relative_path.drive:
        raise ValueError(
            "output-subdir должен быть относительным: "
            f"{output_subdir}"
        )

    if ".." in relative_path.parts:
        raise ValueError(
            "output-subdir не может содержать '..': "
            f"{output_subdir}"
        )

    return relative_path


def contains_path_sequence(
    path_parts: tuple[str, ...],
    sequence_parts: tuple[str, ...],
) -> bool:
    if len(sequence_parts) > len(path_parts):
        return False

    normalized_path = tuple(
        part.casefold()
        for part in path_parts
    )
    normalized_sequence = tuple(
        part.casefold()
        for part in sequence_parts
    )
    sequence_length = len(normalized_sequence)

    return any(
        normalized_path[index:index + sequence_length]
        == normalized_sequence
        for index in range(
            len(normalized_path) - sequence_length + 1
        )
    )


def discover_emb_files(
    input_dir: Path,
    output_subdir: str = DEFAULT_OUTPUT_SUBDIR,
) -> list[Path]:
    """Рекурсивно и детерминированно находит исходные EMB."""

    input_root = input_dir.resolve()

    if not input_root.is_dir():
        raise NotADirectoryError(
            f"Папка input-dir не найдена: {input_root}"
        )

    excluded_parts = validate_output_subdir(
        output_subdir
    ).parts
    discovered: list[Path] = []

    for current_dir, dirnames, filenames in os.walk(
        input_root
    ):
        current_path = Path(current_dir)
        current_relative = current_path.relative_to(
            input_root
        )

        dirnames[:] = [
            directory_name
            for directory_name in dirnames
            if not contains_path_sequence(
                (
                    *current_relative.parts,
                    directory_name,
                ),
                excluded_parts,
            )
        ]

        for filename in filenames:
            if "__processing_" in filename.casefold():
                continue

            file_path = current_path / filename

            if file_path.suffix.lower() == ".emb":
                discovered.append(file_path)

    return sorted(
        discovered,
        key=lambda file_path: (
            file_path.relative_to(
                input_root
            ).as_posix().casefold(),
            file_path.relative_to(
                input_root
            ).as_posix(),
        ),
    )


def decimal_range(
    minimum: Decimal | str | int,
    maximum: Decimal | str | int,
    step: Decimal | str | int,
) -> list[Decimal]:
    minimum_value = as_decimal(minimum, "minimum")
    maximum_value = as_decimal(maximum, "maximum")
    step_value = as_decimal(step, "step")

    if step_value <= 0:
        raise ValueError(
            "step должен быть больше нуля."
        )

    if minimum_value > maximum_value:
        raise ValueError(
            "minimum не может быть больше maximum."
        )

    values: list[Decimal] = []
    current = minimum_value

    while current <= maximum_value:
        values.append(
            normalize_zero(current)
        )
        current += step_value

    return values


def add_center_if_requested(
    coordinates: list[tuple[Decimal, Decimal]],
    include_center: bool,
) -> list[tuple[Decimal, Decimal]]:
    if not include_center:
        return coordinates

    center = (
        Decimal("0"),
        Decimal("0"),
    )

    if center not in coordinates:
        return [
            *coordinates,
            center,
        ]

    return coordinates


def generate_grid_coordinates(
    x_min: Decimal | str | int,
    x_max: Decimal | str | int,
    y_min: Decimal | str | int,
    y_max: Decimal | str | int,
    step: Decimal | str | int,
    include_center: bool = False,
) -> list[tuple[Decimal, Decimal]]:
    if as_decimal(x_min, "x-min") > as_decimal(
        x_max,
        "x-max",
    ):
        raise ValueError(
            "x-min не может быть больше x-max."
        )

    if as_decimal(y_min, "y-min") > as_decimal(
        y_max,
        "y-max",
    ):
        raise ValueError(
            "y-min не может быть больше y-max."
        )

    x_values = decimal_range(
        x_min,
        x_max,
        step,
    )
    y_values = decimal_range(
        y_min,
        y_max,
        step,
    )
    coordinates = [
        (x_value, y_value)
        for x_value in x_values
        for y_value in y_values
    ]

    return add_center_if_requested(
        coordinates,
        include_center,
    )


def coordinate_tick_bounds(
    minimum: Decimal | str | int,
    maximum: Decimal | str | int,
    axis_name: str,
) -> tuple[int, int]:
    minimum_value = as_decimal(
        minimum,
        f"{axis_name}-min",
    )
    maximum_value = as_decimal(
        maximum,
        f"{axis_name}-max",
    )

    if minimum_value > maximum_value:
        raise ValueError(
            f"{axis_name}-min не может быть больше "
            f"{axis_name}-max."
        )

    minimum_tick = int(
        (minimum_value * HUNDRED).to_integral_value(
            rounding=ROUND_CEILING,
        )
    )
    maximum_tick = int(
        (maximum_value * HUNDRED).to_integral_value(
            rounding=ROUND_FLOOR,
        )
    )

    return minimum_tick, maximum_tick


def generate_random_coordinates(
    x_min: Decimal | str | int,
    x_max: Decimal | str | int,
    y_min: Decimal | str | int,
    y_max: Decimal | str | int,
    count: int,
    seed: int | None = None,
    include_center: bool = False,
    rng: random.Random | None = None,
) -> list[tuple[Decimal, Decimal]]:
    if count <= 0:
        raise ValueError(
            "count должен быть больше нуля."
        )

    x_min_tick, x_max_tick = coordinate_tick_bounds(
        x_min,
        x_max,
        "x",
    )
    y_min_tick, y_max_tick = coordinate_tick_bounds(
        y_min,
        y_max,
        "y",
    )
    x_count = max(
        0,
        x_max_tick - x_min_tick + 1,
    )
    y_count = max(
        0,
        y_max_tick - y_min_tick + 1,
    )
    capacity = x_count * y_count

    if count > capacity:
        raise ValueError(
            f"Невозможно получить {count} уникальных "
            "координатных пар после округления до сотых. "
            f"Доступно: {capacity}."
        )

    random_source = (
        rng
        if rng is not None
        else random.Random(seed)
    )
    sampled_indexes = random_source.sample(
        range(capacity),
        count,
    )
    coordinates: list[tuple[Decimal, Decimal]] = []

    for sampled_index in sampled_indexes:
        x_offset, y_offset = divmod(
            sampled_index,
            y_count,
        )
        x_tick = x_min_tick + x_offset
        y_tick = y_min_tick + y_offset
        coordinates.append(
            (
                Decimal(x_tick) / HUNDRED,
                Decimal(y_tick) / HUNDRED,
            )
        )

    return add_center_if_requested(
        coordinates,
        include_center,
    )


def build_variant_output_file(
    relative_source_file: str | Path,
    x: Decimal | str | int,
    y: Decimal | str | int,
    output_subdir: str = DEFAULT_OUTPUT_SUBDIR,
) -> str:
    source_path = Path(relative_source_file)

    if source_path.is_absolute() or source_path.drive:
        raise ValueError(
            "Исходный путь должен быть относительным: "
            f"{relative_source_file}"
        )

    if ".." in source_path.parts:
        raise ValueError(
            "Исходный путь не может содержать '..': "
            f"{relative_source_file}"
        )

    if source_path.suffix.lower() != ".emb":
        raise ValueError(
            "Ожидался исходный файл .emb: "
            f"{relative_source_file}"
        )

    output_subdir_path = validate_output_subdir(
        output_subdir
    )
    filename = (
        f"{source_path.stem}"
        f"__x_{encode_coordinate_for_filename(x)}"
        f"__y_{encode_coordinate_for_filename(y)}"
        ".EMB"
    )
    output_path = (
        source_path.parent
        / output_subdir_path
        / filename
    )

    return output_path.as_posix()


def generate_rows(
    emb_files: list[Path],
    input_dir: Path,
    mode: str,
    x_min: Decimal | str | int,
    x_max: Decimal | str | int,
    y_min: Decimal | str | int,
    y_max: Decimal | str | int,
    output_subdir: str = DEFAULT_OUTPUT_SUBDIR,
    include_center: bool = False,
    step: Decimal | str | int | None = None,
    count: int | None = None,
    seed: int | None = None,
) -> list[VariantRow]:
    input_root = input_dir.resolve()
    validate_output_subdir(output_subdir)

    if mode == "grid":
        if step is None:
            raise ValueError(
                "Для режима grid требуется --step."
            )

        shared_coordinates = generate_grid_coordinates(
            x_min,
            x_max,
            y_min,
            y_max,
            step,
            include_center=include_center,
        )
        random_source = None
    elif mode == "random":
        if count is None:
            raise ValueError(
                "Для режима random требуется --count."
            )

        if seed is None:
            raise ValueError(
                "Для режима random требуется --seed."
            )

        shared_coordinates = None
        random_source = random.Random(seed)
    else:
        raise ValueError(
            f"Неизвестный режим генерации: {mode!r}"
        )

    rows: list[VariantRow] = []
    output_files: dict[str, VariantRow] = {}

    for emb_file in emb_files:
        file_path = (
            emb_file
            if emb_file.is_absolute()
            else input_root / emb_file
        ).resolve()

        try:
            relative_source = file_path.relative_to(
                input_root
            ).as_posix()
        except ValueError as error:
            raise ValueError(
                f"EMB находится вне input-dir: {file_path}"
            ) from error

        if mode == "grid":
            assert shared_coordinates is not None
            coordinates = shared_coordinates
        else:
            assert count is not None
            assert random_source is not None
            coordinates = generate_random_coordinates(
                x_min,
                x_max,
                y_min,
                y_max,
                count,
                include_center=include_center,
                rng=random_source,
            )

        for x_value, y_value in coordinates:
            formatted_x = format_coordinate(x_value)
            formatted_y = format_coordinate(y_value)
            output_file = build_variant_output_file(
                relative_source,
                formatted_x,
                formatted_y,
                output_subdir,
            )
            row = VariantRow(
                file=relative_source,
                x=formatted_x,
                y=formatted_y,
                output_file=output_file,
            )
            output_key = output_file.casefold()
            conflicting_row = output_files.get(
                output_key
            )

            if conflicting_row is not None:
                raise ValueError(
                    "Два задания получили одинаковый "
                    f"output_file: {output_file}. "
                    f"Координаты: "
                    f"({conflicting_row.x}, "
                    f"{conflicting_row.y}) и "
                    f"({row.x}, {row.y})."
                )

            output_files[output_key] = row
            rows.append(row)

    return rows


def write_coordinate_csv_atomic(
    output_csv: Path,
    rows: list[VariantRow],
    overwrite: bool = False,
) -> None:
    output_path = output_csv.resolve()

    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"CSV уже существует: {output_path}. "
            "Используйте --overwrite для замены."
        )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        dir=output_path.parent,
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)

    try:
        with temporary_path.open(
            "w",
            encoding="utf-8-sig",
            newline="",
        ) as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=CSV_COLUMNS,
                delimiter=";",
                lineterminator="\n",
            )
            writer.writeheader()

            for row in rows:
                writer.writerow(
                    {
                        "file": row.file,
                        "x": row.x,
                        "y": row.y,
                        "output_file": row.output_file,
                    }
                )

        os.replace(
            temporary_path,
            output_path,
        )
    finally:
        try:
            temporary_path.unlink(
                missing_ok=True,
            )
        except OSError:
            pass


def decimal_cli_value(
    value: str,
) -> Decimal:
    try:
        return as_decimal(value, "аргумента")
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            str(error)
        ) from error


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-dir",
        type=Path,
        required=True,
        help="Корневая папка исходных EMB",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        required=True,
        help="Выходной CSV для пакетной автоматизации",
    )
    parser.add_argument(
        "--mode",
        choices=("grid", "random"),
        required=True,
        help="Режим генерации координат",
    )
    parser.add_argument(
        "--output-subdir",
        default=DEFAULT_OUTPUT_SUBDIR,
        help="Подпапка вариантов рядом с исходным EMB",
    )
    parser.add_argument(
        "--include-center",
        action="store_true",
        help="Гарантированно добавить координаты 0.00, 0.00",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Атомарно заменить существующий output-csv",
    )
    parser.add_argument(
        "--x-min",
        type=decimal_cli_value,
        required=True,
    )
    parser.add_argument(
        "--x-max",
        type=decimal_cli_value,
        required=True,
    )
    parser.add_argument(
        "--y-min",
        type=decimal_cli_value,
        required=True,
    )
    parser.add_argument(
        "--y-max",
        type=decimal_cli_value,
        required=True,
    )
    parser.add_argument(
        "--step",
        type=decimal_cli_value,
        help="Шаг сетки для режима grid",
    )
    parser.add_argument(
        "--count",
        type=int,
        help="Число случайных координат для режима random",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="Seed для режима random",
    )

    return parser


def print_statistics(
    emb_files: list[Path],
    rows: list[VariantRow],
    output_csv: Path,
) -> None:
    variants_by_file = Counter(
        row.file
        for row in rows
    )
    variant_counts = list(
        variants_by_file.values()
    )

    if not variant_counts:
        variants_text = "0"
    elif min(variant_counts) == max(variant_counts):
        variants_text = str(variant_counts[0])
    else:
        variants_text = (
            f"{min(variant_counts)}-"
            f"{max(variant_counts)}"
        )

    print(f"Найдено EMB: {len(emb_files)}")
    print(f"Вариантов на файл: {variants_text}")
    print(f"Всего задач: {len(rows)}")
    print(f"CSV: {output_csv.resolve()}")


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    try:
        emb_files = discover_emb_files(
            args.input_dir,
            args.output_subdir,
        )
        rows = generate_rows(
            emb_files=emb_files,
            input_dir=args.input_dir,
            mode=args.mode,
            x_min=args.x_min,
            x_max=args.x_max,
            y_min=args.y_min,
            y_max=args.y_max,
            output_subdir=args.output_subdir,
            include_center=args.include_center,
            step=args.step,
            count=args.count,
            seed=args.seed,
        )
        write_coordinate_csv_atomic(
            args.output_csv,
            rows,
            overwrite=args.overwrite,
        )
        print_statistics(
            emb_files,
            rows,
            args.output_csv,
        )
    except Exception as error:
        print(
            f"ERROR: {error}",
            file=sys.stderr,
        )
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
