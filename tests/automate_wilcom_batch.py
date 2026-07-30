from __future__ import annotations

import argparse
import csv
import io
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent

if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from automate_wilcom_file import (
    dismiss_known_open_error_dialog,
    dismiss_save_changes_dialog,
    process_emb_file,
)


REQUIRED_COLUMNS = {"file", "x", "y"}
REPORT_COLUMNS = [
    "row",
    "source_file",
    "relative_source_file",
    "output_file",
    "relative_output_file",
    "requested_x",
    "requested_y",
    "old_x",
    "old_y",
    "actual_x",
    "actual_y",
    "status",
    "error",
    "attempts",
]
REPORT_REQUIRED_COLUMNS = set(REPORT_COLUMNS).difference(
    {
        "attempts",
        "relative_source_file",
        "relative_output_file",
    }
)
TaskKey = tuple[str, str, str, str]


@dataclass(frozen=True)
class CoordinateRow:
    row: int
    file: str
    x: str
    y: str
    output_file: str = ""


@dataclass(frozen=True)
class PreparedTask:
    coordinate_row: CoordinateRow
    source_path: Path
    output_path: Path
    relative_source_file: str
    relative_output_file: str
    requested_x: str
    requested_y: str
    task_key: TaskKey


class BatchStoppedError(RuntimeError):
    """Очередь остановлена после ошибки по запросу пользователя."""


class TaskAttemptsError(RuntimeError):
    """Все разрешённые попытки обработки файла завершились ошибкой."""

    def __init__(
        self,
        message: str,
        attempts: int,
    ) -> None:
        super().__init__(message)
        self.attempts = attempts


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
        output_file_index = (
            headers.index("output_file")
            if "output_file" in headers
            else None
        )

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
                    output_file=(
                        padded_values[
                            output_file_index
                        ].strip()
                        if output_file_index is not None
                        else ""
                    ),
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


def resolve_output_path(
    output_dir: Path,
    output_file: str,
) -> Path:
    """Безопасно разрешает пользовательский output_file."""

    output_root = output_dir.resolve()
    output_file = output_file.strip()

    if not output_file:
        raise ValueError(
            "Столбец output_file не может быть пустым."
        )

    relative_path = Path(output_file)

    if relative_path.is_absolute() or relative_path.drive:
        raise ValueError(
            "output_file должен быть относительным путём: "
            f"{output_file}"
        )

    output_path = (
        output_root
        / relative_path
    ).resolve()

    if not output_path.is_relative_to(output_root):
        raise ValueError(
            "output_file выходит за пределы output-dir: "
            f"{output_file}"
        )

    if output_path.suffix.lower() != ".emb":
        raise ValueError(
            "output_file должен иметь расширение .emb: "
            f"{output_file}"
        )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    return output_path


def paths_are_equal(
    first_path: Path,
    second_path: Path,
) -> bool:
    return os.path.normcase(
        str(first_path.resolve())
    ) == os.path.normcase(
        str(second_path.resolve())
    )


def preflight_batch(
    rows: list[CoordinateRow],
    input_dir: Path,
    output_dir: Path,
) -> list[PreparedTask]:
    """Проверяет всю очередь до первого запуска Wilcom."""

    input_root = input_dir.resolve()
    output_root = output_dir.resolve()
    prepared_tasks: list[PreparedTask] = []
    output_rows: dict[str, PreparedTask] = {}

    for coordinate_row in rows:
        try:
            requested_x = normalize_coordinate(
                coordinate_row.x
            )
            requested_y = normalize_coordinate(
                coordinate_row.y
            )
            source_path = resolve_source_path(
                input_root,
                coordinate_row.file,
            )
            relative_source = source_path.relative_to(
                input_root
            ).as_posix()

            if coordinate_row.output_file.strip():
                output_path = resolve_output_path(
                    output_root,
                    coordinate_row.output_file,
                )
            else:
                output_path = build_output_path(
                    source_path,
                    input_root,
                    output_root,
                )
                output_path.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

            relative_output = output_path.relative_to(
                output_root
            ).as_posix()

            if paths_are_equal(
                source_path,
                output_path,
            ):
                raise ValueError(
                    "исходный и выходной EMB совпадают: "
                    f"{relative_output}"
                )

            task_key = make_task_key(
                relative_source,
                requested_x,
                requested_y,
                input_root,
                output_file=relative_output,
                output_dir=output_root,
            )
            prepared_task = PreparedTask(
                coordinate_row=coordinate_row,
                source_path=source_path,
                output_path=output_path,
                relative_source_file=relative_source,
                relative_output_file=relative_output,
                requested_x=requested_x,
                requested_y=requested_y,
                task_key=task_key,
            )
            normalized_output = os.path.normcase(
                str(output_path)
            )
            conflicting_task = output_rows.get(
                normalized_output
            )

            if conflicting_task is not None:
                raise ValueError(
                    f"Строки "
                    f"{conflicting_task.coordinate_row.row} "
                    f"и {coordinate_row.row} используют "
                    "одинаковый выходной файл:\n"
                    f"{relative_output}"
                )

            output_rows[normalized_output] = prepared_task
            prepared_tasks.append(prepared_task)

        except Exception as error:
            message = str(error) or type(error).__name__

            if message.startswith("Строки "):
                raise

            raise ValueError(
                f"Ошибка preflight в строке "
                f"{coordinate_row.row}: {message}"
            ) from error

    return prepared_tasks


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


