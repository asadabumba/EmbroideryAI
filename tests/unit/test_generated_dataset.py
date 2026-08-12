from pathlib import Path

from src.generated_dataset import (
    load_successful_variants,
    parse_successful_variant,
)

def test_parse_successful_variant() -> None:
    row = {
        "relative_source_file": "Ghost/design.EMB",
        "relative_output_file": (
            "Ghost/positioned_variants/"
            "design__x_m10_00__y_5_00.EMB"
        ),
        "requested_x": "-10.00",
        "requested_y": "5.00",
        "actual_x": "-10.00",
        "actual_y": "5.00",
        "status": "success",
        "attempts": "2",
    }

    variant = parse_successful_variant(row)

    assert variant is not None
    assert variant.source_file == "Ghost/design.EMB"
    assert variant.requested_x == "-10.00"
    assert variant.requested_y == "5.00"
    assert variant.actual_x == "-10.00"
    assert variant.actual_y == "5.00"
    assert variant.attempts == 2


def test_parse_successful_variant_skips_error() -> None:
    row = {
        "relative_source_file": "Ghost/design.EMB",
        "relative_output_file": "Ghost/failed.EMB",
        "requested_x": "-10.00",
        "requested_y": "5.00",
        "actual_x": "",
        "actual_y": "",
        "status": "error",
        "attempts": "3",
    }

    assert parse_successful_variant(row) is None


def test_load_successful_variants(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "batch_results.csv"

    report_path.write_text(
        "relative_source_file;"
        "relative_output_file;"
        "requested_x;"
        "requested_y;"
        "actual_x;"
        "actual_y;"
        "status;"
        "attempts\n"
        "Ghost/design.EMB;"
        "Ghost/positioned_variants/design_1.EMB;"
        "-10.00;"
        "5.00;"
        "-10.00;"
        "5.00;"
        "success;"
        "1\n"
        "Ghost/design.EMB;"
        "Ghost/positioned_variants/design_2.EMB;"
        "10.00;"
        "5.00;"
        ";;"
        "error;"
        "3\n",
        encoding="utf-8-sig",
    )

    variants = load_successful_variants(
        report_path
    )

    assert len(variants) == 1
    assert variants[0].output_file.endswith(
        "design_1.EMB"
    )
    assert variants[0].attempts == 1