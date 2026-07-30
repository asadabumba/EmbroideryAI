from __future__ import annotations

import argparse
import csv
import shutil
import sys
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent

if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from automate_wilcom_file import (
    dismiss_known_open_error_dialog,
    process_emb_file,
)


REQUIRED_COLUMNS = {"file", "x", "y"}
REPORT_COLUMNS = [
    "row",
    "source_file",
    "output_file",
    "requested_x",
    "requested_y",
    "old_x",
    "old_y",
    "actual_x",
    "actual_y",
    "status",
    "error",
]


@dataclass(frozen=True)
class CoordinateRow:
    row: int
    file: str
    x: str
    y: str


class BatchStoppedError(RuntimeError):
    """Очередь остановлена после ошибки по запросу пользователя."""


def normalize_coordinate(value: str) -> str:
    """Проверяет координату и заменяет десятичную запятую точкой."""

    normalized = value.strip().replace(",", ".")

    if not normalized:
        raise ValueError("Координата не может быть пустой.")

    try:
        number = Decimal(normalized)
    except InvalidOperation as error:
        raise ValueError(
            f"Некорректная координата: {value!r}"
        ) from error

    if not number.is_finite():
        raise ValueError(
            f"Координата должна быть конечным числом: {value!r}"
        )

    return normalized


def read_coordinate_csv(csv_path: Path) -> list[CoordinateRow]:
    """Читает CSV с разделителем ``;`` или ``,``."""

    csv_path = csv_path.resolve()

    if not csv_path.is_file():
        raise FileNotFoundError(
            f"CSV-файл не найден: {csv_path}"
        )

    with csv_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        sample = handle.read(8192)
        handle.seek(0)

        if not sample.strip():
            raise ValueError("CSV-файл пуст.")

        try:
            dialect = csv.Sniffer().sniff(
                sample.strip(),
                delimiters=";,",
            )
        except csv.Error as error:
            raise ValueError(
                "Не удалось определить разделитель CSV. "
                "Используйте ';' или ','."
            ) from error

        reader = csv.reader(
            handle,
            dialect,
        )

        raw_header = None

        for values in reader:
            if any(value.strip() for value in values):
                raw_header = values
                break

        if raw_header is None:
            raise ValueError("CSV-файл не содержит заголовка.")

        headers = [
            value.strip().lower()
            for value in raw_header
        ]

        duplicates = {
            header
            for header in headers
            if header and headers.count(header) > 1
        }

        if duplicates:
            names = ", ".join(sorted(duplicates))
            raise ValueError(
                f"Повторяющиеся столбцы CSV: {names}"
            )

        missing = REQUIRED_COLUMNS.difference(headers)

        if missing:
            names = ", ".join(sorted(missing))
            raise ValueError(
                f"В CSV отсутствуют обязательные столбцы: {names}"
            )

        column_indexes = {
            name: headers.index(name)
            for name in REQUIRED_COLUMNS
        }

        rows: list[CoordinateRow] = []

        for values in reader:
            if not any(value.strip() for value in values):
                continue

            if (
                len(values) > len(headers)
                and any(
                    value.strip()
                    for value in values[len(headers):]
                )
            ):
                raise ValueError(
                    f"Строка CSV {reader.line_num} "
                    "содержит лишние значения. "
                    "Проверьте разделитель и экранирование."
                )

            padded_values = [
                *values,
                *([""] * (len(headers) - len(values))),
            ]

            rows.append(
                CoordinateRow(
                    row=len(rows) + 1,
                    file=padded_values[
                        column_indexes["file"]
                    ].strip(),
                    x=padded_values[
                        column_indexes["x"]
                    ].strip(),
                    y=padded_values[
                        column_indexes["y"]
                    ].strip(),
                )
            )

    return rows


def resolve_source_path(
    input_dir: Path,
    file_value: str,
) -> Path:
    """Безопасно разрешает путь к EMB внутри входной папки."""

    input_root = input_dir.resolve()
    file_value = file_value.strip()

    if not file_value:
        raise ValueError("Столбец file не может быть пустым.")

    relative_path = Path(file_value)

    if relative_path.is_absolute() or relative_path.drive:
        raise ValueError(
            f"Путь должен быть относительным: {file_value}"
        )

    source_path = (
        input_root
        / relative_path
    ).resolve()

    if not source_path.is_relative_to(input_root):
        raise ValueError(
            f"Путь выходит за пределы input-dir: {file_value}"
        )

    if source_path.suffix.lower() != ".emb":
        raise ValueError(
            f"Ожидался файл с расширением .emb: {file_value}"
        )

    if not source_path.is_file():
        raise FileNotFoundError(
            f"Исходный EMB-файл не найден: {source_path}"
        )

    return source_path


def build_output_path(
    source_path: Path,
    input_dir: Path,
    output_dir: Path,
) -> Path:
    """Сохраняет относительную структуру входных подпапок."""

    source_path = source_path.resolve()
    input_root = input_dir.resolve()
    output_root = output_dir.resolve()

    try:
        relative_path = source_path.relative_to(
            input_root
        )
    except ValueError as error:
        raise ValueError(
            f"Исходный файл находится вне input-dir: {source_path}"
        ) from error

    return output_root / relative_path


