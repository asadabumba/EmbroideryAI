from __future__ import annotations

import csv
import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

import pytest


TESTS_DIR = Path(__file__).resolve().parents[1]
GENERATOR_PATH = (
    TESTS_DIR
    / "generate_coordinate_variants.py"
)
GENERATOR_SPEC = importlib.util.spec_from_file_location(
    "generate_coordinate_variants",
    GENERATOR_PATH,
)
assert (
    GENERATOR_SPEC is not None
    and GENERATOR_SPEC.loader is not None
)
generator = importlib.util.module_from_spec(
    GENERATOR_SPEC
)
sys.modules[GENERATOR_SPEC.name] = generator
GENERATOR_SPEC.loader.exec_module(generator)

BATCH_PATH = TESTS_DIR / "automate_wilcom_batch.py"
BATCH_SPEC = importlib.util.spec_from_file_location(
    "automate_wilcom_batch_for_generator",
    BATCH_PATH,
)
assert (
    BATCH_SPEC is not None
    and BATCH_SPEC.loader is not None
)
batch = importlib.util.module_from_spec(BATCH_SPEC)
sys.modules[BATCH_SPEC.name] = batch
BATCH_SPEC.loader.exec_module(batch)


def touch_emb(
    file_path: Path,
) -> Path:
    file_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    file_path.write_bytes(b"EMB")
    return file_path


def test_discover_emb_files_recursively(
    tmp_path: Path,
) -> None:
    first = touch_emb(
        tmp_path / "root.EMB"
    )
    second = touch_emb(
        tmp_path / "nested" / "design.emb"
    )

    assert generator.discover_emb_files(
        tmp_path
    ) == [second, first]


def test_discover_emb_files_is_case_insensitive(
    tmp_path: Path,
) -> None:
    expected = [
        touch_emb(tmp_path / "a.EmB"),
        touch_emb(tmp_path / "b.eMb"),
        touch_emb(tmp_path / "c.EMB"),
    ]
    (tmp_path / "ignored.DST").write_bytes(b"DST")

    assert generator.discover_emb_files(
        tmp_path
    ) == expected


def test_discover_emb_files_excludes_output_subdir(
    tmp_path: Path,
) -> None:
    source = touch_emb(
        tmp_path / "Ghost" / "design.EMB"
    )
    touch_emb(
        tmp_path
        / "Ghost"
        / "variants"
        / "generated.EMB"
    )

    assert generator.discover_emb_files(
        tmp_path,
        "variants",
    ) == [source]


def test_discover_emb_files_excludes_processing_files(
    tmp_path: Path,
) -> None:
    source = touch_emb(
        tmp_path / "design.EMB"
    )
    touch_emb(
        tmp_path
        / "design.__processing_12345.EMB"
    )

    assert generator.discover_emb_files(
        tmp_path
    ) == [source]


def test_discover_emb_files_sorting_is_deterministic(
    tmp_path: Path,
) -> None:
    touch_emb(tmp_path / "z.EMB")
    touch_emb(tmp_path / "a" / "A.EMB")
    touch_emb(tmp_path / "B" / "b.EMB")

    first_run = generator.discover_emb_files(
        tmp_path
    )
    second_run = generator.discover_emb_files(
        tmp_path
    )

    assert first_run == second_run
    assert [
        path.relative_to(tmp_path).as_posix()
        for path in first_run
    ] == [
        "a/A.EMB",
        "B/b.EMB",
        "z.EMB",
    ]


def test_grid_is_cartesian_product() -> None:
    coordinates = generator.generate_grid_coordinates(
        "-10",
        "10",
        "-5",
        "5",
        "10",
    )

    assert coordinates == [
        (Decimal("-10"), Decimal("-5")),
        (Decimal("-10"), Decimal("5")),
        (Decimal("0"), Decimal("-5")),
        (Decimal("0"), Decimal("5")),
        (Decimal("10"), Decimal("-5")),
        (Decimal("10"), Decimal("5")),
    ]


def test_decimal_range_includes_aligned_boundaries() -> None:
    assert generator.decimal_range(
        "-1",
        "1",
        "0.5",
    ) == [
        Decimal("-1"),
        Decimal("-0.5"),
        Decimal("0"),
        Decimal("0.5"),
        Decimal("1"),
    ]


