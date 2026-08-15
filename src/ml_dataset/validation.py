from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .canonicalize import (
    deterministic_design_id,
    deterministic_source_design_id,
    normalize_path_key,
)
from .schema import DesignRecord
from .serialization import write_json
from .splitting import SPLIT_NAMES, leakage_overlaps


KNOWN_COMMAND_TYPES = {
    "stitch",
    "jump",
    "color_change",
    "end",
    "sequin_mode",
    "sequin_eject",
}


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    code: str
    message: str
    design_id: str | None = None
    source_path: str | None = None


@dataclass
class ValidationReport:
    record_count: int
    issue_counts: dict[str, int]
    issues: list[ValidationIssue]

    @property
    def is_valid(self) -> bool:
        return self.issue_counts.get("error", 0) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_count": self.record_count,
            "is_valid": self.is_valid,
            "issue_counts": self.issue_counts,
            "issues": [asdict(issue) for issue in self.issues],
        }


def _issue(record: DesignRecord, severity: str, code: str, message: str) -> ValidationIssue:
    design_id = record.identity.get("design_id")
    source_path = record.identity.get("source_path")
    return ValidationIssue(
        severity,
        code,
        message,
        design_id if isinstance(design_id, str) else None,
        source_path if isinstance(source_path, str) else None,
    )


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _first_non_finite(value: Any, path: str = "record") -> str | None:
    if isinstance(value, float) and not math.isfinite(value):
        return path
    if isinstance(value, dict):
        for key, child in value.items():
            found = _first_non_finite(child, f"{path}.{key}")
            if found is not None:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = _first_non_finite(child, f"{path}[{index}]")
            if found is not None:
                return found
    return None


def _valid_point(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(_finite_number(component) for component in value)
    )


def _close(first: Any, second: Any) -> bool:
    return _finite_number(first) and _finite_number(second) and math.isclose(
        float(first), float(second), abs_tol=1e-7
    )