def write_batch_results(
    report_path: Path,
    results: list[dict[str, str]],
) -> None:
    """Записывает пакетный отчёт с BOM и разделителем ``;``."""

    report_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with report_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=REPORT_COLUMNS,
            delimiter=";",
            lineterminator="\n",
            extrasaction="ignore",
        )
        writer.writeheader()

        for result in results:
            writer.writerow(
                {
                    column: result.get(column, "")
                    for column in REPORT_COLUMNS
                }
            )


def make_result(
    coordinate_row: CoordinateRow,
) -> dict[str, str]:
    return {
        "row": str(coordinate_row.row),
        "source_file": "",
        "output_file": "",
        "requested_x": coordinate_row.x,
        "requested_y": coordinate_row.y,
        "old_x": "",
        "old_y": "",
        "actual_x": "",
        "actual_y": "",
        "status": "error",
        "error": "",
    }


def run_batch(
    csv_path: Path,
    input_dir: Path,
    output_dir: Path,
    es_path: Path | None = None,
    stop_on_error: bool = False,
    delay: float = 1.0,
) -> list[dict[str, str]]:
    """Копирует и последовательно обрабатывает EMB-файлы из CSV."""

    input_root = input_dir.resolve()
    output_root = output_dir.resolve()
    report_path = output_root / "batch_results.csv"
    rows: list[CoordinateRow] = []
    results: list[dict[str, str]] = []

    try:
        if delay < 0:
            raise ValueError(
                "--delay не может быть отрицательным."
            )

        if not input_root.is_dir():
            raise NotADirectoryError(
                f"Папка input-dir не найдена: {input_root}"
            )

        output_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        rows = read_coordinate_csv(csv_path)
        total = len(rows)

        for index, coordinate_row in enumerate(
            rows,
            start=1,
        ):
            result = make_result(coordinate_row)

            try:
                display_file = (
                    coordinate_row.file
                    or "<пустой file>"
                )
                print(
                    f"[{index}/{total}] {display_file}"
                )

                requested_x = normalize_coordinate(
                    coordinate_row.x
                )
                requested_y = normalize_coordinate(
                    coordinate_row.y
                )

                result["requested_x"] = requested_x
                result["requested_y"] = requested_y

                source_path = resolve_source_path(
                    input_root,
                    coordinate_row.file,
                )
                output_path = build_output_path(
                    source_path,
                    input_root,
                    output_root,
                )

                if output_path == source_path:
                    raise ValueError(
                        "output-dir совпадает с input-dir; "
                        "исходный EMB нельзя перезаписывать."
                    )

                result["source_file"] = str(source_path)
                result["output_file"] = str(output_path)

                output_path.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )
                shutil.copy2(
                    source_path,
                    output_path,
                )

                processed = process_emb_file(
                    file_path=output_path,
                    x=requested_x,
                    y=requested_y,
                    es_path=es_path,
                    close=True,
                )

                result.update(
                    {
                        "old_x": processed["old_x"],
                        "old_y": processed["old_y"],
                        "actual_x": processed["new_x"],
                        "actual_y": processed["new_y"],
                        "status": "success",
                        "error": "",
                    }
                )

                print(
                    f"  X: {result['old_x']} "
                    f"-> {result['actual_x']}"
                )
                print(
                    f"  Y: {result['old_y']} "
                    f"-> {result['actual_y']}"
                )
                print("  OK")

            except KeyboardInterrupt:
                message = "Обработка прервана пользователем"
                result["status"] = "error"
                result["error"] = message

                print(f"  ERROR: {message}")
                results.append(result)
                raise

            except Exception as error:
                message = str(error) or type(error).__name__
                result["status"] = "error"
                result["error"] = message

                print(f"  ERROR: {message}")

                results.append(result)

                if stop_on_error:
                    raise BatchStoppedError(
                        f"Ошибка в строке {coordinate_row.row}: "
                        f"{message}"
                    ) from error

            else:
                results.append(result)

            finally:
                try:
                    for _ in range(3):
                        if (
                            dismiss_known_open_error_dialog()
                            is None
                        ):
                            break
                except Exception:
                    pass

            if delay and index < total:
                time.sleep(delay)

    finally:
        write_batch_results(
            report_path,
            results,
        )

        success_count = sum(
            result["status"] == "success"
            for result in results
        )
        error_count = sum(
            result["status"] == "error"
            for result in results
        )

        print()
        print(f"Всего строк: {len(rows)}")
        print(f"Успешно: {success_count}")
        print(f"Ошибок: {error_count}")
        print(f"Отчёт: {report_path}")

    return results


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--csv",
        type=Path,
        required=True,
        help="CSV со столбцами file, x и y",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        required=True,
        help="Корневая папка исходных EMB",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Папка обработанных копий",
    )
    parser.add_argument(
        "--es",
        type=Path,
        help="Необязательный путь к ES.EXE",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Остановить очередь после первой ошибки",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Пауза между файлами в секундах",
    )

    args = parser.parse_args()

    try:
        run_batch(
            csv_path=args.csv,
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            es_path=args.es,
            stop_on_error=args.stop_on_error,
            delay=args.delay,
        )
    except BatchStoppedError as error:
        print(
            f"Очередь остановлена: {error}",
            file=sys.stderr,
        )
        raise SystemExit(1) from error
    except Exception as error:
        print(
            f"ERROR: {error}",
            file=sys.stderr,
        )
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
