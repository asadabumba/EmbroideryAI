from __future__ import annotations

import argparse
import hashlib
import sys
import time
from dataclasses import dataclass
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent

if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from automate_wilcom_batch import (
    PreparedTask,
    TaskKey,
    index_results,
    make_result,
    make_task_key,
    preflight_batch,
    read_batch_results,
    read_coordinate_csv,
    upsert_result,
    write_batch_results_atomic,
)
from automate_wilcom_grouped_file import (
    publish_variant_when_unlocked,
    run_grouped_file,
)


PROGRESS_DIR_NAME = ".grouped_progress"
REPORT_NAME = "batch_results.csv"


@dataclass(frozen=True)
class GroupedBatchSummary:
    results: list[dict[str, str]]
    source_failures: dict[str, str]
    processed_variants: int
    skipped_variants: int


def nonempty_file_exists(file_path: Path) -> bool:
    try:
        return file_path.is_file() and file_path.stat().st_size > 0
    except OSError:
        return False


def result_key(
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


def task_is_verified(
    task: PreparedTask,
    positions: dict[TaskKey, int],
    results: list[dict[str, str]],
) -> bool:
    position = positions.get(task.task_key)

    if position is None:
        return False

    result = results[position]

    return (
        result.get("status") == "success"
        and nonempty_file_exists(task.output_path)
    )


def checkpoint_path(
    progress_dir: Path,
    relative_source_file: str,
) -> Path:
    digest = hashlib.sha256(
        relative_source_file.casefold().encode("utf-8")
    ).hexdigest()
    return progress_dir / f"{digest}.csv"


def load_grouped_results(
    report_path: Path,
    progress_dir: Path,
    input_dir: Path,
    output_dir: Path,
) -> tuple[list[dict[str, str]], dict[TaskKey, int]]:
    loaded: list[dict[str, str]] = []

    if report_path.is_file():
        loaded.extend(
            read_batch_results(
                report_path,
                input_dir=input_dir,
                output_dir=output_dir,
            )
        )

    if progress_dir.is_dir():
        for progress_path in sorted(
            progress_dir.glob("*.csv")
        ):
            loaded.extend(
                read_batch_results(
                    progress_path,
                    input_dir=input_dir,
                    output_dir=output_dir,
                )
            )

    return index_results(
        loaded,
        input_dir,
        output_dir,
    )


def group_tasks_by_source(
    tasks: list[PreparedTask],
) -> dict[str, list[PreparedTask]]:
    groups: dict[str, list[PreparedTask]] = {}

    for task in tasks:
        groups.setdefault(
            task.relative_source_file,
            [],
        ).append(task)

    return groups


def select_source_groups(
    groups: dict[str, list[PreparedTask]],
    sources: list[str] | None,
    source_limit: int | None,
) -> dict[str, list[PreparedTask]]:
    if source_limit is not None and source_limit <= 0:
        raise ValueError(
            "--source-limit должен быть больше нуля."
        )

    selected = groups

    if sources:
        normalized_groups = {
            source.casefold(): source
            for source in groups
        }
        selected = {}

        for requested_source in sources:
            source_key = requested_source.strip().replace(
                "\\",
                "/",
            ).casefold()
            canonical_source = normalized_groups.get(
                source_key
            )

            if canonical_source is None:
                raise ValueError(
                    "В CSV нет source для grouped batch: "
                    f"{requested_source}"
                )

            selected.setdefault(
                canonical_source,
                groups[canonical_source],
            )

    if source_limit is not None:
        selected = dict(
            list(selected.items())[:source_limit]
        )

    return selected


def build_task_result(
    task: PreparedTask,
    status: str,
    attempts: int,
    values: dict[str, str] | None = None,
    error: str = "",
) -> dict[str, str]:
    result = make_result(
        task.coordinate_row
    )
    result.update(
        {
            "source_file": str(task.source_path),
            "relative_source_file": (
                task.relative_source_file
            ),
            "output_file": str(task.output_path),
            "relative_output_file": (
                task.relative_output_file
            ),
            "requested_x": task.requested_x,
            "requested_y": task.requested_y,
            "status": status,
            "error": error,
            "attempts": str(attempts),
        }
    )

    if values is not None:
        result.update(
            {
                "old_x": values.get("old_x", ""),
                "old_y": values.get("old_y", ""),
                "actual_x": values.get("new_x", ""),
                "actual_y": values.get("new_y", ""),
            }
        )

    return result


def previous_attempts(
    task: PreparedTask,
    positions: dict[TaskKey, int],
    results: list[dict[str, str]],
) -> int:
    position = positions.get(task.task_key)

    if position is None:
        return 0

    return int(
        results[position].get("attempts", "0") or "0"
    )


def ensure_outputs_are_resumable(
    tasks: list[PreparedTask],
    results: list[dict[str, str]],
    positions: dict[TaskKey, int],
    resume: bool,
) -> None:
    existing = [
        task
        for task in tasks
        if task.output_path.exists()
    ]

    if not existing:
        return

    if not resume:
        raise FileExistsError(
            "Output-dir уже содержит variant EMB. "
            "Используйте --resume только с валидным checkpoint: "
            f"{existing[0].output_path}"
        )

    for task in existing:
        if not task_is_verified(
            task,
            positions,
            results,
        ):
            raise RuntimeError(
                "Найден final output без подтверждённого "
                "успешного grouped checkpoint; файл не будет "
                f"перезаписан: {task.output_path}"
            )


def result_reports_success(
    task: PreparedTask,
    results: list[dict[str, str]],
    positions: dict[TaskKey, int],
) -> bool:
    position = positions.get(task.task_key)

    return (
        position is not None
        and results[position].get("status") == "success"
    )


def recover_stale_group_artifacts(
    tasks: list[PreparedTask],
    results: list[dict[str, str]],
    positions: dict[TaskKey, int],
    output_dir: Path,
    resume: bool,
) -> None:
    output_root = output_dir.resolve()
    working_files = list(
        (output_root / ".working").glob(
            "*__groupwork_*.EMB"
        )
    )
    publishing_files = list(
        output_root.rglob(
            ".*.__publishing_*.EMB"
        )
    )

    if not working_files and not publishing_files:
        return

    if not resume:
        artifact = (
            working_files + publishing_files
        )[0]
        raise RuntimeError(
            "Найден незавершённый grouped artifact. "
            "Проверьте, что другой Wilcom job не запущен, "
            f"затем используйте --resume: {artifact}"
        )

    task_by_publishing_prefix = {
        (
            task.output_path.parent.resolve(),
            f".{task.output_path.stem}.__publishing_",
        ): task
        for task in tasks
    }

    for publishing_path in publishing_files:
        matching = [
            task
            for (parent, prefix), task in (
                task_by_publishing_prefix.items()
            )
            if (
                publishing_path.parent.resolve() == parent
                and publishing_path.name.startswith(prefix)
            )
        ]

        if len(matching) != 1:
            raise RuntimeError(
                "Не удалось однозначно сопоставить publishing "
                f"artifact с canonical task: {publishing_path}"
            )

        task = matching[0]

        if task.output_path.exists():
            if not task_is_verified(
                task,
                positions,
                results,
            ):
                raise RuntimeError(
                    "Publishing artifact конфликтует с "
                    "неподтверждённым final output: "
                    f"{task.output_path}"
                )

            publishing_path.unlink()
            print(
                "Удалён stale publishing artifact: ",
                publishing_path,
                sep="",
            )
            continue

        if (
            result_reports_success(
                task,
                results,
                positions,
            )
            and nonempty_file_exists(publishing_path)
        ):
            publish_variant_when_unlocked(
                publishing_path,
                task.output_path,
            )
            print(
                "Восстановлен checkpointed output: ",
                task.output_path,
                sep="",
            )
        else:
            publishing_path.unlink()
            print(
                "Удалён незавершённый publishing artifact: ",
                publishing_path,
                sep="",
            )

    for working_path in working_files:
        working_path.unlink()
        print(
            "Удалён stale grouped working copy: ",
            working_path,
            sep="",
        )


def merge_source_results(
    all_results: list[dict[str, str]],
    all_positions: dict[TaskKey, int],
    source_results: list[dict[str, str]],
    input_dir: Path,
    output_dir: Path,
) -> None:
    for result in source_results:
        upsert_result(
            all_results,
            all_positions,
            result,
            result_key(
                result,
                input_dir,
                output_dir,
            ),
        )


def run_grouped_batch(
    csv_path: Path,
    input_dir: Path,
    output_dir: Path,
    es_path: Path | None = None,
    resume: bool = False,
    retries: int = 0,
    retry_delay: float = 1.0,
    stop_on_error: bool = False,
    sources: list[str] | None = None,
    source_limit: int | None = None,
    timings: bool = False,
) -> GroupedBatchSummary:
    if retries < 0:
        raise ValueError(
            "--retries не может быть отрицательным."
        )

    if retry_delay < 0:
        raise ValueError(
            "--retry-delay не может быть отрицательным."
        )

    input_root = input_dir.resolve()
    output_root = output_dir.resolve()
    report_path = output_root / REPORT_NAME
    progress_dir = output_root / PROGRESS_DIR_NAME
    rows = read_coordinate_csv(csv_path)
    prepared_tasks = preflight_batch(
        rows,
        input_root,
        output_root,
    )
    groups = select_source_groups(
        group_tasks_by_source(prepared_tasks),
        sources,
        source_limit,
    )
    selected_tasks = [
        task
        for group_tasks in groups.values()
        for task in group_tasks
    ]

    if not resume and (
        report_path.exists()
        or progress_dir.exists()
    ):
        raise FileExistsError(
            "Grouped checkpoint уже существует. "
            "Используйте --resume после проверки output-dir."
        )

    results, positions = load_grouped_results(
        report_path,
        progress_dir,
        input_root,
        output_root,
    )
    recover_stale_group_artifacts(
        selected_tasks,
        results,
        positions,
        output_root,
        resume,
    )
    ensure_outputs_are_resumable(
        selected_tasks,
        results,
        positions,
        resume,
    )
    progress_dir.mkdir(
        parents=True,
        exist_ok=True,
    )
    skipped_variants = sum(
        task_is_verified(
            task,
            positions,
            results,
        )
        for task in selected_tasks
    )
    source_failures: dict[str, str] = {}
    total_groups = len(groups)

    for group_index, (
        source,
        group_tasks,
    ) in enumerate(
        groups.items(),
        start=1,
    ):
        print()
        print(
            f"=== Group {group_index}/{total_groups}: "
            f"{source} ==="
        )
        group_keys = {
            task.task_key
            for task in group_tasks
        }
        source_results = [
            result
            for result in results
            if result_key(
                result,
                input_root,
                output_root,
            ) in group_keys
        ]
        source_results, source_positions = index_results(
            source_results,
            input_root,
            output_root,
        )
        progress_path = checkpoint_path(
            progress_dir,
            source,
        )
        group_completed = False

        for group_attempt in range(
            1,
            retries + 2,
        ):
            missing_keys = {
                task.task_key
                for task in group_tasks
                if not task_is_verified(
                    task,
                    source_positions,
                    source_results,
                )
            }

            if not missing_keys:
                group_completed = True
                break

            current_attempts: dict[TaskKey, int] = {}

            def attempt_number(task: PreparedTask) -> int:
                return current_attempts.setdefault(
                    task.task_key,
                    previous_attempts(
                        task,
                        source_positions,
                        source_results,
                    )
                    + 1,
                )

            def checkpoint_result(
                result: dict[str, str],
                task: PreparedTask,
            ) -> None:
                upsert_result(
                    source_results,
                    source_positions,
                    result,
                    task.task_key,
                )
                write_batch_results_atomic(
                    progress_path,
                    source_results,
                )

            def variant_success(
                task: PreparedTask,
                values: dict[str, str],
            ) -> None:
                checkpoint_result(
                    build_task_result(
                        task,
                        "success",
                        attempt_number(task),
                        values=values,
                    ),
                    task,
                )

            def variant_error(
                task: PreparedTask,
                error: BaseException,
                values: dict[str, str] | None,
            ) -> None:
                checkpoint_result(
                    build_task_result(
                        task,
                        "error",
                        attempt_number(task),
                        values=values,
                        error=(
                            str(error)
                            or type(error).__name__
                        ),
                    ),
                    task,
                )

            try:
                run_grouped_file(
                    csv_path=csv_path,
                    input_dir=input_root,
                    output_dir=output_root,
                    source=source,
                    es_path=es_path,
                    timings=timings,
                    task_filter=(
                        lambda task: (
                            task.task_key in missing_keys
                        )
                    ),
                    on_variant_success=variant_success,
                    on_variant_error=variant_error,
                    atomic_publish=True,
                )
                group_completed = all(
                    task_is_verified(
                        task,
                        source_positions,
                        source_results,
                    )
                    for task in group_tasks
                )

                if not group_completed:
                    raise RuntimeError(
                        "Grouped run завершился без полного "
                        "подтверждённого checkpoint."
                    )

                break

            except KeyboardInterrupt:
                merge_source_results(
                    results,
                    positions,
                    source_results,
                    input_root,
                    output_root,
                )
                write_batch_results_atomic(
                    report_path,
                    results,
                )
                raise

            except Exception as error:
                message = str(error) or type(error).__name__
                print(
                    f"Group attempt {group_attempt}/"
                    f"{retries + 1} failed: {message}"
                )

                if group_attempt <= retries:
                    if retry_delay:
                        time.sleep(retry_delay)
                    continue

                source_failures[source] = message

        merge_source_results(
            results,
            positions,
            source_results,
            input_root,
            output_root,
        )
        write_batch_results_atomic(
            report_path,
            results,
        )

        if not group_completed and stop_on_error:
            break

    final_verified = sum(
        task_is_verified(
            task,
            positions,
            results,
        )
        for task in selected_tasks
    )

    return GroupedBatchSummary(
        results=results,
        source_failures=source_failures,
        processed_variants=(
            final_verified - skipped_variants
        ),
        skipped_variants=skipped_variants,
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
        "--es",
        type=Path,
    )
    parser.add_argument(
        "--resume",
        action="store_true",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
    )
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
    )
    parser.add_argument(
        "--source-limit",
        type=int,
    )
    parser.add_argument(
        "--timings",
        action="store_true",
    )
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()

    try:
        summary = run_grouped_batch(
            csv_path=args.csv,
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            es_path=args.es,
            resume=args.resume,
            retries=args.retries,
            retry_delay=args.retry_delay,
            stop_on_error=args.stop_on_error,
            sources=args.sources,
            source_limit=args.source_limit,
            timings=args.timings,
        )
    except KeyboardInterrupt as error:
        print(
            "Grouped batch прерван пользователем.",
            file=sys.stderr,
        )
        raise SystemExit(130) from error
    except Exception as error:
        print(
            f"ERROR: {error}",
            file=sys.stderr,
        )
        raise SystemExit(1) from error

    print()
    print("Обработано вариантов:", summary.processed_variants)
    print("Пропущено вариантов:", summary.skipped_variants)
    print("Ошибок source:", len(summary.source_failures))
    print(
        "Отчёт:",
        args.output_dir.resolve() / REPORT_NAME,
    )

    if summary.source_failures:
        for source, message in summary.source_failures.items():
            print(
                f"ERROR {source}: {message}",
                file=sys.stderr,
            )
        raise SystemExit(1)

if __name__ == "__main__":
    main()