def write_batch_results_atomic(
    report_path: Path,
    results: list[dict[str, str]],
) -> None:
    """Атомарно заменяет отчёт его полностью записанной копией."""

    report_path = report_path.resolve()
    report_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{report_path.name}.",
        suffix=".tmp",
        dir=report_path.parent,
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)

    try:
        write_batch_results(
            temporary_path,
            results,
        )
        os.replace(
            temporary_path,
            report_path,
        )
    finally:
        try:
            temporary_path.unlink(
                missing_ok=True,
            )
        except OSError:
            pass


def normalize_relative_report_path(
    value: str,
    field_name: str,
) -> str:
    """Проверяет относительный EMB-путь из отчёта."""

    value = value.strip()

    if not value:
        raise ValueError(
            f"пустое значение {field_name}"
        )

    relative_path = Path(value)

    if relative_path.is_absolute() or relative_path.drive:
        raise ValueError(
            f"{field_name} должен быть относительным: {value}"
        )

    if ".." in relative_path.parts:
        raise ValueError(
            f"{field_name} выходит за корневую папку: {value}"
        )

    if relative_path.suffix.lower() != ".emb":
        raise ValueError(
            f"{field_name} должен иметь расширение .emb: "
            f"{value}"
        )

    return relative_path.as_posix()


def derive_report_relative_path(
    absolute_or_relative: str,
    root_dir: Path | None,
    field_name: str,
) -> str:
    """Восстанавливает новую относительную колонку старого отчёта."""

    value = absolute_or_relative.strip()

    if not value:
        raise ValueError(
            f"невозможно вычислить {field_name}: "
            "исходный путь пуст"
        )

    file_path = Path(value)

    if file_path.is_absolute() or file_path.drive:
        if root_dir is None:
            raise ValueError(
                f"невозможно вычислить {field_name} "
                "из абсолютного пути без корневой папки: "
                f"{value}"
            )

        try:
            file_path = file_path.resolve().relative_to(
                root_dir.resolve()
            )
        except ValueError as error:
            raise ValueError(
                f"невозможно вычислить {field_name}: "
                f"{value} находится вне {root_dir.resolve()}"
            ) from error

    return normalize_relative_report_path(
        file_path.as_posix(),
        field_name,
    )