def validate_record(
    record: DesignRecord,
    input_root: Path | None = None,
    output_root: Path | None = None,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    non_finite_path = _first_non_finite(record.to_dict())
    if non_finite_path is not None:
        issues.append(
            _issue(record, "error", "non_finite_value", f"NaN or infinity found at {non_finite_path}")
        )
    identity = record.identity
    for name in ("design_id", "source_design_id", "source_path", "format", "content_sha256"):
        if not isinstance(identity.get(name), str) or not identity[name]:
            issues.append(_issue(record, "error", "corrupt_identity", f"identity.{name} is missing"))
    content_hash = identity.get("content_sha256")
    if isinstance(content_hash, str) and not re.fullmatch(r"[0-9a-f]{64}", content_hash):
        issues.append(
            _issue(record, "error", "invalid_content_hash", "content SHA-256 is not 64 lowercase hex characters")
        )
    source_format = identity.get("format")
    design_id = identity.get("design_id")
    if (
        isinstance(source_format, str)
        and isinstance(content_hash, str)
        and re.fullmatch(r"[0-9a-f]{64}", content_hash)
        and design_id != deterministic_design_id(source_format, content_hash)
    ):
        issues.append(_issue(record, "error", "inconsistent_design_id", "design ID does not match format and content hash"))
    source_key = identity.get("source_design_key")
    source_id = identity.get("source_design_id")
    if isinstance(source_key, str) and source_key:
        if source_id != deterministic_source_design_id(source_key):
            issues.append(_issue(record, "error", "inconsistent_source_design_id", "source design ID does not match its grouping key"))
    else:
        issues.append(_issue(record, "error", "corrupt_identity", "identity.source_design_key is missing"))

    source_path_value = identity.get("source_path")
    if isinstance(source_path_value, str) and source_path_value:
        source_path = Path(source_path_value)
        if source_path.is_absolute() or source_path.anchor or ".." in source_path.parts:
            issues.append(_issue(record, "error", "unsafe_source_path", "source path must be relative and cannot traverse parents"))
        elif input_root is not None and not (input_root / source_path).is_file():
            issues.append(_issue(record, "error", "missing_source_file", "source file does not exist"))

    coordinates = record.geometry.get("absolute_stitch_coordinates")
    if not isinstance(coordinates, list):
        issues.append(_issue(record, "error", "corrupt_geometry", "coordinate array is not a list"))
        coordinates = []
    if not coordinates:
        issues.append(
            _issue(
                record,
                "warning",
                "empty_stitch_path",
                "no stitch trajectory is available for this record",
            )
        )
    for index, point in enumerate(coordinates):
        if not _valid_point(point):
            issues.append(
                _issue(record, "error", "invalid_coordinate", f"coordinate {index} is invalid")
            )
            break

    normalized = record.geometry.get("normalized_stitch_coordinates")
    if not isinstance(normalized, list) or len(normalized) != len(coordinates):
        issues.append(
            _issue(
                record,
                "error",
                "coordinate_array_mismatch",
                "absolute and normalized coordinate arrays have different lengths",
            )
        )
        normalized = []
    for index, point in enumerate(normalized):
        if not _valid_point(point) or any(abs(float(value)) > 0.5000001 for value in point):
            issues.append(
                _issue(record, "error", "invalid_normalized_coordinate", f"normalized coordinate {index} is invalid")
            )
            break

    stitch_deltas = record.geometry.get("stitch_deltas")
    if not isinstance(stitch_deltas, list) or len(stitch_deltas) != len(coordinates):
        issues.append(
            _issue(
                record,
                "error",
                "stitch_delta_mismatch",
                "stitch delta and coordinate arrays have different lengths",
            )
        )
        stitch_deltas = []
    for index, delta in enumerate(stitch_deltas):
        if not _valid_point(delta):
            issues.append(_issue(record, "error", "invalid_stitch_delta", f"stitch delta {index} is invalid"))
            break

    for field_name in ("width", "height", "total_path_length"):
        value = record.geometry.get(field_name)
        if value is not None and (not _finite_number(value) or float(value) < 0):
            issues.append(
                _issue(record, "error", "impossible_geometry", f"geometry.{field_name} is invalid")
            )

    bounding_box = record.geometry.get("bounding_box")
    center = record.geometry.get("center")
    if coordinates and all(_valid_point(point) for point in coordinates):
        xs = [float(point[0]) for point in coordinates]
        ys = [float(point[1]) for point in coordinates]
        expected_bounds = {
            "min_x": min(xs),
            "min_y": min(ys),
            "max_x": max(xs),
            "max_y": max(ys),
        }
        if not isinstance(bounding_box, dict) or not all(
            _close(bounding_box.get(name), expected) for name, expected in expected_bounds.items()
        ):
            issues.append(_issue(record, "error", "inconsistent_bounding_box", "bounding box does not match stitch coordinates"))
        expected_width = expected_bounds["max_x"] - expected_bounds["min_x"]
        expected_height = expected_bounds["max_y"] - expected_bounds["min_y"]
        if not _close(record.geometry.get("width"), expected_width) or not _close(
            record.geometry.get("height"), expected_height
        ):
            issues.append(_issue(record, "error", "inconsistent_dimensions", "width or height does not match the bounding box"))
        expected_center = [
            (expected_bounds["min_x"] + expected_bounds["max_x"]) / 2.0,
            (expected_bounds["min_y"] + expected_bounds["max_y"]) / 2.0,
        ]
        if not _valid_point(center) or not all(
            _close(actual, expected) for actual, expected in zip(center, expected_center)
        ):
            issues.append(_issue(record, "error", "inconsistent_center", "center does not match the bounding box"))
    elif bounding_box is not None or center is not None:
        issues.append(_issue(record, "error", "impossible_geometry", "empty stitch paths cannot have a bounding box or center"))

    observed = record.source_metadata.get("observed")
    if not isinstance(observed, dict):
        issues.append(
            _issue(record, "error", "corrupt_metadata", "source_metadata.observed is not an object")
        )
    for field_name in ("stitch_count", "jump_count", "trim_count", "color_change_count"):
        value = record.stitch.get(field_name)
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value < 0
        ):
            issues.append(
                _issue(record, "error", "invalid_stitch_count", f"stitch.{field_name} is invalid")
            )

    preview_path_value = record.rendering.get("preview_path")
    if preview_path_value is not None:
        if not isinstance(preview_path_value, str) or not preview_path_value:
            issues.append(_issue(record, "error", "corrupt_rendering", "rendering.preview_path is invalid"))
        else:
            preview_path = Path(preview_path_value)
            if preview_path.is_absolute() or preview_path.anchor or ".." in preview_path.parts:
                issues.append(_issue(record, "error", "unsafe_preview_path", "preview path must be relative and cannot traverse parents"))
            elif output_root is not None and not (output_root / preview_path).is_file():
                issues.append(_issue(record, "error", "missing_preview_file", "declared preview file does not exist"))

    events = record.stitch.get("command_sequence")
    if not isinstance(events, list):
        issues.append(_issue(record, "error", "corrupt_command_sequence", "command sequence is not a list"))
        events = []
    current_x = 0.0
    current_y = 0.0
    actual_frequencies: Counter[str] = Counter()
    stitch_points: list[list[float]] = []
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            issues.append(_issue(record, "error", "malformed_command", f"command {index} is not an object"))
            continue
        event_type = event.get("type")
        if event_type not in KNOWN_COMMAND_TYPES:
            issues.append(_issue(record, "error", "unknown_command", f"command {index} has type {event_type!r}"))
        else:
            actual_frequencies[event_type] += 1
        if event.get("index") != index:
            issues.append(_issue(record, "error", "invalid_command_index", f"command {index} has a non-sequential index"))
        values = [event.get(name) for name in ("dx", "dy", "x", "y")]
        if not all(_finite_number(value) for value in values):
            issues.append(_issue(record, "error", "invalid_command_coordinate", f"command {index} has non-finite coordinates"))
            continue
        current_x += float(event["dx"])
        current_y += float(event["dy"])
        if not math.isclose(current_x, float(event["x"]), abs_tol=1e-7) or not math.isclose(
            current_y, float(event["y"]), abs_tol=1e-7
        ):
            issues.append(_issue(record, "error", "inconsistent_command_delta", f"command {index} is not cumulative"))
        if event_type == "stitch":
            stitch_points.append([float(event["x"]), float(event["y"])])
    end_indexes = [
        index for index, event in enumerate(events) if isinstance(event, dict) and event.get("type") == "end"
    ]
    if events and not end_indexes:
        issues.append(_issue(record, "error", "missing_end_command", "non-empty command sequence has no end command"))
    elif end_indexes and end_indexes != [len(events) - 1]:
        issues.append(_issue(record, "error", "malformed_end_command", "command sequence must contain one terminal end command"))

    if stitch_points != coordinates:
        issues.append(_issue(record, "error", "coordinate_sequence_mismatch", "stitch coordinates do not match the command sequence"))
    for field_name, command_type in (
        ("stitch_count", "stitch"),
        ("jump_count", "jump"),
        ("color_change_count", "color_change"),
    ):
        value = record.stitch.get(field_name)
        if events and value != actual_frequencies.get(command_type, 0):
            issues.append(_issue(record, "error", "inconsistent_stitch_count", f"stitch.{field_name} does not match the command sequence"))
    command_frequencies = record.statistics.get("command_frequencies")
    if not isinstance(command_frequencies, dict) or command_frequencies != dict(sorted(actual_frequencies.items())):
        issues.append(_issue(record, "error", "inconsistent_command_frequencies", "statistics.command_frequencies does not match the sequence"))

    for diagnostic in record.parse_diagnostics:
        if diagnostic.get("severity") == "error":
            issues.append(
                _issue(
                    record,
                    "error",
                    str(diagnostic.get("code", "parse_diagnostic")),
                    str(diagnostic.get("message", "parser reported an error")),
                )
            )

    relation = record.augmentation.get("relation")
    if relation != "original":
        if not record.augmentation.get("original_source_path"):
            issues.append(_issue(record, "error", "missing_original_lineage", "augmented record has no original source path"))
        if relation == "translated_variant" and (
            not _finite_number(record.augmentation.get("x_translation"))
            or not _finite_number(record.augmentation.get("y_translation"))
        ):
            issues.append(_issue(record, "error", "invalid_translation_lineage", "translated variant has invalid x/y translation"))
        if relation == "translated_variant" and isinstance(source_key, str):
            original_path = record.augmentation.get("original_source_path")
            if isinstance(original_path, str) and normalize_path_key(original_path) != normalize_path_key(source_key):
                issues.append(_issue(record, "error", "inconsistent_translation_lineage", "translated variant grouping key does not match its original source path"))
    return issues