def test_decimal_range_has_no_float_artifacts() -> None:
    values = generator.decimal_range(
        "0",
        "0.3",
        "0.1",
    )

    assert values == [
        Decimal("0"),
        Decimal("0.1"),
        Decimal("0.2"),
        Decimal("0.3"),
    ]
    assert [
        generator.format_coordinate(value)
        for value in values
    ] == [
        "0.00",
        "0.10",
        "0.20",
        "0.30",
    ]


@pytest.mark.parametrize(
    "step",
    ["0", "-0.01"],
)
def test_decimal_range_rejects_nonpositive_step(
    step: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="step должен быть больше нуля",
    ):
        generator.decimal_range(
            "0",
            "1",
            step,
        )


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (
            ("2", "1", "0", "1"),
            "x-min",
        ),
        (
            ("0", "1", "2", "1"),
            "y-min",
        ),
    ],
)
def test_grid_rejects_invalid_min_max(
    arguments: tuple[str, str, str, str],
    message: str,
) -> None:
    with pytest.raises(
        ValueError,
        match=message,
    ):
        generator.generate_grid_coordinates(
            *arguments,
            step="1",
        )


def test_random_is_deterministic_for_same_seed() -> None:
    first = generator.generate_random_coordinates(
        "-10",
        "10",
        "-10",
        "10",
        count=20,
        seed=123,
    )
    second = generator.generate_random_coordinates(
        "-10",
        "10",
        "-10",
        "10",
        count=20,
        seed=123,
    )

    assert first == second


def test_random_differs_for_different_seeds() -> None:
    first = generator.generate_random_coordinates(
        "-10",
        "10",
        "-10",
        "10",
        count=20,
        seed=1,
    )
    second = generator.generate_random_coordinates(
        "-10",
        "10",
        "-10",
        "10",
        count=20,
        seed=2,
    )

    assert first != second


def test_random_has_no_duplicate_coordinates() -> None:
    coordinates = generator.generate_random_coordinates(
        "-1",
        "1",
        "-1",
        "1",
        count=100,
        seed=42,
    )

    assert len(coordinates) == len(
        set(coordinates)
    )


def test_random_rejects_impossible_unique_count() -> None:
    with pytest.raises(
        ValueError,
        match="Невозможно получить 2 уникальных",
    ):
        generator.generate_random_coordinates(
            "0",
            "0",
            "0",
            "0",
            count=2,
            seed=1,
        )


def test_include_center_adds_center() -> None:
    coordinates = generator.generate_grid_coordinates(
        "1",
        "2",
        "1",
        "2",
        "1",
        include_center=True,
    )

    assert (
        Decimal("0"),
        Decimal("0"),
    ) in coordinates


def test_include_center_does_not_duplicate_center() -> None:
    coordinates = generator.generate_grid_coordinates(
        "-1",
        "1",
        "-1",
        "1",
        "1",
        include_center=True,
    )

    assert coordinates.count(
        (
            Decimal("0"),
            Decimal("0"),
        )
    ) == 1


def test_negative_zero_is_formatted_as_positive_zero() -> None:
    assert generator.format_coordinate(
        Decimal("-0.004")
    ) == "0.00"
    assert generator.normalize_zero(
        Decimal("-0")
    ) == Decimal("0")


def test_encode_positive_coordinate() -> None:
    assert (
        generator.encode_coordinate_for_filename(
            "2.91"
        )
        == "2_91"
    )


def test_encode_negative_coordinate() -> None:
    assert (
        generator.encode_coordinate_for_filename(
            "-6.41"
        )
        == "m6_41"
    )


def test_generated_output_files_are_unique(
    tmp_path: Path,
) -> None:
    source = touch_emb(
        tmp_path / "input" / "design.EMB"
    )
    rows = generator.generate_rows(
        emb_files=[source],
        input_dir=tmp_path / "input",
        mode="grid",
        x_min="0",
        x_max="1",
        y_min="0",
        y_max="1",
        step="1",
    )

    assert len(rows) == 4
    assert len(
        {
            row.output_file
            for row in rows
        }
    ) == 4