def read_batch_results(
    report_path: Path,
    input_dir: Path | None = None,
    output_dir: Path | None = None,
) -> list[dict[str, str]]:
    """Читает и проверяет ранее созданный пакетный отчёт."""

    report_path = report_path.resolve()

    if not report_path.is_file():
        raise FileNotFoundError(
            f"Предыдущий отчёт не найден: {report_path}"
        )

    try:
        contents = report_path.read_text(
            encoding="utf-8-sig",
        )
    except UnicodeError as error:
        raise ValueError(
            f"Не удалось прочитать предыдущий отчёт "
            f"как UTF-8: {report_path}"
        ) from error

    if not contents.strip():
        return []

    reader = csv.DictReader(
        io.StringIO(contents, newline=""),
        delimiter=";",
    )

    if reader.fieldnames is None:
        raise ValueError(
            "Повреждённый предыдущий отчёт: "
            "отсутствует строка заголовка."
        )

    headers = [
        header.strip()
        for header in reader.fieldnames
        if header is not None
    ]
    missing = REPORT_REQUIRED_COLUMNS.difference(
        headers
    )

    if missing:
        names = ", ".join(sorted(missing))
        raise ValueError(
            "Повреждённый предыдущий отчёт: "
            f"отсутствуют обязательные столбцы: {names}"
        )

    results: list[dict[str, str]] = []

    for line_number, raw_result in enumerate(
        reader,
        start=2,
    ):
        if not any(
            (value or "").strip()
            for key, value in raw_result.items()
            if key is not None
        ):
            continue

        if None in raw_result:
            raise ValueError(
                "Повреждённый предыдущий отчёт: "
                f"лишние значения в строке {line_number}."
            )

        result = {
            column: (
                raw_result.get(column) or ""
            ).strip()
            for column in REPORT_COLUMNS
        }

        if result["status"] not in {
            "success",
            "error",
        }:
            raise ValueError(
                "Повреждённый предыдущий отчёт: "
                f"неизвестный status в строке {line_number}: "
                f"{result['status']!r}."
            )

        attempts = result["attempts"] or "1"

        try:
            attempts_number = int(attempts)
        except ValueError as error:
            raise ValueError(
                "Повреждённый предыдущий отчёт: "
                f"некорректный attempts в строке "
                f"{line_number}: {attempts!r}."
            ) from error

        if attempts_number < 0:
            raise ValueError(
                "Повреждённый предыдущий отчёт: "
                f"attempts не может быть отрицательным "
                f"в строке {line_number}."
            )

        result["attempts"] = str(attempts_number)

        try:
            result["relative_source_file"] = (
                normalize_relative_report_path(
                    result["relative_source_file"],
                    "relative_source_file",
                )
                if result["relative_source_file"]
                else derive_report_relative_path(
                    result["source_file"],
                    input_dir,
                    "relative_source_file",
                )
            )
            result["relative_output_file"] = (
                normalize_relative_report_path(
                    result["relative_output_file"],
                    "relative_output_file",
                )
                if result["relative_output_file"]
                else derive_report_relative_path(
                    result["output_file"],
                    output_dir,
                    "relative_output_file",
                )
            )
        except ValueError as error:
            raise ValueError(
                "Повреждённый предыдущий отчёт: "
                f"строка {line_number}: {error}"
            ) from error

        results.append(result)

    return results


def canonical_coordinate(
    value: str,
) -> str:
    """Возвращает числовую каноническую форму координаты."""

    number = Decimal(
        normalize_coordinate(value)
    )

    if number == 0:
        return "0"

    canonical = format(number, "f")

    if "." in canonical:
        canonical = canonical.rstrip("0").rstrip(".")

    return canonical


def relative_source_file(
    source_file: str,
    input_dir: Path,
) -> str:
    """Приводит путь из CSV или отчёта к относительному пути задачи."""

    source_path = Path(source_file)

    if source_path.is_absolute():
        try:
            source_path = source_path.resolve().relative_to(
                input_dir.resolve()
            )
        except ValueError:
            pass

    return source_path.as_posix().casefold()


def make_task_key(
    source_file: str,
    requested_x: str,
    requested_y: str,
    input_dir: Path,
    output_file: str = "",
    output_dir: Path | None = None,
) -> TaskKey:
    """Идентифицирует одну задачу независимо от формата десятичной дроби."""

    normalized_source = relative_source_file(
        source_file,
        input_dir,
    )

    if output_file.strip():
        normalized_output = relative_source_file(
            output_file,
            output_dir or input_dir,
        )
    else:
        normalized_output = normalized_source

    return (
        normalized_source,
        canonical_coordinate(requested_x),
        canonical_coordinate(requested_y),
        normalized_output,
    )


