from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent

if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from automate_wilcom_batch import (
    PreparedTask,
    TaskKey,
    canonical_coordinate,
    index_results,
    make_task_key,
    preflight_batch,
    read_batch_results,
    read_coordinate_csv,
)


@dataclass(frozen=True)
class DatasetVerification:
    source_count: int
    coordinate_count: int
    expected_outputs: int
    actual_outputs: int
    report_rows: int
    retries: int


COORDINATE_TOLERANCE = Decimal("0.011")


def coordinates_match(
    actual: str,
    requested: str,
) -> bool:
    difference = abs(
        Decimal(canonical_coordinate(actual))
        - Decimal(canonical_coordinate(requested))
    )
    return difference <= COORDINATE_TOLERANCE


def normalized_path(file_path: Path) -> str:
    return os.path.normcase(
        str(file_path.resolve())
    )


def report_key(
    result: dict[str, str],
    input_dir: Path,
    output_dir: Path,
) -> TaskKey:
    return make_task_key(
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


def require_nonempty_output(task: PreparedTask) -> None:
    if not task.output_path.is_file():
        raise ValueError(
            f"Отсутствует expected output: {task.output_path}"
        )

    if task.output_path.stat().st_size <= 0:
        raise ValueError(
            f"Expected output пуст: {task.output_path}"
        )


def verify_positioned_dataset(
    csv_path: Path,
    input_dir: Path,
    output_dir: Path,
    expected_sources: int | None = None,
    expected_coordinates: int | None = None,
    expected_tasks: int | None = None,
    sources: list[str] | None = None,
) -> DatasetVerification:
    input_root = input_dir.resolve()
    output_root = output_dir.resolve()

    if not output_root.is_dir():
        raise NotADirectoryError(
            f"Output-dir не найден: {output_root}"
        )

    rows = read_coordinate_csv(csv_path)
    tasks = preflight_batch(
        rows,
        input_root,
        output_root,
    )

    if sources:
        requested_sources = {
            Path(source).as_posix().casefold()
            for source in sources
        }
        available_sources = {
            task.relative_source_file.casefold()
            for task in tasks
        }
        unknown_sources = (
            requested_sources - available_sources
        )

        if unknown_sources:
            raise ValueError(
                "Запрошенные sources отсутствуют в CSV: "
                + ", ".join(sorted(unknown_sources))
            )

        tasks = [
            task
            for task in tasks
            if (
                task.relative_source_file.casefold()
                in requested_sources
            )
        ]
    sources = {
        task.relative_source_file.casefold()
        for task in tasks
    }
    source_coordinates = {
        (
            task.relative_source_file.casefold(),
            canonical_coordinate(task.requested_x),
            canonical_coordinate(task.requested_y),
        )
        for task in tasks
    }
    coordinate_pairs = {
        (
            canonical_coordinate(task.requested_x),
            canonical_coordinate(task.requested_y),
        )
        for task in tasks
    }
    expected_paths = {
        normalized_path(task.output_path)
        for task in tasks
    }

    if len(source_coordinates) != len(tasks):
        raise ValueError(
            "CSV содержит повторяющиеся source/coordinate задачи."
        )

    if len(expected_paths) != len(tasks):
        raise ValueError(
            "CSV содержит повторяющиеся output paths."
        )

    if (
        expected_sources is not None
        and len(sources) != expected_sources
    ):
        raise ValueError(
            f"Ожидалось sources: {expected_sources}; "
            f"фактически: {len(sources)}"
        )

    if (
        expected_coordinates is not None
        and len(coordinate_pairs) != expected_coordinates
    ):
        raise ValueError(
            f"Ожидалось coordinates: {expected_coordinates}; "
            f"фактически: {len(coordinate_pairs)}"
        )

    if (
        expected_tasks is not None
        and len(tasks) != expected_tasks
    ):
        raise ValueError(
            f"Ожидалось tasks: {expected_tasks}; "
            f"фактически: {len(tasks)}"
        )

    report_path = output_root / "batch_results.csv"
    report_results = read_batch_results(
        report_path,
        input_dir=input_root,
        output_dir=output_root,
    )
    indexed_results, positions = index_results(
        report_results,
        input_root,
        output_root,
    )

    if len(indexed_results) != len(report_results):
        raise ValueError(
            "Batch report содержит повторяющиеся task rows."
        )

    expected_keys = {
        task.task_key
        for task in tasks
    }
    report_keys = {
        report_key(
            result,
            input_root,
            output_root,
        )
        for result in report_results
    }
    unexpected_keys = report_keys.difference(
        expected_keys
    )

    if unexpected_keys:
        raise ValueError(
            "Batch report содержит задачи вне canonical CSV: "
            f"{len(unexpected_keys)}"
        )

    for task in tasks:
        position = positions.get(task.task_key)

        if position is None:
            raise ValueError(
                "В batch report отсутствует задача: "
                f"{task.relative_output_file}"
            )

        result = indexed_results[position]

        if result["status"] != "success":
            raise ValueError(
                "Неразрешённая ошибка задачи: "
                f"{task.relative_output_file}: "
                f"{result['error']}"
            )

        if (
            not coordinates_match(
                result["actual_x"],
                task.requested_x,
            )
            or not coordinates_match(
                result["actual_y"],
                task.requested_y,
            )
        ):
            raise ValueError(
                "Actual coordinates не совпадают с requested: "
                f"{task.relative_output_file}"
            )

        require_nonempty_output(task)

    actual_emb_files = list(
        output_root.rglob("*.EMB")
    )
    actual_paths = {
        normalized_path(file_path)
        for file_path in actual_emb_files
    }
    extra_paths = actual_paths.difference(
        expected_paths
    )
    missing_paths = expected_paths.difference(
        actual_paths
    )

    if missing_paths:
        raise ValueError(
            f"Не хватает expected EMB outputs: {len(missing_paths)}"
        )

    if extra_paths:
        raise ValueError(
            f"Найдены лишние EMB outputs: {len(extra_paths)}"
        )

    unfinished = [
        file_path
        for file_path in actual_emb_files
        if (
            ".working" in file_path.parts
            or ".__publishing_" in file_path.name
        )
    ]

    if unfinished:
        raise ValueError(
            "Найдены незавершённые working/publishing EMB: "
            f"{len(unfinished)}"
        )

    retries = sum(
        max(
            0,
            int(result["attempts"] or "0") - 1,
        )
        for result in report_results
    )

    return DatasetVerification(
        source_count=len(sources),
        coordinate_count=len(coordinate_pairs),
        expected_outputs=len(expected_paths),
        actual_outputs=len(actual_paths),
        report_rows=len(report_results),
        retries=retries,
    )


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--csv",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--expected-sources",
        type=int,
    )
    parser.add_argument(
        "--expected-coordinates",
        type=int,
    )
    parser.add_argument(
        "--expected-tasks",
        type=int,
    )
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
    )
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()

    try:
        result = verify_positioned_dataset(
            csv_path=args.csv,
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            expected_sources=args.expected_sources,
            expected_coordinates=(
                args.expected_coordinates
            ),
            expected_tasks=args.expected_tasks,
            sources=args.sources,
        )
    except Exception as error:
        print(
            f"ERROR: {error}",
            file=sys.stderr,
        )
        raise SystemExit(1) from error

    print("Sources:", result.source_count)
    print("Coordinates:", result.coordinate_count)
    print("Expected outputs:", result.expected_outputs)
    print("Actual outputs:", result.actual_outputs)
    print("Report rows:", result.report_rows)
    print("Retries:", result.retries)
    print("VERIFIED")


if __name__ == "__main__":
    main()
