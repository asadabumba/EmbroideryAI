from __future__ import annotations

import argparse
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .schema import DesignRecord
from .serialization import read_jsonl, write_json


def _reconstruction_error(record: DesignRecord) -> float | None:
    absolute = record.geometry.get("absolute_stitch_coordinates", [])
    normalized = record.geometry.get("normalized_stitch_coordinates", [])
    center = record.geometry.get("center")
    width = record.geometry.get("width")
    height = record.geometry.get("height")
    if not absolute or len(absolute) != len(normalized) or not center:
        return None
    scale = max(float(width), float(height))
    if scale == 0:
        scale = 1.0
    errors = []
    for actual, unit_point in zip(absolute, normalized):
        reconstructed = [
            float(unit_point[0]) * scale + float(center[0]),
            float(unit_point[1]) * scale + float(center[1]),
        ]
        errors.append(math.hypot(reconstructed[0] - actual[0], reconstructed[1] - actual[1]))
    return max(errors, default=0.0)


def _trajectory_distance(first: DesignRecord, second: DesignRecord) -> float | None:
    a = first.geometry.get("normalized_stitch_coordinates", [])
    b = second.geometry.get("normalized_stitch_coordinates", [])
    if not a or len(a) != len(b):
        return None
    return sum(
        math.hypot(float(left[0]) - float(right[0]), float(left[1]) - float(right[1]))
        for left, right in zip(a, b)
    ) / len(a)


def run_baselines(records: Iterable[DesignRecord]) -> dict[str, Any]:
    values = list(records)
    reconstruction = [
        error for record in values if (error := _reconstruction_error(record)) is not None
    ]
    groups: dict[str, list[DesignRecord]] = defaultdict(list)
    for record in values:
        groups[record.source_design_id].append(record)
    comparisons = []
    for source_id, group in sorted(groups.items()):
        if len(group) < 2:
            continue
        reference = sorted(group, key=lambda record: record.source_path)[0]
        for candidate in sorted(group, key=lambda record: record.source_path)[1:]:
            distance = _trajectory_distance(reference, candidate)
            if distance is not None:
                comparisons.append(
                    {
                        "source_design_id": source_id,
                        "reference": reference.source_path,
                        "candidate": candidate.source_path,
                        "mean_normalized_point_distance": distance,
                    }
                )
    feature_rows = [
        {
            "design_id": record.design_id,
            "source_design_id": record.source_design_id,
            "stitch_count": record.stitch.get("stitch_count"),
            "jump_count": record.stitch.get("jump_count"),
            "color_change_count": record.stitch.get("color_change_count"),
            "total_path_length": record.geometry.get("total_path_length"),
            "mean_stitch_length": record.statistics.get("stitch_length", {}).get("mean"),
        }
        for record in values
    ]
    return {
        "record_count": len(values),
        "trajectory_records": len(reconstruction),
        "normalized_reconstruction": {
            "max_error_mm": max(reconstruction) if reconstruction else None,
            "mean_error_mm": (
                sum(reconstruction) / len(reconstruction) if reconstruction else None
            ),
        },
        "translation_invariance": {
            "comparable_variant_pairs": len(comparisons),
            "comparisons": comparisons,
        },
        "sequence_statistic_features": feature_rows,
        "note": (
            "These are deterministic data-pipeline checks, not trained-model results. "
            "No corpus-level conclusion is valid until real records are supplied."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run lightweight Stage 2 baselines")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    records = [DesignRecord.from_dict(value) for value in read_jsonl(args.manifest)]
    write_json(args.output, run_baselines(records))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