def index_results(
    results: list[dict[str, str]],
    input_dir: Path,
    output_dir: Path | None = None,
) -> tuple[
    list[dict[str, str]],
    dict[TaskKey, int],
]:
    """Удаляет дубликаты задач, сохраняя их последние результаты."""

    indexed_results: list[dict[str, str]] = []
    positions: dict[TaskKey, int] = {}

    for result in results:
        try:
            key = make_task_key(
                (
                    result.get("relative_source_file")
                    or result["source_file"]
                ),
                result["requested_x"],
                result["requested_y"],
                input_dir,
                output_file=(
                    result.get("relative_output_file")
                    or result["output_file"]
                ),
                output_dir=output_dir,
            )
        except (KeyError, ValueError):
            indexed_results.append(result)
            continue

        existing_position = positions.get(key)

        if existing_position is None:
            positions[key] = len(indexed_results)
            indexed_results.append(result)
        else:
            indexed_results[existing_position] = result

    return indexed_results, positions


def upsert_result(
    results: list[dict[str, str]],
    positions: dict[TaskKey, int],
    result: dict[str, str],
    key: TaskKey | None,
) -> None:
    """Добавляет результат либо заменяет прежнюю запись той же задачи."""

    if key is not None and key in positions:
        results[positions[key]] = result
        return

    if key is not None:
        positions[key] = len(results)

    results.append(result)


def reported_output_exists(
    result: dict[str, str],
    output_dir: Path,
) -> bool:
    output_value = result.get(
        "output_file",
        "",
    ).strip()

    if not output_value:
        return False

    output_path = Path(output_value)

    if not output_path.is_absolute():
        output_path = output_dir.resolve() / output_path

    return output_path.is_file()


def remove_file_best_effort(
    file_path: Path | None,
) -> None:
    if file_path is None:
        return

    try:
        file_path.unlink(
            missing_ok=True,
        )
    except OSError:
        pass


def cleanup_wilcom_best_effort() -> None:
    """Закрывает известные модальные ошибки, не маскируя исходную ошибку."""

    try:
        dismiss_save_changes_dialog(
            document_stem=None,
            save=False,
            timeout=1.0,
        )
    except Exception:
        pass

    try:
        for _ in range(3):
            if dismiss_known_open_error_dialog() is None:
                break
    except Exception:
        pass


def create_processing_copy(
    source_path: Path,
    output_path: Path,
) -> Path:
    """Создаёт рядом с output временный EMB для безопасной обработки."""

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f"{output_path.stem}.__processing_",
        suffix=".EMB",
        dir=output_path.parent,
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)

    try:
        shutil.copy2(
            source_path,
            temporary_path,
        )
    except Exception:
        remove_file_best_effort(
            temporary_path
        )
        raise

    return temporary_path


def process_file_with_retries(
    source_path: Path,
    output_path: Path,
    requested_x: str,
    requested_y: str,
    es_path: Path | None,
    retries: int,
    retry_delay: float,
) -> tuple[dict[str, str], int]:
    """Обрабатывает временные EMB и публикует output только после успеха."""

    maximum_attempts = retries + 1

    for attempt in range(1, maximum_attempts + 1):
        temporary_path: Path | None = None

        try:
            temporary_path = create_processing_copy(
                source_path,
                output_path,
            )
            processed = process_emb_file(
                file_path=temporary_path,
                x=requested_x,
                y=requested_y,
                es_path=es_path,
                close=True,
            )

            # Проверяем структуру ответа до публикации обработанного EMB.
            processed_values = {
                "old_x": processed["old_x"],
                "old_y": processed["old_y"],
                "new_x": processed["new_x"],
                "new_y": processed["new_y"],
            }

            os.replace(
                temporary_path,
                output_path,
            )
            temporary_path = None

            return processed_values, attempt

        except KeyboardInterrupt as error:
            setattr(
                error,
                "attempts",
                attempt,
            )
            raise

        except Exception as error:
            if attempt >= maximum_attempts:
                message = str(error) or type(error).__name__
                raise TaskAttemptsError(
                    message,
                    attempt,
                ) from error

            cleanup_wilcom_best_effort()
            print(
                f"  Попытка {attempt + 1}/{maximum_attempts} "
                f"после ошибки: "
                f"{str(error) or type(error).__name__}"
            )

            if retry_delay:
                try:
                    time.sleep(retry_delay)
                except KeyboardInterrupt as interrupt:
                    setattr(
                        interrupt,
                        "attempts",
                        attempt,
                    )
                    raise

        finally:
            remove_file_best_effort(
                temporary_path
            )

    raise AssertionError(
        "Недостижимое состояние повторных попыток."
    )


