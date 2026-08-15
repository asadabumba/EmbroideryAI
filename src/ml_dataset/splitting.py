from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from typing import Iterable, Mapping

from .schema import DesignRecord


SPLIT_NAMES = ("train", "validation", "test")


def validate_split_ratios(ratios: Mapping[str, float]) -> None:
    if set(ratios) != set(SPLIT_NAMES):
        raise ValueError(f"ratios must contain exactly: {', '.join(SPLIT_NAMES)}")
    if any(value < 0 for value in ratios.values()):
        raise ValueError("split ratios cannot be negative")
    if not math.isclose(sum(ratios.values()), 1.0, abs_tol=1e-9):
        raise ValueError("split ratios must sum to 1")


def _split_counts(group_count: int, ratios: Mapping[str, float]) -> dict[str, int]:
    raw = {name: ratios[name] * group_count for name in SPLIT_NAMES}
    counts = {name: math.floor(raw[name]) for name in SPLIT_NAMES}
    remaining = group_count - sum(counts.values())
    order = sorted(SPLIT_NAMES, key=lambda name: (-(raw[name] - counts[name]), SPLIT_NAMES.index(name)))
    for name in order[:remaining]:
        counts[name] += 1

    nonzero = [name for name in SPLIT_NAMES if ratios[name] > 0]
    if group_count >= len(nonzero):
        for empty_name in [name for name in nonzero if counts[name] == 0]:
            donor = max(SPLIT_NAMES, key=lambda name: counts[name])
            if counts[donor] > 1:
                counts[donor] -= 1
                counts[empty_name] += 1
    return counts


def assign_grouped_splits(
    records: Iterable[DesignRecord],
    *,
    seed: int = 20260816,
    ratios: Mapping[str, float] | None = None,
) -> dict[str, str]:
    selected_ratios = dict(ratios or {"train": 0.8, "validation": 0.1, "test": 0.1})
    validate_split_ratios(selected_ratios)
    group_ids = sorted({record.source_design_id for record in records})
    ranked = sorted(
        group_ids,
        key=lambda group_id: hashlib.sha256(f"{seed}\0{group_id}".encode("utf-8")).digest(),
    )
    counts = _split_counts(len(ranked), selected_ratios)
    assignments: dict[str, str] = {}
    position = 0
    for split_name in SPLIT_NAMES:
        for group_id in ranked[position : position + counts[split_name]]:
            assignments[group_id] = split_name
        position += counts[split_name]
    return assignments


def records_by_split(
    records: Iterable[DesignRecord], assignments: Mapping[str, str]
) -> dict[str, list[DesignRecord]]:
    result: dict[str, list[DesignRecord]] = {name: [] for name in SPLIT_NAMES}
    for record in records:
        split_name = assignments[record.source_design_id]
        result[split_name].append(record)
    for values in result.values():
        values.sort(key=lambda record: (record.source_path, record.design_id))
    return result


def leakage_overlaps(splits: Mapping[str, Iterable[DesignRecord]]) -> dict[str, list[str]]:
    membership: dict[str, set[str]] = defaultdict(set)
    for split_name, records in splits.items():
        for record in records:
            membership[record.source_design_id].add(split_name)
    return {
        group_id: sorted(split_names)
        for group_id, split_names in sorted(membership.items())
        if len(split_names) > 1
    }


def split_statistics(splits: Mapping[str, Iterable[DesignRecord]]) -> dict[str, dict[str, int]]:
    result = {}
    for split_name in SPLIT_NAMES:
        values = list(splits.get(split_name, []))
        result[split_name] = {
            "records": len(values),
            "source_design_groups": len({record.source_design_id for record in values}),
            "augmented_variants": sum(
                record.augmentation.get("relation") != "original" for record in values
            ),
        }
    return result
