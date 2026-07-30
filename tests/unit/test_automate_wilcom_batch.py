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
            "output_file": "output/Ghost/ghost_01.EMB",
            "requested_x": "14.00",
            "requested_y": "0.74",
            "old_x": "0.00",
            "old_y": "0.78",
            "actual_x": "14.00",
            "actual_y": "0.74",
            "status": "success",
            "error": "",
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
