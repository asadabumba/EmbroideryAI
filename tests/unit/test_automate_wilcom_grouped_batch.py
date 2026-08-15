from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "automate_wilcom_grouped_batch.py"
)
SPEC = importlib.util.spec_from_file_location(
    "automate_wilcom_grouped_batch_tests",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
grouped_batch = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = grouped_batch
SPEC.loader.exec_module(grouped_batch)


def write_fixture_dataset(
    tmp_path: Path,
) -> tuple[Path, Path, Path]:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    csv_path = tmp_path / "coordinates.csv"
    input_dir.mkdir()
    (input_dir / "first.EMB").write_bytes(b"first")
    (input_dir / "second.EMB").write_bytes(b"second")
    csv_path.write_text(
        "file;x;y;output_file\n"
        "first.EMB;1;10;variants/first_1.EMB\n"
        "first.EMB;2;20;variants/first_2.EMB\n"
        "second.EMB;3;30;variants/second_1.EMB\n"
        "second.EMB;4;40;variants/second_2.EMB\n",
        encoding="utf-8",
    )
    return input_dir, output_dir, csv_path


def prepared_groups(
    input_dir: Path,
    output_dir: Path,
    csv_path: Path,
) -> dict[str, list[grouped_batch.PreparedTask]]:
    rows = grouped_batch.read_coordinate_csv(csv_path)
    tasks = grouped_batch.preflight_batch(
        rows,
        input_dir,
        output_dir,
    )
    return grouped_batch.group_tasks_by_source(tasks)


def success_values(
    task: grouped_batch.PreparedTask,
) -> dict[str, str]:
    return {
        "old_x": "0",
        "old_y": "0",
        "new_x": task.requested_x,
        "new_y": task.requested_y,
    }


def test_grouped_batch_writes_atomic_checkpoints_and_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir, output_dir, csv_path = (
        write_fixture_dataset(tmp_path)
    )
    groups = prepared_groups(
        input_dir,
        output_dir,
        csv_path,
    )
    calls: list[str] = []

    def run_group(**kwargs: object) -> int:
        source = str(kwargs["source"])
        calls.append(source)
        task_filter = kwargs["task_filter"]
        success = kwargs["on_variant_success"]
        assert callable(task_filter)
        assert callable(success)
        assert kwargs["atomic_publish"] is True
        created = 0

        for task in groups[source]:
            if not task_filter(task):
                continue

            values = success_values(task)
            success(task, values)
            assert not task.output_path.exists()
            task.output_path.write_bytes(
                f"{source}:{task.requested_x}".encode()
            )
            created += 1

        return created

    monkeypatch.setattr(
        grouped_batch,
        "run_grouped_file",
        run_group,
    )

    summary = grouped_batch.run_grouped_batch(
        csv_path=csv_path,
        input_dir=input_dir,
        output_dir=output_dir,
        retry_delay=0,
    )

    assert calls == ["first.EMB", "second.EMB"]
    assert summary.processed_variants == 4
    assert summary.skipped_variants == 0
    assert summary.source_failures == {}
    assert len(summary.results) == 4
    assert {
        result["status"]
        for result in summary.results
    } == {"success"}
    report = grouped_batch.read_batch_results(
        output_dir / grouped_batch.REPORT_NAME,
        input_dir=input_dir,
        output_dir=output_dir,
    )
    assert len(report) == 4
    assert len(
        list(
            (
                output_dir
                / grouped_batch.PROGRESS_DIR_NAME
            ).glob("*.csv")
        )
    ) == 2


def test_resume_retries_only_failed_variant_and_preserves_successes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir, output_dir, csv_path = (
        write_fixture_dataset(tmp_path)
    )
    groups = prepared_groups(
        input_dir,
        output_dir,
        csv_path,
    )

    def first_run(**kwargs: object) -> int:
        source = str(kwargs["source"])
        task_filter = kwargs["task_filter"]
        success = kwargs["on_variant_success"]
        error_callback = kwargs["on_variant_error"]
        assert callable(task_filter)
        assert callable(success)
        assert callable(error_callback)
        created = 0

        for task in groups[source]:
            if not task_filter(task):
                continue

            if (
                source == "first.EMB"
                and task.requested_x == "2"
            ):
                error = RuntimeError("transient")
                error_callback(task, error, None)
                raise error

            success(task, success_values(task))
            task.output_path.write_bytes(
                f"ready:{task.requested_x}".encode()
            )
            created += 1

        return created

    monkeypatch.setattr(
        grouped_batch,
        "run_grouped_file",
        first_run,
    )
    first_summary = grouped_batch.run_grouped_batch(
        csv_path=csv_path,
        input_dir=input_dir,
        output_dir=output_dir,
        retry_delay=0,
    )
    first_output = (
        output_dir / "variants" / "first_1.EMB"
    )
    first_bytes = first_output.read_bytes()
    assert first_summary.source_failures == {
        "first.EMB": "transient"
    }
    assert first_summary.processed_variants == 3

    resumed_tasks: list[tuple[str, str]] = []

    def resumed_run(**kwargs: object) -> int:
        source = str(kwargs["source"])
        task_filter = kwargs["task_filter"]
        success = kwargs["on_variant_success"]
        assert callable(task_filter)
        assert callable(success)
        created = 0

        for task in groups[source]:
            if not task_filter(task):
                continue

            resumed_tasks.append(
                (source, task.requested_x)
            )
            success(task, success_values(task))
            task.output_path.write_bytes(b"recovered")
            created += 1

        return created

    monkeypatch.setattr(
        grouped_batch,
        "run_grouped_file",
        resumed_run,
    )
    resumed_summary = grouped_batch.run_grouped_batch(
        csv_path=csv_path,
        input_dir=input_dir,
        output_dir=output_dir,
        resume=True,
        retry_delay=0,
    )

    assert resumed_tasks == [("first.EMB", "2")]
    assert first_output.read_bytes() == first_bytes
    assert resumed_summary.skipped_variants == 3
    assert resumed_summary.processed_variants == 1
    assert resumed_summary.source_failures == {}
    assert len(resumed_summary.results) == 4
    assert {
        result["status"]
        for result in resumed_summary.results
    } == {"success"}
    recovered = next(
        result
        for result in resumed_summary.results
        if result["requested_x"] == "2"
    )
    assert recovered["attempts"] == "2"


def test_retry_reopens_group_and_increments_failed_task_attempts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir, output_dir, csv_path = (
        write_fixture_dataset(tmp_path)
    )
    groups = prepared_groups(
        input_dir,
        output_dir,
        csv_path,
    )
    calls = 0

    def flaky_group(**kwargs: object) -> int:
        nonlocal calls
        calls += 1
        source = str(kwargs["source"])
        task_filter = kwargs["task_filter"]
        success = kwargs["on_variant_success"]
        error_callback = kwargs["on_variant_error"]
        assert callable(task_filter)
        assert callable(success)
        assert callable(error_callback)
        task = groups[source][0]

        if not task_filter(task):
            return 0

        if calls == 1:
            error = RuntimeError("once")
            error_callback(task, error, None)
            raise error

        success(task, success_values(task))
        task.output_path.write_bytes(b"ready")

        for remaining in groups[source][1:]:
            if task_filter(remaining):
                success(
                    remaining,
                    success_values(remaining),
                )
                remaining.output_path.write_bytes(b"ready")

        return 2

    monkeypatch.setattr(
        grouped_batch,
        "run_grouped_file",
        flaky_group,
    )
    summary = grouped_batch.run_grouped_batch(
        csv_path=csv_path,
        input_dir=input_dir,
        output_dir=output_dir,
        retries=1,
        retry_delay=0,
        sources=["first.EMB"],
    )

    assert calls == 2
    assert summary.source_failures == {}
    first = next(
        result
        for result in summary.results
        if result["requested_x"] == "1"
    )
    second = next(
        result
        for result in summary.results
        if result["requested_x"] == "2"
    )
    assert first["attempts"] == "2"
    assert second["attempts"] == "1"


def test_resume_refuses_uncheckpointed_existing_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir, output_dir, csv_path = (
        write_fixture_dataset(tmp_path)
    )
    existing = output_dir / "variants" / "first_1.EMB"
    existing.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    existing.write_bytes(b"unknown")
    monkeypatch.setattr(
        grouped_batch,
        "run_grouped_file",
        lambda **_: pytest.fail(
            "Конфликт проверяется до первого запуска Wilcom"
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="без подтверждённого успешного grouped checkpoint",
    ):
        grouped_batch.run_grouped_batch(
            csv_path=csv_path,
            input_dir=input_dir,
            output_dir=output_dir,
            resume=True,
            retry_delay=0,
        )


def test_source_selection_normalizes_slashes_and_applies_limit(
    tmp_path: Path,
) -> None:
    input_dir, output_dir, csv_path = (
        write_fixture_dataset(tmp_path)
    )
    groups = prepared_groups(
        input_dir,
        output_dir,
        csv_path,
    )

    selected = grouped_batch.select_source_groups(
        groups,
        [r"SECOND.EMB"],
        1,
    )

    assert list(selected) == ["second.EMB"]


def test_resume_recovers_checkpointed_publishing_output(
    tmp_path: Path,
) -> None:
    input_dir, output_dir, csv_path = (
        write_fixture_dataset(tmp_path)
    )
    task = prepared_groups(
        input_dir,
        output_dir,
        csv_path,
    )["first.EMB"][0]
    result = grouped_batch.build_task_result(
        task,
        "success",
        1,
        values=success_values(task),
    )
    results, positions = grouped_batch.index_results(
        [result],
        input_dir,
        output_dir,
    )
    publishing = task.output_path.with_name(
        f".{task.output_path.stem}"
        ".__publishing_deadbeef.EMB"
    )
    publishing.write_bytes(b"ready")
    working = (
        output_dir
        / ".working"
        / "first__groupwork_deadbeef.EMB"
    )
    working.parent.mkdir()
    working.write_bytes(b"source")

    grouped_batch.recover_stale_group_artifacts(
        [task],
        results,
        positions,
        output_dir,
        resume=True,
    )

    assert task.output_path.read_bytes() == b"ready"
    assert not publishing.exists()
    assert not working.exists()


def test_fresh_run_refuses_stale_group_artifact(
    tmp_path: Path,
) -> None:
    input_dir, output_dir, csv_path = (
        write_fixture_dataset(tmp_path)
    )
    task = prepared_groups(
        input_dir,
        output_dir,
        csv_path,
    )["first.EMB"][0]
    publishing = task.output_path.with_name(
        f".{task.output_path.stem}"
        ".__publishing_deadbeef.EMB"
    )
    publishing.write_bytes(b"ready")

    with pytest.raises(
        RuntimeError,
        match="Найден незавершённый grouped artifact",
    ):
        grouped_batch.recover_stale_group_artifacts(
            [task],
            [],
            {},
            output_dir,
            resume=False,
        )
