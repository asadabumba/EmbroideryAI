from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.generated_dataset import load_successful_variants

from .canonicalize import normalize_path_key


def _optional_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
            entries[output_key] = LineageInfo(
                source_design_key=source_path,
                relation="translated_variant",
                original_source_path=source_path,
                x_translation=_optional_float(variant.actual_x or variant.requested_x),
                y_translation=_optional_float(variant.actual_y or variant.requested_y),
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
        matches = [value for candidate, value in self._entries.items() if key.endswith(candidate)]
        if len(matches) == 1:
            return matches[0]
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
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("pairs"), list):
            raise ValueError("pair metadata must contain a pairs list")
        entries: dict[str, dict[str, Any]] = {}
        for row in value["pairs"]:
            if not isinstance(row, dict):
                raise TypeError("each pair metadata row must be an object")
            for field in ("emb_file", "dst_file"):
                candidate = row.get(field)
                if isinstance(candidate, str):
                    entries[normalize_path_key(candidate)] = dict(row)
        return cls(entries)

    def lookup(self, relative_path: str) -> dict[str, Any] | None:
        key = normalize_path_key(relative_path)
        if key in self._entries:
            return dict(self._entries[key])
        matches = [value for candidate, value in self._entries.items() if candidate.endswith(key)]
        if len(matches) == 1:
            return dict(matches[0])
        return None
