from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GeneratedVariant:
    source_file: str
    output_file: str
    requested_x: str
    requested_y: str
    actual_x: str
    actual_y: str
    attempts: int

def parse_successful_variant(
    row: dict[str, str],
) -> GeneratedVariant | None:
    if row.get("status", "").strip() != "success":
        return None

    return GeneratedVariant(
        source_file=row.get(
            "relative_source_file",
            "",
        ).strip(),
        output_file=row.get(
            "relative_output_file",
            "",
        ).strip(),
        requested_x=row.get(
            "requested_x",
            "",
        ).strip(),
        requested_y=row.get(
            "requested_y",
            "",
        ).strip(),
        actual_x=row.get(
            "actual_x",
            "",
        ).strip(),
        actual_y=row.get(
            "actual_y",
            "",
        ).strip(),
        attempts=int(
            row.get("attempts", "1").strip() or "1"
        ),
    )

def load_successful_variants(
    report_path: Path,
) -> list[GeneratedVariant]:
    with report_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        reader = csv.DictReader(
            handle,
            delimiter=";",
        )

        variants = []

        for row in reader:
            variant = parse_successful_variant(row)

            if variant is not None:
                variants.append(variant)

        return variants