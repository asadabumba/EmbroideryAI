from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "verify_positioned_dataset.py"
)
SPEC = importlib.util.spec_from_file_location(
    "verify_positioned_dataset_tests",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
verification = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = verification
SPEC.loader.exec_module(verification)


def make_complete_dataset(
    tmp_path: Path,
) -> tuple[Path, Path, Path]:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    csv_path = tmp_path / "coordinates.csv"
    input_dir.mkdir()
    output_dir.mkdir()
    source = input_dir / "design.EMB"
    source.write_bytes(b"source")
    csv_path.write_text(
        "file;x;y;output_file\n"
        "design.EMB;1;2;variants/one.EMB\n"
        "design.EMB;3;4;variants/two.EMB\n",
        encoding="utf-8",
    )
    rows = verification.read_coordinate_csv(csv_path)
    tasks = verification.preflight_batch(
        rows,
        input_dir,
        output_dir,
    )
    results = []

    for attempt, task in enumerate(tasks, start=1):
        task.output_path.write_bytes(b"ready")
        results.append(
            {
                "row": str(task.coordinate_row.row),
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
                "old_x": "0",
                "old_y": "0",
                "actual_x": task.requested_x,
                "actual_y": task.requested_y,
                "status": "success",
                "error": "",
                "attempts": str(attempt),
            }
        )

    from automate_wilcom_batch import (
        write_batch_results_atomic,
    )

    write_batch_results_atomic(
        output_dir / "batch_results.csv",
        results,
    )
    return input_dir, output_dir, csv_path


def test_verifies_complete_unique_nonempty_dataset(
    tmp_path: Path,
) -> None:
    input_dir, output_dir, csv_path = (
        make_complete_dataset(tmp_path)
    )

    result = verification.verify_positioned_dataset(
        csv_path=csv_path,
        input_dir=input_dir,
        output_dir=output_dir,
        expected_sources=1,
        expected_coordinates=2,
        expected_tasks=2,
    )

    assert result.source_count == 1
    assert result.coordinate_count == 2
    assert result.expected_outputs == 2
    assert result.actual_outputs == 2
    assert result.report_rows == 2
    assert result.retries == 1


def test_rejects_zero_byte_output(
    tmp_path: Path,
) -> None:
    input_dir, output_dir, csv_path = (
        make_complete_dataset(tmp_path)
    )
    (output_dir / "variants" / "one.EMB").write_bytes(
        b""
    )

    with pytest.raises(
        ValueError,
        match="Expected output пуст",
    ):
        verification.verify_positioned_dataset(
            csv_path,
            input_dir,
            output_dir,
        )


def test_rejects_unresolved_report_error(
    tmp_path: Path,
) -> None:
    input_dir, output_dir, csv_path = (
        make_complete_dataset(tmp_path)
    )
    report_path = output_dir / "batch_results.csv"
    text = report_path.read_text(encoding="utf-8-sig")
    report_path.write_text(
        text.replace(";success;;1", ";error;failed;1", 1),
        encoding="utf-8-sig",
    )

    with pytest.raises(
        ValueError,
        match="Неразрешённая ошибка",
    ):
        verification.verify_positioned_dataset(
            csv_path,
            input_dir,
            output_dir,
        )


def test_rejects_extra_or_unfinished_emb(
    tmp_path: Path,
) -> None:
    input_dir, output_dir, csv_path = (
        make_complete_dataset(tmp_path)
    )
    extra = (
        output_dir
        / ".working"
        / "stale.__publishing_deadbeef.EMB"
    )
    extra.parent.mkdir()
    extra.write_bytes(b"stale")

    with pytest.raises(
        ValueError,
        match="лишние EMB outputs",
    ):
        verification.verify_positioned_dataset(
            csv_path,
            input_dir,
            output_dir,
        )