def validate_dataset(
    records: Iterable[DesignRecord],
    *,
    input_root: Path | None = None,
    output_root: Path | None = None,
    splits: Mapping[str, Iterable[DesignRecord]] | None = None,
) -> ValidationReport:
    values = list(records)
    issues = [
        issue
        for record in values
        for issue in validate_record(record, input_root, output_root)
    ]

    by_design_id: dict[str, list[DesignRecord]] = defaultdict(list)
    by_source_path: dict[str, list[DesignRecord]] = defaultdict(list)
    by_source_id: dict[str, list[DesignRecord]] = defaultdict(list)
    for record in values:
        design_id = record.identity.get("design_id")
        source_path = record.identity.get("source_path")
        source_id = record.identity.get("source_design_id")
        if isinstance(design_id, str) and design_id:
            by_design_id[design_id].append(record)
        if isinstance(source_path, str) and source_path:
            by_source_path[source_path.casefold()].append(record)
        if isinstance(source_id, str) and source_id:
            by_source_id[source_id].append(record)

    for design_id, duplicates in sorted(by_design_id.items()):
        if len(duplicates) > 1:
            duplicate_source_path = duplicates[0].identity.get("source_path")
            issues.append(
                ValidationIssue(
                    "error",
                    "duplicate_design_id",
                    f"design ID appears {len(duplicates)} times",
                    design_id,
                    duplicate_source_path if isinstance(duplicate_source_path, str) else None,
                )
            )
    for duplicates in by_source_path.values():
        if len(duplicates) > 1:
            issues.append(_issue(duplicates[0], "error", "duplicate_output_record", "source path appears more than once in output"))
    for duplicates in by_source_id.values():
        if len(duplicates) > 1 and all(
            record.augmentation.get("relation") == "original"
            and record.source_metadata.get("pair_metadata") is None
            for record in duplicates
        ):
            issues.append(
                _issue(
                    duplicates[0],
                    "warning",
                    "duplicate_source_id_without_lineage",
                    "source group is duplicated without augmentation or pair lineage",
                )
            )

    if splits is not None:
        materialized_splits = {
            split_name: list(split_records)
            for split_name, split_records in splits.items()
        }
        for split_name in sorted(set(materialized_splits) - set(SPLIT_NAMES)):
            issues.append(
                ValidationIssue(
                    "error",
                    "unknown_split",
                    f"unexpected split name: {split_name}",
                )
            )
        for split_name in SPLIT_NAMES:
            if split_name not in materialized_splits:
                issues.append(
                    ValidationIssue(
                        "error",
                        "missing_split",
                        f"required split is absent: {split_name}",
                    )
                )

        def record_key(item: DesignRecord) -> tuple[str | None, str | None]:
            design_id = item.identity.get("design_id")
            source_path = item.identity.get("source_path")
            return (
                design_id if isinstance(design_id, str) else None,
                source_path if isinstance(source_path, str) else None,
            )

        expected_records = Counter(record_key(record) for record in values)
        split_records = Counter(
            record_key(record)
            for split_name in SPLIT_NAMES
            for record in materialized_splits.get(split_name, [])
        )
        for key, count in sorted(expected_records.items(), key=str):
            split_count = split_records.get(key, 0)
            if split_count < count:
                issues.append(
                    ValidationIssue(
                        "error",
                        "missing_split_record",
                        "dataset record is absent from split manifests",
                        key[0],
                        key[1],
                    )
                )
            elif split_count > count:
                issues.append(
                    ValidationIssue(
                        "error",
                        "duplicate_split_record",
                        "dataset record appears more than once in split manifests",
                        key[0],
                        key[1],
                    )
                )
        for key in sorted(split_records.keys() - expected_records.keys(), key=str):
            issues.append(
                ValidationIssue(
                    "error",
                    "unknown_split_record",
                    "split manifest contains a record absent from the dataset",
                    key[0],
                    key[1],
                )
            )

        for source_id, split_names in leakage_overlaps(materialized_splits).items():
            issues.append(
                ValidationIssue(
                    "error",
                    "split_leakage",
                    f"source design occurs in splits: {', '.join(split_names)}",
                    None,
                    source_id,
                )
            )

    issues.sort(key=lambda item: (item.severity, item.code, item.source_path or "", item.design_id or ""))
    return ValidationReport(
        record_count=len(values),
        issue_counts=dict(sorted(Counter(issue.severity for issue in issues).items())),
        issues=issues,
    )


def write_validation_report(output_dir: Path, report: ValidationReport) -> None:
    write_json(output_dir / "validation.json", report.to_dict())
    lines = [
        "# Dataset validation report",
        "",
        f"- Records: {report.record_count}",
        f"- Valid: {'yes' if report.is_valid else 'no'}",
        f"- Errors: {report.issue_counts.get('error', 0)}",
        f"- Warnings: {report.issue_counts.get('warning', 0)}",
        "",
        "## Issues",
        "",
    ]
    if not report.issues:
        lines.append("No issues detected.")
    else:
        for issue in report.issues:
            location = issue.source_path or issue.design_id or "dataset"
            lines.append(f"- [{issue.severity.upper()}] `{issue.code}` ({location}): {issue.message}")
    from .serialization import _atomic_text_write

    _atomic_text_write(output_dir / "validation.md", "\n".join(lines) + "\n")
