from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "automate_wilcom_batch.py"
)
SPEC = importlib.util.spec_from_file_location(
    "automate_wilcom_batch",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
batch = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = batch
SPEC.loader.exec_module(batch)


def test_read_coordinate_csv_with_semicolon(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "coordinates.csv"
    csv_path.write_text(
        "file;x;y\n"
        "Ghost/ghost_01.EMB;14;0.74\n"
        "\n",
        encoding="utf-8",
    )

    rows = batch.read_coordinate_csv(csv_path)

    assert rows == [
        batch.CoordinateRow(
            row=1,
            file="Ghost/ghost_01.EMB",
            x="14",
            y="0.74",
        )
    ]


def test_read_coordinate_csv_with_comma(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "coordinates.csv"
    csv_path.write_text(
        "file,x,y\n"
        'Ghost/ghost_01.EMB,"14,5","0,74"\n',
        encoding="utf-8",
    )

    rows = batch.read_coordinate_csv(csv_path)

    assert rows[0].file == "Ghost/ghost_01.EMB"
    assert rows[0].x == "14,5"
    assert rows[0].y == "0,74"


def test_read_coordinate_csv_with_utf8_bom_and_clean_headers(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "coordinates.csv"
    csv_path.write_text(
        " FILE ; X ; Y \n"
        "Ghost/ghost_01.EMB;14;0.74\n",
        encoding="utf-8-sig",
    )

    rows = batch.read_coordinate_csv(csv_path)

    assert len(rows) == 1
    assert rows[0].file == "Ghost/ghost_01.EMB"


def test_read_coordinate_csv_requires_all_columns(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "coordinates.csv"
    csv_path.write_text(
        "file;x\nGhost/ghost_01.EMB;14\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="обязательные столбцы: y",
    ):
        batch.read_coordinate_csv(csv_path)


def test_resolve_source_path_rejects_parent_escape(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (tmp_path / "outside.EMB").write_bytes(b"EMB")

    with pytest.raises(
        ValueError,
        match="за пределы input-dir",
    ):
        batch.resolve_source_path(
            input_dir,
            "../outside.EMB",
        )


def test_build_output_path_preserves_subdirectories(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    source_path = (
        input_dir
        / "Ghost"
        / "ghost_01.EMB"
    )
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"EMB")

    result = batch.build_output_path(
        source_path,
        input_dir,
        output_dir,
    )

    assert result == (
        output_dir.resolve()
        / "Ghost"
        / "ghost_01.EMB"
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("14", "14"),
        (" 14.00 ", "14.00"),
        ("0,74", "0.74"),
        ("-1,25", "-1.25"),
    ],
)
def test_normalize_coordinate(
    value: str,
    expected: str,
) -> None:
    assert batch.normalize_coordinate(value) == expected


@pytest.mark.parametrize(
    "value",
    ["", "not-a-number", "NaN", "Infinity"],
)
def test_normalize_coordinate_rejects_invalid_values(
    value: str,
) -> None:
    with pytest.raises(ValueError):
        batch.normalize_coordinate(value)


def test_write_batch_results(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "batch_results.csv"
    results = [
        {
            "row": "1",
            "source_file": "input/Ghost/ghost_01.EMB",
            "relative_source_file": "Ghost/ghost_01.EMB",
            "output_file": "output/Ghost/ghost_01.EMB",
            "relative_output_file": "Ghost/ghost_01.EMB",
            "requested_x": "14.00",
            "requested_y": "0.74",
            "old_x": "0.00",
            "old_y": "0.78",
            "actual_x": "14.00",
            "actual_y": "0.74",
            "status": "success",
            "error": "",
            "attempts": "1",
        }
    ]

    batch.write_batch_results(
        report_path,
        results,
    )

    assert report_path.read_bytes().startswith(
        b"\xef\xbb\xbf"
    )

    with report_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        reader = csv.DictReader(
            handle,
            delimiter=";",
        )
        written_rows = list(reader)

    assert reader.fieldnames == batch.REPORT_COLUMNS
    assert written_rows == results


def test_keyboard_interrupt_records_current_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    csv_path = tmp_path / "coordinates.csv"
    first_file = input_dir / "first.EMB"
    second_file = input_dir / "second.EMB"

    input_dir.mkdir()
    first_file.write_bytes(b"first")
    second_file.write_bytes(b"second")
    csv_path.write_text(
        "file;x;y\n"
        "first.EMB;1;2\n"
        "second.EMB;3;4\n",
        encoding="utf-8",
    )

    def interrupt_processing(**_) -> dict[str, str]:
        raise KeyboardInterrupt

    cleanup_calls = 0

    def cleanup_dialog() -> None:
        nonlocal cleanup_calls
        cleanup_calls += 1
        return None

    monkeypatch.setattr(
        batch,
        "process_emb_file",
        interrupt_processing,
    )
    monkeypatch.setattr(
        batch,
        "dismiss_known_open_error_dialog",
        cleanup_dialog,
    )

    with pytest.raises(KeyboardInterrupt):
        batch.run_batch(
            csv_path=csv_path,
            input_dir=input_dir,
            output_dir=output_dir,
            delay=0,
        )

    report_path = output_dir / "batch_results.csv"

    with report_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        rows = list(
            csv.DictReader(
                handle,
                delimiter=";",
            )
        )

    assert len(rows) == 1
    assert rows[0]["row"] == "1"
    assert rows[0]["status"] == "error"
    assert (
        rows[0]["error"]
        == "Обработка прервана пользователем"
    )
    assert cleanup_calls == 1


def test_batch_cleans_dialog_before_next_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    csv_path = tmp_path / "coordinates.csv"

    input_dir.mkdir()
    (input_dir / "first.EMB").write_bytes(b"first")
    (input_dir / "second.EMB").write_bytes(b"second")
    csv_path.write_text(
        "file;x;y\n"
        "first.EMB;1;2\n"
        "second.EMB;3;4\n",
        encoding="utf-8",
    )

    process_calls = 0

    def process_file(**_) -> dict[str, str]:
        nonlocal process_calls
        process_calls += 1

        if process_calls == 1:
            raise RuntimeError("Ошибка открытия")

        return {
            "file": "second.EMB",
            "old_x": "0.00",
            "old_y": "0.00",
            "new_x": "3.00",
            "new_y": "4.00",
            "status": "success",
        }

    cleanup_calls = 0

    def cleanup_dialog() -> None:
        nonlocal cleanup_calls
        cleanup_calls += 1
        return None

    monkeypatch.setattr(
        batch,
        "process_emb_file",
        process_file,
    )
    monkeypatch.setattr(
        batch,
        "dismiss_known_open_error_dialog",
        cleanup_dialog,
    )

    results = batch.run_batch(
        csv_path=csv_path,
        input_dir=input_dir,
        output_dir=output_dir,
        delay=0,
    )

    assert [
        result["status"]
        for result in results
    ] == ["error", "success"]
    assert cleanup_calls == 2


def make_report_result(
    row: int,
    source_path: Path,
    output_path: Path,
    x: str,
    y: str,
    status: str,
    error: str = "",
    attempts: str = "1",
) -> dict[str, str]:
    return {
        "row": str(row),
        "source_file": str(source_path),
        "relative_source_file": source_path.name,
        "output_file": str(output_path),
        "relative_output_file": output_path.name,
        "requested_x": x,
        "requested_y": y,
        "old_x": "0.00",
        "old_y": "0.00",
        "actual_x": x if status == "success" else "",
        "actual_y": y if status == "success" else "",
        "status": status,
        "error": error,
        "attempts": attempts,
    }


def successful_processing(
    **kwargs: object,
) -> dict[str, str]:
    return {
        "file": str(kwargs["file_path"]),
        "old_x": "0.00",
        "old_y": "0.00",
        "new_x": str(kwargs["x"]),
        "new_y": str(kwargs["y"]),
        "status": "success",
    }


def test_write_batch_results_atomic_creates_valid_csv(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "batch_results.csv"
    result = make_report_result(
        1,
        tmp_path / "input.EMB",
        tmp_path / "output.EMB",
        "1.50",
        "2",
        "success",
    )

    batch.write_batch_results_atomic(
        report_path,
        [result],
    )

    assert report_path.read_bytes().startswith(
        b"\xef\xbb\xbf"
    )
    assert batch.read_batch_results(
        report_path
    ) == [result]
    assert not list(
        tmp_path.glob(".batch_results.csv.*.tmp")
    )


def test_checkpoint_is_written_after_every_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    csv_path = tmp_path / "coordinates.csv"
    input_dir.mkdir()
    (input_dir / "first.EMB").write_bytes(b"first")
    (input_dir / "second.EMB").write_bytes(b"second")
    csv_path.write_text(
        "file;x;y\n"
        "first.EMB;1;2\n"
        "second.EMB;3;4\n",
        encoding="utf-8",
    )
    checkpoints: list[list[str]] = []

    def record_checkpoint(
        _report_path: Path,
        results: list[dict[str, str]],
    ) -> None:
        checkpoints.append(
            [result["status"] for result in results]
        )

    monkeypatch.setattr(
        batch,
        "process_emb_file",
        successful_processing,
    )
    monkeypatch.setattr(
        batch,
        "write_batch_results_atomic",
        record_checkpoint,
    )
    monkeypatch.setattr(
        batch,
        "cleanup_wilcom_best_effort",
        lambda: None,
    )

    batch.run_batch(
        csv_path=csv_path,
        input_dir=input_dir,
        output_dir=output_dir,
        delay=0,
    )

    assert checkpoints == [
        ["success"],
        ["success", "success"],
    ]


def test_resume_skips_existing_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    csv_path = tmp_path / "coordinates.csv"
    source_path = input_dir / "design.EMB"
    output_path = output_dir / "design.EMB"
    input_dir.mkdir()
    output_dir.mkdir()
    source_path.write_bytes(b"source")
    output_path.write_bytes(b"ready")
    csv_path.write_text(
        "file;x;y\ndesign.EMB;1,50;2\n",
        encoding="utf-8",
    )
    batch.write_batch_results_atomic(
        output_dir / "batch_results.csv",
        [
            make_report_result(
                1,
                source_path,
                output_path,
                "1.50",
                "2.0",
                "success",
            )
        ],
    )

    def must_not_process(**_: object) -> dict[str, str]:
        raise AssertionError("Задача не должна запускаться")

    monkeypatch.setattr(
        batch,
        "process_emb_file",
        must_not_process,
    )
    monkeypatch.setattr(
        batch,
        "cleanup_wilcom_best_effort",
        lambda: None,
    )

    results = batch.run_batch(
        csv_path=csv_path,
        input_dir=input_dir,
        output_dir=output_dir,
        delay=0,
        resume=True,
    )

    assert len(results) == 1
    assert results[0]["status"] == "success"
    assert output_path.read_bytes() == b"ready"


def test_resume_reprocesses_success_with_missing_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    csv_path = tmp_path / "coordinates.csv"
    source_path = input_dir / "design.EMB"
    output_path = output_dir / "design.EMB"
    input_dir.mkdir()
    output_dir.mkdir()
    source_path.write_bytes(b"source")
    csv_path.write_text(
        "file;x;y\ndesign.EMB;1.5;2\n",
        encoding="utf-8",
    )
    batch.write_batch_results_atomic(
        output_dir / "batch_results.csv",
        [
            make_report_result(
                1,
                source_path,
                output_path,
                "1.50",
                "2",
                "success",
            )
        ],
    )
    calls = 0

    def process(**kwargs: object) -> dict[str, str]:
        nonlocal calls
        calls += 1
        return successful_processing(**kwargs)

    monkeypatch.setattr(
        batch,
        "process_emb_file",
        process,
    )
    monkeypatch.setattr(
        batch,
        "cleanup_wilcom_best_effort",
        lambda: None,
    )

    results = batch.run_batch(
        csv_path=csv_path,
        input_dir=input_dir,
        output_dir=output_dir,
        delay=0,
        resume=True,
    )

    assert calls == 1
    assert len(results) == 1
    assert results[0]["status"] == "success"
    assert output_path.read_bytes() == b"source"


def test_retry_errors_runs_only_errors_and_replaces_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    csv_path = tmp_path / "coordinates.csv"
    input_dir.mkdir()
    output_dir.mkdir()
    first_source = input_dir / "first.EMB"
    second_source = input_dir / "second.EMB"
    first_output = output_dir / "first.EMB"
    second_output = output_dir / "second.EMB"
    first_source.write_bytes(b"first")
    second_source.write_bytes(b"second")
    first_output.write_bytes(b"ready")
    csv_path.write_text(
        "file;x;y\n"
        "first.EMB;1;2\n"
        "second.EMB;3;4\n",
        encoding="utf-8",
    )
    batch.write_batch_results_atomic(
        output_dir / "batch_results.csv",
        [
            make_report_result(
                1,
                first_source,
                first_output,
                "1",
                "2",
                "success",
            ),
            make_report_result(
                2,
                second_source,
                second_output,
                "3",
                "4",
                "error",
                "old error",
            ),
        ],
    )
    processed_names: list[str] = []

    def process(**kwargs: object) -> dict[str, str]:
        processed_names.append(
            Path(str(kwargs["file_path"])).name
        )
        return successful_processing(**kwargs)

    monkeypatch.setattr(
        batch,
        "process_emb_file",
        process,
    )
    monkeypatch.setattr(
        batch,
        "cleanup_wilcom_best_effort",
        lambda: None,
    )

    results = batch.run_batch(
        csv_path=csv_path,
        input_dir=input_dir,
        output_dir=output_dir,
        delay=0,
        retry_errors=True,
    )

    assert len(processed_names) == 1
    assert processed_names[0].startswith(
        "second.__processing_"
    )
    assert len(results) == 2
    assert [
        result["status"]
        for result in results
    ] == ["success", "success"]
    assert len(
        batch.read_batch_results(
            output_dir / "batch_results.csv"
        )
    ) == 2


def test_resume_and_retry_errors_are_mutually_exclusive() -> None:
    parser = batch.build_argument_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "--csv",
                "coordinates.csv",
                "--input-dir",
                "input",
                "--output-dir",
                "output",
                "--resume",
                "--retry-errors",
            ]
        )


def test_retries_zero_calls_process_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "source.EMB"
    output_path = tmp_path / "output.EMB"
    source_path.write_bytes(b"source")
    calls = 0

    def fail(**_: object) -> dict[str, str]:
        nonlocal calls
        calls += 1
        raise RuntimeError("failure")

    monkeypatch.setattr(
        batch,
        "process_emb_file",
        fail,
    )
    monkeypatch.setattr(
        batch,
        "cleanup_wilcom_best_effort",
        lambda: None,
    )

    with pytest.raises(
        batch.TaskAttemptsError,
    ) as captured:
        batch.process_file_with_retries(
            source_path,
            output_path,
            "1",
            "2",
            None,
            retries=0,
            retry_delay=0,
        )

    assert calls == 1
    assert captured.value.attempts == 1


def test_retries_two_can_call_process_three_times(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "source.EMB"
    output_path = tmp_path / "output.EMB"
    source_path.write_bytes(b"source")
    calls = 0

    def process(**kwargs: object) -> dict[str, str]:
        nonlocal calls
        calls += 1

        if calls < 3:
            raise RuntimeError(f"failure {calls}")

        return successful_processing(**kwargs)

    monkeypatch.setattr(
        batch,
        "process_emb_file",
        process,
    )
    monkeypatch.setattr(
        batch,
        "cleanup_wilcom_best_effort",
        lambda: None,
    )

    _, attempts = batch.process_file_with_retries(
        source_path,
        output_path,
        "1",
        "2",
        None,
        retries=2,
        retry_delay=0,
    )

    assert calls == 3
    assert attempts == 3
    assert output_path.is_file()


def test_attempts_is_written_after_retry_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    csv_path = tmp_path / "coordinates.csv"
    input_dir.mkdir()
    (input_dir / "design.EMB").write_bytes(b"source")
    csv_path.write_text(
        "file;x;y\ndesign.EMB;1;2\n",
        encoding="utf-8",
    )
    calls = 0

    def process(**kwargs: object) -> dict[str, str]:
        nonlocal calls
        calls += 1

        if calls == 1:
            raise RuntimeError("try again")

        return successful_processing(**kwargs)

    monkeypatch.setattr(
        batch,
        "process_emb_file",
        process,
    )
    monkeypatch.setattr(
        batch,
        "cleanup_wilcom_best_effort",
        lambda: None,
    )

    results = batch.run_batch(
        csv_path=csv_path,
        input_dir=input_dir,
        output_dir=output_dir,
        delay=0,
        retries=1,
    )

    assert results[0]["attempts"] == "2"


def test_temporary_emb_is_published_only_after_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "source.EMB"
    output_path = tmp_path / "output.EMB"
    source_path.write_bytes(b"source")
    seen_temporary_path: Path | None = None

    def process(**kwargs: object) -> dict[str, str]:
        nonlocal seen_temporary_path
        assert not output_path.exists()
        seen_temporary_path = Path(
            str(kwargs["file_path"])
        )
        assert seen_temporary_path.suffix == ".EMB"
        seen_temporary_path.write_bytes(b"processed")
        return successful_processing(**kwargs)

    monkeypatch.setattr(
        batch,
        "process_emb_file",
        process,
    )

    batch.process_file_with_retries(
        source_path,
        output_path,
        "1",
        "2",
        None,
        retries=0,
        retry_delay=0,
    )

    assert output_path.read_bytes() == b"processed"
    assert seen_temporary_path is not None
    assert not seen_temporary_path.exists()


def test_failed_processing_removes_temp_and_preserves_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "source.EMB"
    output_path = tmp_path / "output.EMB"
    source_path.write_bytes(b"source")
    output_path.write_bytes(b"previous success")
    temporary_paths: list[Path] = []

    def fail(**kwargs: object) -> dict[str, str]:
        temporary_paths.append(
            Path(str(kwargs["file_path"]))
        )
        raise RuntimeError("failure")

    monkeypatch.setattr(
        batch,
        "process_emb_file",
        fail,
    )

    with pytest.raises(batch.TaskAttemptsError):
        batch.process_file_with_retries(
            source_path,
            output_path,
            "1",
            "2",
            None,
            retries=0,
            retry_delay=0,
        )

    assert output_path.read_bytes() == b"previous success"
    assert temporary_paths
    assert all(
        not temporary_path.exists()
        for temporary_path in temporary_paths
    )


def test_keyboard_interrupt_preserves_completed_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    csv_path = tmp_path / "coordinates.csv"
    input_dir.mkdir()
    (input_dir / "first.EMB").write_bytes(b"first")
    (input_dir / "second.EMB").write_bytes(b"second")
    csv_path.write_text(
        "file;x;y\n"
        "first.EMB;1;2\n"
        "second.EMB;3;4\n",
        encoding="utf-8",
    )
    calls = 0

    def process(**kwargs: object) -> dict[str, str]:
        nonlocal calls
        calls += 1

        if calls == 2:
            raise KeyboardInterrupt

        return successful_processing(**kwargs)

    monkeypatch.setattr(
        batch,
        "process_emb_file",
        process,
    )
    monkeypatch.setattr(
        batch,
        "cleanup_wilcom_best_effort",
        lambda: None,
    )

    with pytest.raises(KeyboardInterrupt):
        batch.run_batch(
            csv_path=csv_path,
            input_dir=input_dir,
            output_dir=output_dir,
            delay=0,
        )

    report_results = batch.read_batch_results(
        output_dir / "batch_results.csv"
    )
    assert [
        result["status"]
        for result in report_results
    ] == ["success", "error"]
    assert (
        report_results[1]["error"]
        == "Обработка прервана пользователем"
    )


def test_equivalent_coordinate_formats_have_same_task_key(
    tmp_path: Path,
) -> None:
    assert batch.make_task_key(
        "folder/design.EMB",
        "1,50",
        "2.00",
        tmp_path,
    ) == batch.make_task_key(
        "folder/design.EMB",
        "1.50",
        "2",
        tmp_path,
    )


def test_read_batch_results_accepts_empty_file(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "batch_results.csv"
    report_path.write_text(
        "",
        encoding="utf-8-sig",
    )

    assert batch.read_batch_results(report_path) == []


def test_read_batch_results_reports_corrupt_header(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "batch_results.csv"
    report_path.write_text(
        "row;status\n1;success\n",
        encoding="utf-8-sig",
    )

    with pytest.raises(
        ValueError,
        match="Повреждённый предыдущий отчёт.*"
        "обязательные столбцы",
    ):
        batch.read_batch_results(report_path)


def test_csv_without_output_file_keeps_default_output(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    csv_path = tmp_path / "coordinates.csv"
    source_path = input_dir / "Ghost" / "design.EMB"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"source")
    csv_path.write_text(
        "file;x;y\n"
        "Ghost/design.EMB;1;2\n",
        encoding="utf-8",
    )

    rows = batch.read_coordinate_csv(csv_path)
    tasks = batch.preflight_batch(
        rows,
        input_dir,
        output_dir,
    )

    assert rows[0].output_file == ""
    assert tasks[0].output_path == (
        output_dir.resolve()
        / "Ghost"
        / "design.EMB"
    )
    assert (
        tasks[0].relative_output_file
        == "Ghost/design.EMB"
    )


def test_csv_output_file_builds_requested_output_path(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    csv_path = tmp_path / "coordinates.csv"
    source_path = input_dir / "Ghost" / "design.EMB"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"source")
    csv_path.write_text(
        "file;x;y;output_file\n"
        "Ghost/design.EMB;11;0.12;"
        "variants/Ghost_x11.EMB\n",
        encoding="utf-8",
    )

    rows = batch.read_coordinate_csv(csv_path)
    tasks = batch.preflight_batch(
        rows,
        input_dir,
        output_dir,
    )

    assert (
        rows[0].output_file
        == "variants/Ghost_x11.EMB"
    )
    assert tasks[0].output_path == (
        output_dir.resolve()
        / "variants"
        / "Ghost_x11.EMB"
    )
    assert (
        tasks[0].relative_output_file
        == "variants/Ghost_x11.EMB"
    )


def test_one_source_can_have_two_output_variants(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    source_path = input_dir / "design.EMB"
    input_dir.mkdir()
    source_path.write_bytes(b"source")
    rows = [
        batch.CoordinateRow(
            1,
            "design.EMB",
            "1",
            "2",
            "design_one.EMB",
        ),
        batch.CoordinateRow(
            2,
            "design.EMB",
            "3",
            "4",
            "design_two.EMB",
        ),
    ]

    tasks = batch.preflight_batch(
        rows,
        input_dir,
        output_dir,
    )

    assert len(tasks) == 2
    assert tasks[0].source_path == tasks[1].source_path
    assert tasks[0].output_path != tasks[1].output_path
    assert tasks[0].task_key != tasks[1].task_key


def test_preflight_rejects_duplicate_output_paths(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    (input_dir / "first.EMB").write_bytes(b"first")
    (input_dir / "second.EMB").write_bytes(b"second")
    rows = [
        batch.CoordinateRow(
            2,
            "first.EMB",
            "1",
            "2",
            "same.EMB",
        ),
        batch.CoordinateRow(
            5,
            "second.EMB",
            "3",
            "4",
            "same.EMB",
        ),
    ]

    with pytest.raises(
        ValueError,
        match=r"Строки 2 и 5.*одинаковый выходной файл",
    ):
        batch.preflight_batch(
            rows,
            input_dir,
            output_dir,
        )


def test_resolve_output_path_rejects_absolute_path(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="относительным",
    ):
        batch.resolve_output_path(
            tmp_path,
            r"C:\outside.EMB",
        )


def test_resolve_output_path_rejects_parent_escape(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="за пределы output-dir",
    ):
        batch.resolve_output_path(
            tmp_path,
            "../outside.EMB",
        )


def test_resolve_output_path_requires_emb_extension(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="расширение .emb",
    ):
        batch.resolve_output_path(
            tmp_path,
            "variant.DST",
        )


def test_preflight_rejects_source_as_output(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "same"
    input_dir.mkdir()
    (input_dir / "design.EMB").write_bytes(b"source")

    with pytest.raises(
        ValueError,
        match="исходный и выходной EMB совпадают",
    ):
        batch.preflight_batch(
            [
                batch.CoordinateRow(
                    1,
                    "design.EMB",
                    "1",
                    "2",
                )
            ],
            input_dir,
            input_dir,
        )


def test_resolve_output_path_creates_parent_directories(
    tmp_path: Path,
) -> None:
    output_path = batch.resolve_output_path(
        tmp_path,
        "one/two/design.EMB",
    )

    assert output_path.parent.is_dir()
    assert output_path == (
        tmp_path.resolve()
        / "one"
        / "two"
        / "design.EMB"
    )


def test_resume_distinguishes_variants_of_same_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    csv_path = tmp_path / "coordinates.csv"
    source_path = input_dir / "design.EMB"
    first_output = output_dir / "design_one.EMB"
    second_output = output_dir / "design_two.EMB"
    input_dir.mkdir()
    output_dir.mkdir()
    source_path.write_bytes(b"source")
    first_output.write_bytes(b"ready")
    csv_path.write_text(
        "file;x;y;output_file\n"
        "design.EMB;1;2;design_one.EMB\n"
        "design.EMB;3;4;design_two.EMB\n",
        encoding="utf-8",
    )
    batch.write_batch_results_atomic(
        output_dir / "batch_results.csv",
        [
            make_report_result(
                1,
                source_path,
                first_output,
                "1",
                "2",
                "success",
            ),
            make_report_result(
                2,
                source_path,
                second_output,
                "3",
                "4",
                "error",
                "old error",
            ),
        ],
    )
    processed_paths: list[Path] = []

    def process(**kwargs: object) -> dict[str, str]:
        processed_paths.append(
            Path(str(kwargs["file_path"]))
        )
        return successful_processing(**kwargs)

    monkeypatch.setattr(
        batch,
        "process_emb_file",
        process,
    )
    monkeypatch.setattr(
        batch,
        "cleanup_wilcom_best_effort",
        lambda: None,
    )

    results = batch.run_batch(
        csv_path=csv_path,
        input_dir=input_dir,
        output_dir=output_dir,
        delay=0,
        resume=True,
    )

    assert len(processed_paths) == 1
    assert processed_paths[0].name.startswith(
        "design_two.__processing_"
    )
    assert len(results) == 2
    assert all(
        result["status"] == "success"
        for result in results
    )


def test_retry_errors_retries_only_failed_variant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    csv_path = tmp_path / "coordinates.csv"
    source_path = input_dir / "design.EMB"
    first_output = output_dir / "design_one.EMB"
    second_output = output_dir / "design_two.EMB"
    input_dir.mkdir()
    output_dir.mkdir()
    source_path.write_bytes(b"source")
    first_output.write_bytes(b"ready")
    csv_path.write_text(
        "file;x;y;output_file\n"
        "design.EMB;1;2;design_one.EMB\n"
        "design.EMB;3;4;design_two.EMB\n",
        encoding="utf-8",
    )
    batch.write_batch_results_atomic(
        output_dir / "batch_results.csv",
        [
            make_report_result(
                1,
                source_path,
                first_output,
                "1",
                "2",
                "success",
            ),
            make_report_result(
                2,
                source_path,
                second_output,
                "3",
                "4",
                "error",
                "failed variant",
            ),
        ],
    )
    processed_paths: list[Path] = []

    def process(**kwargs: object) -> dict[str, str]:
        processed_paths.append(
            Path(str(kwargs["file_path"]))
        )
        return successful_processing(**kwargs)

    monkeypatch.setattr(
        batch,
        "process_emb_file",
        process,
    )
    monkeypatch.setattr(
        batch,
        "cleanup_wilcom_best_effort",
        lambda: None,
    )

    results = batch.run_batch(
        csv_path=csv_path,
        input_dir=input_dir,
        output_dir=output_dir,
        delay=0,
        retry_errors=True,
    )

    assert len(processed_paths) == 1
    assert processed_paths[0].name.startswith(
        "design_two.__processing_"
    )
    assert len(results) == 2
    assert results[1]["status"] == "success"


def test_report_contains_relative_source_and_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    csv_path = tmp_path / "coordinates.csv"
    source_path = input_dir / "Ghost" / "design.EMB"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"source")
    csv_path.write_text(
        "file;x;y;output_file\n"
        "Ghost/design.EMB;1;2;"
        "variants/design_x1.EMB\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        batch,
        "process_emb_file",
        successful_processing,
    )
    monkeypatch.setattr(
        batch,
        "cleanup_wilcom_best_effort",
        lambda: None,
    )

    batch.run_batch(
        csv_path=csv_path,
        input_dir=input_dir,
        output_dir=output_dir,
        delay=0,
    )
    report_results = batch.read_batch_results(
        output_dir / "batch_results.csv"
    )

    assert (
        report_results[0]["relative_source_file"]
        == "Ghost/design.EMB"
    )
    assert (
        report_results[0]["relative_output_file"]
        == "variants/design_x1.EMB"
    )


def test_old_report_without_relative_columns_is_read(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    report_path = output_dir / "batch_results.csv"
    source_path = input_dir / "Ghost" / "design.EMB"
    output_path = output_dir / "Ghost" / "design.EMB"
    source_path.parent.mkdir(parents=True)
    output_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"source")
    old_columns = [
        column
        for column in batch.REPORT_COLUMNS
        if column not in {
            "relative_source_file",
            "relative_output_file",
        }
    ]
    old_result = make_report_result(
        1,
        source_path,
        output_path,
        "1",
        "2",
        "success",
    )

    with report_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=old_columns,
            delimiter=";",
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerow(old_result)

    results = batch.read_batch_results(
        report_path,
        input_dir=input_dir,
        output_dir=output_dir,
    )

    assert (
        results[0]["relative_source_file"]
        == "Ghost/design.EMB"
    )
    assert (
        results[0]["relative_output_file"]
        == "Ghost/design.EMB"
    )


def test_preflight_finishes_before_first_wilcom_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    csv_path = tmp_path / "coordinates.csv"
    input_dir.mkdir()
    (input_dir / "first.EMB").write_bytes(b"first")
    csv_path.write_text(
        "file;x;y\n"
        "first.EMB;1;2\n"
        "missing.EMB;3;4\n",
        encoding="utf-8",
    )
    process_calls = 0

    def process(**_: object) -> dict[str, str]:
        nonlocal process_calls
        process_calls += 1
        return {}

    monkeypatch.setattr(
        batch,
        "process_emb_file",
        process,
    )

    with pytest.raises(
        ValueError,
        match="Ошибка preflight в строке 2",
    ):
        batch.run_batch(
            csv_path=csv_path,
            input_dir=input_dir,
            output_dir=output_dir,
            delay=0,
        )

    assert process_calls == 0


def test_output_conflict_never_calls_wilcom(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    csv_path = tmp_path / "coordinates.csv"
    input_dir.mkdir()
    (input_dir / "first.EMB").write_bytes(b"first")
    (input_dir / "second.EMB").write_bytes(b"second")
    csv_path.write_text(
        "file;x;y;output_file\n"
        "first.EMB;1;2;same.EMB\n"
        "second.EMB;3;4;same.EMB\n",
        encoding="utf-8",
    )
    process_calls = 0

    def process(**_: object) -> dict[str, str]:
        nonlocal process_calls
        process_calls += 1
        return {}

    monkeypatch.setattr(
        batch,
        "process_emb_file",
        process,
    )

    with pytest.raises(
        ValueError,
        match="одинаковый выходной файл",
    ):
        batch.run_batch(
            csv_path=csv_path,
            input_dir=input_dir,
            output_dir=output_dir,
            delay=0,
        )

    assert process_calls == 0
    assert not list(
        output_dir.rglob("*.__processing_*.EMB")
    )


def test_processing_files_for_variants_do_not_conflict(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "input" / "design.EMB"
    output_dir = tmp_path / "output"
    source_path.parent.mkdir()
    source_path.write_bytes(b"source")
    first_output = output_dir / "design_one.EMB"
    second_output = output_dir / "design_two.EMB"

    first_temporary = batch.create_processing_copy(
        source_path,
        first_output,
    )
    second_temporary = batch.create_processing_copy(
        source_path,
        second_output,
    )

    try:
        assert first_temporary != second_temporary
        assert first_temporary.name.startswith(
            "design_one.__processing_"
        )
        assert second_temporary.name.startswith(
            "design_two.__processing_"
        )
        assert first_temporary.is_file()
        assert second_temporary.is_file()
    finally:
        batch.remove_file_best_effort(first_temporary)
        batch.remove_file_best_effort(second_temporary)
