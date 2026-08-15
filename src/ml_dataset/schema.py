from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


SCHEMA_VERSION = "2.0.0"


@dataclass
class DesignRecord:
    """Format-independent, inspectable representation of one design file."""

    schema_version: str
    identity: dict[str, Any]
    geometry: dict[str, Any]
    stitch: dict[str, Any]
    color_thread: dict[str, Any]
    augmentation: dict[str, Any]
    statistics: dict[str, Any]
    rendering: dict[str, Any]
    source_metadata: dict[str, Any]
    parse_diagnostics: list[dict[str, Any]]

    @property
    def design_id(self) -> str:
        return str(self.identity["design_id"])

    @property
    def source_design_id(self) -> str:
        return str(self.identity["source_design_id"])

    @property
    def source_path(self) -> str:
        return str(self.identity["source_path"])

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DesignRecord":
        required = {
            "schema_version",
            "identity",
            "geometry",
            "stitch",
            "color_thread",
            "augmentation",
            "statistics",
            "rendering",
            "source_metadata",
            "parse_diagnostics",
        }
        missing = sorted(required - set(value))
        if missing:
            raise ValueError(f"record is missing required fields: {', '.join(missing)}")

        schema_version = value["schema_version"]
        if schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported schema version {schema_version!r}; expected {SCHEMA_VERSION!r}"
            )

        mapping_fields = required - {"schema_version", "parse_diagnostics"}
        for field_name in mapping_fields:
            if not isinstance(value[field_name], Mapping):
                raise TypeError(f"{field_name} must be an object")
        if not isinstance(value["parse_diagnostics"], list):
            raise TypeError("parse_diagnostics must be a list")

        return cls(
            schema_version=SCHEMA_VERSION,
            identity=dict(value["identity"]),
            geometry=dict(value["geometry"]),
            stitch=dict(value["stitch"]),
            color_thread=dict(value["color_thread"]),
            augmentation=dict(value["augmentation"]),
            statistics=dict(value["statistics"]),
            rendering=dict(value["rendering"]),
            source_metadata=dict(value["source_metadata"]),
            parse_diagnostics=[dict(item) for item in value["parse_diagnostics"]],
        )
