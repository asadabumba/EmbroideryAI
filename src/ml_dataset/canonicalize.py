from __future__ import annotations

import hashlib
import math
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

from .schema import SCHEMA_VERSION, DesignRecord


MOVEMENT_TYPES = {"stitch", "jump", "sequin_eject"}


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_path_key(value: str | Path) -> str:
    return str(value).replace("\\", "/").strip("/").casefold()


def stable_id(namespace: str, value: str, length: int = 24) -> str:
    digest = hashlib.sha256(f"{namespace}\0{value}".encode("utf-8")).hexdigest()
    return f"{namespace}-{digest[:length]}"


def deterministic_design_id(source_format: str, content_sha256: str) -> str:
    return stable_id("design", f"{source_format.casefold()}:{content_sha256}")


def deterministic_source_design_id(source_key: str) -> str:
    return stable_id("source", normalize_path_key(source_key))


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _quantile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _length_statistics(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {
            "min": None,
            "max": None,
            "mean": None,
            "q25": None,
            "median": None,
            "q75": None,
        }
    return {
        "min": min(values),
        "max": max(values),
        "mean": sum(values) / len(values),
        "q25": _quantile(values, 0.25),
        "median": _quantile(values, 0.5),
        "q75": _quantile(values, 0.75),
    }


def _canonical_events(
    commands: Iterable[Mapping[str, Any]], unit_mm: float
) -> list[dict[str, Any]]:
    events = []
    for fallback_index, command in enumerate(commands):
        event_type = str(command.get("type", "unknown"))
        dx_native = _number(command.get("dx"))
        dy_native = _number(command.get("dy"))
        x_native = _number(command.get("x"))
        y_native = _number(command.get("y"))
        events.append(
            {
                "index": int(command.get("index", fallback_index)),
                "type": event_type,
                "dx": None if dx_native is None else dx_native * unit_mm,
                "dy": None if dy_native is None else dy_native * unit_mm,
                "x": None if x_native is None else x_native * unit_mm,
                "y": None if y_native is None else y_native * unit_mm,
                "raw": command.get("raw"),
            }
        )
    return events


def _geometry(events: list[dict[str, Any]]) -> tuple[dict[str, Any], list[float]]:
    points: list[list[float]] = []
    movement_lengths: list[float] = []
    for event in events:
        if event["type"] not in MOVEMENT_TYPES:
            continue
        x = event.get("x")
        y = event.get("y")
        dx = event.get("dx")
        dy = event.get("dy")
        if None in (x, y, dx, dy):
            continue
        movement_lengths.append(math.hypot(float(dx), float(dy)))
        if event["type"] == "stitch":
            points.append([float(x), float(y)])

    if not points:
        return (
            {
                "units": "mm",
                "width": None,
                "height": None,
                "bounding_box": None,
                "center": None,
                "absolute_stitch_coordinates": [],
                "normalized_stitch_coordinates": [],
                "stitch_deltas": [],
                "total_path_length": None,
                "normalization": "bbox_centered_max_dimension",
            },
            [],
        )

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width = max_x - min_x
    height = max_y - min_y
    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0
    scale = max(width, height)
    if scale == 0:
        scale = 1.0
    normalized = [
        [(point[0] - center_x) / scale, (point[1] - center_y) / scale]
        for point in points
    ]
    deltas = [
        [float(event["dx"]), float(event["dy"])]
        for event in events
        if event["type"] == "stitch"
        and event.get("dx") is not None
        and event.get("dy") is not None
    ]
    return (
        {
            "units": "mm",
            "width": width,
            "height": height,
            "bounding_box": {
                "min_x": min_x,
                "min_y": min_y,
                "max_x": max_x,
                "max_y": max_y,
            },
            "center": [center_x, center_y],
            "absolute_stitch_coordinates": points,
            "normalized_stitch_coordinates": normalized,
            "stitch_deltas": deltas,
            "total_path_length": sum(movement_lengths),
            "normalization": "bbox_centered_max_dimension",
        },
        movement_lengths,
    )


def _color_blocks(events: list[dict[str, Any]]) -> list[dict[str, int]]:
    blocks: list[dict[str, int]] = []
    start = 0
    stitch_count = 0
    movement_count = 0
    for event_index, event in enumerate(events):
        if event["type"] == "color_change":
            blocks.append(
                {
                    "index": len(blocks),
                    "start_event_index": start,
                    "end_event_index": event_index,
                    "stitch_count": stitch_count,
                    "movement_count": movement_count,
                }
            )
            start = event_index + 1
            stitch_count = 0
            movement_count = 0
        elif event["type"] == "stitch":
            stitch_count += 1
            movement_count += 1
        elif event["type"] in MOVEMENT_TYPES:
            movement_count += 1
    if events and (movement_count or stitch_count or blocks):
        blocks.append(
            {
                "index": len(blocks),
                "start_event_index": start,
                "end_event_index": len(events),
                "stitch_count": stitch_count,
                "movement_count": movement_count,
            }
        )
    return blocks


def canonicalize_design(
    *,
    source_path: str,
    source_format: str,
    content_sha256: str,
    commands: Iterable[Mapping[str, Any]] = (),
    observed_metadata: Mapping[str, Any] | None = None,
    source_design_key: str | None = None,
    augmentation: Mapping[str, Any] | None = None,
    pair_metadata: Mapping[str, Any] | None = None,
    unit_mm: float = 1.0,
    diagnostics: Iterable[Mapping[str, Any]] = (),
) -> DesignRecord:
    observed = dict(observed_metadata or {})
    augmentation_data = dict(augmentation or {})
    relation = str(augmentation_data.get("relation", "original"))
    original_source_path = str(
        augmentation_data.get("original_source_path") or source_path
    )
    source_key = source_design_key or original_source_path

    events = _canonical_events(commands, unit_mm)
    geometry, movement_lengths = _geometry(events)
    frequencies = dict(sorted(Counter(event["type"] for event in events).items()))
    stitch_lengths = [
        math.hypot(float(event["dx"]), float(event["dy"]))
        for event in events
        if event["type"] == "stitch"
        and event.get("dx") is not None
        and event.get("dy") is not None
    ]

    metadata_stitch_count = observed.get("stitch_count")
    metadata_trim_count = observed.get("trim_count")
    metadata_color_changes = observed.get("color_change_count")
    if events:
        stitch_count: int | None = frequencies.get("stitch", 0)
        jump_count: int | None = frequencies.get("jump", 0)
        color_change_count: int | None = frequencies.get("color_change", 0)
    else:
        stitch_count = int(metadata_stitch_count) if isinstance(metadata_stitch_count, int) else None
        jump_count = None
        color_change_count = (
            int(metadata_color_changes) if isinstance(metadata_color_changes, int) else None
        )
    trim_count = int(metadata_trim_count) if isinstance(metadata_trim_count, int) else None

    augmentation_result = {
        "relation": relation,
        "original_source_path": original_source_path,
        "x_translation": augmentation_data.get("x_translation"),
        "y_translation": augmentation_data.get("y_translation"),
        "metadata": dict(augmentation_data.get("metadata", {})),
    }

    return DesignRecord(
        schema_version=SCHEMA_VERSION,
        identity={
            "design_id": deterministic_design_id(source_format, content_sha256),
            "source_design_id": deterministic_source_design_id(source_key),
            "source_design_key": normalize_path_key(source_key),
            "source_path": source_path.replace("\\", "/"),
            "format": source_format.casefold(),
            "content_sha256": content_sha256,
        },
        geometry=geometry,
        stitch={
            "stitch_count": stitch_count,
            "jump_count": jump_count,
            "trim_count": trim_count,
            "color_change_count": color_change_count,
            "command_sequence": events,
            "color_blocks": _color_blocks(events),
        },
        color_thread={
            "color_sequence": None,
            "thread_information": None,
        },
        augmentation=augmentation_result,
        statistics={
            "stitch_length": _length_statistics(stitch_lengths),
            "movement_length": _length_statistics(movement_lengths),
            "command_frequencies": frequencies,
        },
        rendering={
            "preview_path": None,
            "width_px": None,
            "height_px": None,
            "renderer": None,
        },
        source_metadata={
            "observed": observed,
            "derived_fields": [
                "geometry",
                "normalized_stitch_coordinates",
                "statistics",
                "color_blocks",
            ] if events else [],
            "pair_metadata": dict(pair_metadata) if pair_metadata else None,
        },
        parse_diagnostics=[dict(item) for item in diagnostics],
    )
