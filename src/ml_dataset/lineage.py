from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.generated_dataset import load_successful_variants

from .canonicalize import normalize_path_key
from .serialization import read_json


def _optional_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def path_keys_match(first: str, second: str) -> bool:
    first = normalize_path_key(first)
    second = normalize_path_key(second)
    return (
        first == second
        or first.endswith(f"/{second}")
        or second.endswith(f"/{first}")
    )


@dataclass(frozen=True)
class LineageInfo:
    source_design_key: str
    relation: str
    original_source_path: str
    x_translation: float | None = None
    y_translation: float | None = None
    metadata: dict[str, Any] | None = None

    def as_augmentation(self) -> dict[str, Any]:
        return {
            "relation": self.relation,
            "original_source_path": self.original_source_path,
            "x_translation": self.x_translation,
            "y_translation": self.y_translation,
            "metadata": dict(self.metadata or {}),
        }


class LineageIndex:
    def __init__(self, entries: dict[str, LineageInfo] | None = None):
        self._entries = entries or {}

    @classmethod
    def from_csv(cls, path: Path) -> "LineageIndex":
        entries: dict[str, LineageInfo] = {}
        for variant in load_successful_variants(path):
            output_key = normalize_path_key(variant.output_file)
            source_path = variant.source_file.replace("\\", "/")
            if not output_key:
                raise ValueError("successful lineage row has no relative_output_file")
            if not normalize_path_key(source_path):
                raise ValueError(
                    f"successful lineage row for {variant.output_file!r} has no relative_source_file"
                )
            x_translation = _optional_float(variant.actual_x or variant.requested_x)
            y_translation = _optional_float(variant.actual_y or variant.requested_y)
            if x_translation is None or y_translation is None:
                raise ValueError(
                    f"successful lineage row for {variant.output_file!r} has invalid coordinates"
                )
            if output_key in entries:
                raise ValueError(
                    f"duplicate successful lineage output path: {variant.output_file}"
                )
            entries[output_key] = LineageInfo(
                source_design_key=source_path,
                relation="translated_variant",
                original_source_path=source_path,
                x_translation=x_translation,
                y_translation=y_translation,
                metadata={
                    "requested_x": _optional_float(variant.requested_x),
                    "requested_y": _optional_float(variant.requested_y),
                    "attempts": variant.attempts,
                },
            )
        return cls(entries)

    def lookup(self, relative_path: str) -> LineageInfo:
        key = normalize_path_key(relative_path)
        if key in self._entries:
            return self._entries[key]
        matches = [
            value
            for candidate, value in self._entries.items()
            if path_keys_match(key, candidate)
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(f"ambiguous lineage path: {relative_path}")
        normalized = relative_path.replace("\\", "/")
        return LineageInfo(
            source_design_key=normalized,
            relation="original",
            original_source_path=normalized,
        )


class PairMetadataIndex:
    def __init__(self, entries: dict[str, dict[str, Any]] | None = None):
        self._entries = entries or {}

    @classmethod
    def from_json(cls, path: Path) -> "PairMetadataIndex":
        value = read_json(path)
        if not isinstance(value, dict) or not isinstance(value.get("pairs"), list):
            raise ValueError("pair metadata must contain a pairs list")
        declared_count = value.get("pair_count")
        if declared_count is not None and (
            not isinstance(declared_count, int)
            or isinstance(declared_count, bool)
            or declared_count != len(value["pairs"])
        ):
            raise ValueError("pair metadata pair_count does not match its pairs list")
        entries: dict[str, dict[str, Any]] = {}
        for index, row in enumerate(value["pairs"]):
            if not isinstance(row, dict):
                raise TypeError("each pair metadata row must be an object")
            normalized_name = row.get("normalized_name")
            if not isinstance(normalized_name, str) or not normalized_name.strip():
                raise ValueError(f"pair metadata row {index} has no normalized_name")
            for field in ("emb_file", "dst_file"):
                candidate = row.get(field)
                if not isinstance(candidate, str) or not normalize_path_key(candidate):
                    raise ValueError(f"pair metadata row {index} has no {field}")
                key = normalize_path_key(candidate)
                if key in entries:
                    raise ValueError(f"duplicate pair metadata path: {candidate}")
                entries[key] = dict(row)
        return cls(entries)

    def lookup(self, relative_path: str) -> dict[str, Any] | None:
        key = normalize_path_key(relative_path)
        if key in self._entries:
            return dict(self._entries[key])
        matches = [
            value
            for candidate, value in self._entries.items()
            if path_keys_match(key, candidate)
        ]
        if len(matches) == 1:
            return dict(matches[0])
        if len(matches) > 1:
            raise ValueError(f"ambiguous pair metadata path: {relative_path}")
        return None