def make_result(
    coordinate_row: CoordinateRow,
) -> dict[str, str]:
    return {
        "row": str(coordinate_row.row),
        "source_file": "",
        "relative_source_file": "",
        "output_file": "",
        "relative_output_file": "",
        "requested_x": coordinate_row.x,
        "requested_y": coordinate_row.y,
        "old_x": "",
        "old_y": "",
        "actual_x": "",
        "actual_y": "",
        "status": "error",
        "error": "",
        "attempts": "0",
    }


def run_batch(
    csv_path: Path,
    input_dir: Path,
    output_dir: Path,
    es_path: Path | None = None,
    stop_on_error: bool = False,
    delay: float = 1.0,
    resume: bool = False,
    retry_errors: bool = False,
    retries: int = 0,
) -> list[dict[str, str]]:
    """Надёжно и последовательно обрабатывает EMB-файлы из CSV."""

    input_root = input_dir.resolve()
    output_root = output_dir.resolve()
    report_path = output_root / "batch_results.csv"
    rows: list[CoordinateRow] = []
    prepared_tasks: list[PreparedTask] = []
    results: list[dict[str, str]] = []
    positions: dict[TaskKey, int] = {}
    processed_now = 0
    skipped = 0
    row_statuses: list[str] = []
    report_ready = False
    checkpoint_current = False

    try:
        if resume and retry_errors:
            raise ValueError(
                "--resume и --retry-errors нельзя "
                "использовать одновременно."
            )

        if delay < 0:
            raise ValueError(
                "--delay не может быть отрицательным."
            )

        if retries < 0:
            raise ValueError(
                "--retries не может быть отрицательным."
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
        prepared_tasks = preflight_batch(
            rows,
            input_root,
            output_root,
        )
        total = len(prepared_tasks)

        if retry_errors and not report_path.is_file():
            raise FileNotFoundError(
                "--retry-errors требует существующий отчёт: "
                f"{report_path}"
            )

        previous_results: list[dict[str, str]] = []

        if (
            (resume or retry_errors)
            and report_path.is_file()
        ):
            previous_results = read_batch_results(
                report_path,
                input_dir=input_root,
                output_dir=output_root,
            )

        results, positions = index_results(
            previous_results,
            input_root,
            output_root,
        )
        report_ready = True
        checkpoint_current = bool(
            (resume or retry_errors)
            and report_path.is_file()
        )

        for index, prepared_task in enumerate(
            prepared_tasks,
            start=1,
        ):
            coordinate_row = prepared_task.coordinate_row
            result = make_result(coordinate_row)
            task_key: TaskKey | None = prepared_task.task_key
            row_status = ""
            should_delay = True
            counted_as_processed = False

            try:
                display_file = (
                    coordinate_row.file
                    or "<пустой file>"
                )
                print(
                    f"[{index}/{total}] {display_file}"
                )

                result.update(
                    {
                        "source_file": str(
                            prepared_task.source_path
                        ),
                        "relative_source_file": (
                            prepared_task.relative_source_file
                        ),
                        "output_file": str(
                            prepared_task.output_path
                        ),
                        "relative_output_file": (
                            prepared_task.relative_output_file
                        ),
                        "requested_x": (
                            prepared_task.requested_x
                        ),
                        "requested_y": (
                            prepared_task.requested_y
                        ),
                    }
                )

                previous_position = positions.get(
                    task_key
                )
                previous_result = (
                    results[previous_position]
                    if previous_position is not None
                    else None
                )

                if (
                    resume
                    and previous_result is not None
                    and previous_result["status"] == "success"
                    and reported_output_exists(
                        previous_result,
                        output_root,
                    )
                ):
                    skipped += 1
                    row_status = "success"
                    print(
                        "  SKIP: уже успешно обработан"
                    )
                    write_batch_results_atomic(
                        report_path,
                        results,
                    )
                    checkpoint_current = True
                    continue

                if retry_errors and (
                    previous_result is None
                    or previous_result["status"] != "error"
                ):
                    skipped += 1
                    row_status = (
                        previous_result["status"]
                        if previous_result is not None
                        else ""
                    )
                    print(
                        "  SKIP: нет предыдущей ошибки"
                    )
                    write_batch_results_atomic(
                        report_path,
                        results,
                    )
                    checkpoint_current = True
                    continue

                processed_now += 1
                counted_as_processed = True
                processed, attempts = process_file_with_retries(
                    source_path=prepared_task.source_path,
                    output_path=prepared_task.output_path,
                    requested_x=prepared_task.requested_x,
                    requested_y=prepared_task.requested_y,
                    es_path=es_path,
                    retries=retries,
                    retry_delay=delay,
                )

                result.update(
                    {
                        "old_x": processed["old_x"],
                        "old_y": processed["old_y"],
                        "actual_x": processed["new_x"],
                        "actual_y": processed["new_y"],
                        "status": "success",
                        "error": "",
                        "attempts": str(attempts),
                    }
                )
                row_status = "success"

                print(
                    f"  X: {result['old_x']} "
                    f"-> {result['actual_x']}"
                )
                print(
                    f"  Y: {result['old_y']} "
                    f"-> {result['actual_y']}"
                )
                print("  OK")

                upsert_result(
                    results,
                    positions,
                    result,
                    task_key,
                )
                checkpoint_current = False
                write_batch_results_atomic(
                    report_path,
                    results,
                )
                checkpoint_current = True

            except KeyboardInterrupt as error:
                if not counted_as_processed:
                    processed_now += 1
                    counted_as_processed = True

                message = "Обработка прервана пользователем"
                result["status"] = "error"
                result["error"] = message
                result["attempts"] = str(
                    getattr(
                        error,
                        "attempts",
                        int(result["attempts"]),
                    )
                )
                row_status = "error"

                print(f"  ERROR: {message}")
                upsert_result(
                    results,
                    positions,
                    result,
                    task_key,
                )
                checkpoint_current = False
                write_batch_results_atomic(
                    report_path,
                    results,
                )
                checkpoint_current = True
                should_delay = False
                raise

            except Exception as error:
                if not counted_as_processed:
                    processed_now += 1
                    counted_as_processed = True

                message = str(error) or type(error).__name__
                result["status"] = "error"
                result["error"] = message
                result["attempts"] = str(
                    getattr(
                        error,
                        "attempts",
                        int(result["attempts"]),
                    )
                )
                row_status = "error"

                print(f"  ERROR: {message}")

                upsert_result(
                    results,
                    positions,
                    result,
                    task_key,
                )
                checkpoint_current = False
                write_batch_results_atomic(
                    report_path,
                    results,
                )
                checkpoint_current = True

                if stop_on_error:
                    should_delay = False
                    raise BatchStoppedError(
                        f"Ошибка в строке {coordinate_row.row}: "
                        f"{message}"
                    ) from error

            finally:
                cleanup_wilcom_best_effort()
                row_statuses.append(row_status)

            if (
                should_delay
                and delay
                and index < total
            ):
                time.sleep(delay)

    finally:
        if (
            report_ready
            and not checkpoint_current
        ):
            write_batch_results_atomic(
                report_path,
                results,
            )

        success_count = sum(
            status == "success"
            for status in row_statuses
        )
        error_count = sum(
            status == "error"
            for status in row_statuses
        )

        print()
        print(f"Всего задач: {len(rows)}")
        print(f"Обработано сейчас: {processed_now}")
        print(f"Пропущено: {skipped}")
        print(f"Успешно: {success_count}")
        print(f"Ошибок: {error_count}")
        print(f"Отчёт: {report_path}")

    return results


def build_argument_parser() -> argparse.ArgumentParser:
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
    parser.add_argument(
        "--retries",
        type=int,
        default=0,
        help="Число дополнительных попыток каждого файла",
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--resume",
        action="store_true",
        help="Пропустить уже успешно обработанные задачи",
    )
    mode_group.add_argument(
        "--retry-errors",
        action="store_true",
        help="Повторить только ошибки предыдущего отчёта",
    )

    return parser


def main() -> None:
    parser = build_argument_parser()

    args = parser.parse_args()

    try:
        run_batch(
            csv_path=args.csv,
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            es_path=args.es,
            stop_on_error=args.stop_on_error,
            delay=args.delay,
            resume=args.resume,
            retry_errors=args.retry_errors,
            retries=args.retries,
        )
    except KeyboardInterrupt as error:
        print(
            "Обработка прервана пользователем.",
            file=sys.stderr,
        )
        raise SystemExit(130) from error
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