def test_output_file_preserves_source_subdirectories(
    tmp_path: Path,
) -> None:
    source = touch_emb(
        tmp_path
        / "input"
        / "Ghost"
        / "design.EMB"
    )
    rows = generator.generate_rows(
        emb_files=[source],
        input_dir=tmp_path / "input",
        mode="grid",
        x_min="0",
        x_max="0",
        y_min="0",
        y_max="0",
        step="1",
        output_subdir="variants",
    )

    assert rows == [
        generator.VariantRow(
            file="Ghost/design.EMB",
            x="0.00",
            y="0.00",
            output_file=(
                "Ghost/variants/"
                "design__x_0_00__y_0_00.EMB"
            ),
        )
    ]


def test_existing_csv_without_overwrite_is_unchanged(
    tmp_path: Path,
) -> None:
    output_csv = tmp_path / "coordinates.csv"
    output_csv.write_bytes(b"original")

    with pytest.raises(
        FileExistsError,
        match="--overwrite",
    ):
        generator.write_coordinate_csv_atomic(
            output_csv,
            [],
            overwrite=False,
        )

    assert output_csv.read_bytes() == b"original"


def test_overwrite_uses_atomic_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_csv = tmp_path / "coordinates.csv"
    output_csv.write_bytes(b"old")
    replace_calls: list[tuple[Path, Path]] = []
    real_replace = generator.os.replace

    def replace(
        source: Path,
        destination: Path,
    ) -> None:
        replace_calls.append(
            (
                Path(source),
                Path(destination),
            )
        )
        real_replace(
            source,
            destination,
        )

    monkeypatch.setattr(
        generator.os,
        "replace",
        replace,
    )
    generator.write_coordinate_csv_atomic(
        output_csv,
        [
            generator.VariantRow(
                "design.EMB",
                "0.00",
                "0.00",
                (
                    "positioned_variants/"
                    "design__x_0_00__y_0_00.EMB"
                ),
            )
        ],
        overwrite=True,
    )

    assert len(replace_calls) == 1
    assert replace_calls[0][0] != output_csv
    assert replace_calls[0][1] == output_csv.resolve()
    assert b"design.EMB" in output_csv.read_bytes()


def test_csv_has_bom_and_semicolon_delimiter(
    tmp_path: Path,
) -> None:
    output_csv = tmp_path / "coordinates.csv"
    rows = [
        generator.VariantRow(
            "design.EMB",
            "-1.00",
            "2.00",
            (
                "positioned_variants/"
                "design__x_m1_00__y_2_00.EMB"
            ),
        )
    ]

    generator.write_coordinate_csv_atomic(
        output_csv,
        rows,
    )

    assert output_csv.read_bytes().startswith(
        b"\xef\xbb\xbf"
    )

    with output_csv.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        reader = csv.DictReader(
            handle,
            delimiter=";",
        )
        written_rows = list(reader)

    assert reader.fieldnames == generator.CSV_COLUMNS
    assert written_rows == [
        {
            "file": "design.EMB",
            "x": "-1.00",
            "y": "2.00",
            "output_file": (
                "positioned_variants/"
                "design__x_m1_00__y_2_00.EMB"
            ),
        }
    ]


def test_generated_csv_is_compatible_with_batch_reader(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    source = touch_emb(
        input_dir / "Ghost" / "design.EMB"
    )
    output_csv = tmp_path / "coordinates.csv"
    generated_rows = generator.generate_rows(
        emb_files=[source],
        input_dir=input_dir,
        mode="grid",
        x_min="-1",
        x_max="1",
        y_min="0",
        y_max="0",
        step="1",
    )
    generator.write_coordinate_csv_atomic(
        output_csv,
        generated_rows,
    )

    batch_rows = batch.read_coordinate_csv(
        output_csv
    )

    assert len(batch_rows) == 3
    assert batch_rows[0].file == "Ghost/design.EMB"
    assert batch_rows[0].x == "-1.00"
    assert batch_rows[0].y == "0.00"
    assert batch_rows[0].output_file.endswith(
        "design__x_m1_00__y_0_00.EMB"
    )
