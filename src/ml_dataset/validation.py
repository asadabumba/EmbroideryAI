from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .schema import DesignRecord
from .serialization import write_json
from .splitting import leakage_overlaps


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
    return ValidationIssue(severity, code, message, record.design_id, record.source_path)


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def validate_record(record: DesignRecord, input_root: Path | None = None) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    identity = record.identity
    for name in ("design_id", "source_design_id", "source_path", "format", "content_sha256"):
        if not isinstance(identity.get(name), str) or not identity[name]:
            issues.append(_issue(record, "error", "corrupt_identity", f"identity.{name} is missing"))
    content_hash = identity.get("content_sha256")
    if isinstance(content_hash, str) and not re.fullmatch(r"[0-9a-f]{64}", content_hash):
        issues.append(
            _issue(record, "error", "invalid_content_hash", "content SHA-256 is not 64 lowercase hex characters")
        )

    if input_root is not None and not (input_root / record.source_path).is_file():
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
        if (
            not isinstance(point, list)
            or len(point) != 2
            or not all(_finite_number(value) for value in point)
        ):
            issues.append(
                _issue(record, "error", "invalid_coordinate", f"coordinate {index} is invalid")
            )
            break

    events = record.stitch.get("command_sequence")
    if not isinstance(events, list):
        issues.append(_issue(record, "error", "corrupt_command_sequence", "command sequence is not a list"))
        events = []
    current_x = 0.0
    current_y = 0.0
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            issues.append(_issue(record, "error", "malformed_command", f"command {index} is not an object"))
            continue
        event_type = event.get("type")
        if event_type not in KNOWN_COMMAND_TYPES:
            issues.append(_issue(record, "error", "unknown_command", f"command {index} has type {event_type!r}"))
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
    if events and not any(event.get("type") == "end" for event in events if isinstance(event, dict)):
        issues.append(_issue(record, "error", "missing_end_command", "non-empty command sequence has no end command"))

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
    return issues


def validate_dataset(
    records: Iterable[DesignRecord],
    *,
    input_root: Path | None = None,
    splits: Mapping[str, Iterable[DesignRecord]] | None = None,
) -> ValidationReport:
    values = list(records)
    issues = [issue for record in values for issue in validate_record(record, input_root)]

    by_design_id: dict[str, list[DesignRecord]] = defaultdict(list)
    by_source_path: dict[str, list[DesignRecord]] = defaultdict(list)
    by_source_id: dict[str, list[DesignRecord]] = defaultdict(list)
    for record in values:
        by_design_id[record.design_id].append(record)
        by_source_path[record.source_path.casefold()].append(record)
        by_source_id[record.source_design_id].append(record)

    for design_id, duplicates in sorted(by_design_id.items()):
        if len(duplicates) > 1:
            issues.append(
                ValidationIssue(
                    "error",
                    "duplicate_design_id",
                    f"design ID appears {len(duplicates)} times",
                    design_id,
                    duplicates[0].source_path,
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
        for source_id, split_names in leakage_overlaps(splits).items():
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
