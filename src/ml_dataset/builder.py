from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters import SUPPORTED_SUFFIXES, parse_source
from .canonicalize import canonicalize_design, sha256_file
from .lineage import LineageIndex, PairMetadataIndex, path_keys_match
from .rendering import render_preview
from .schema import SCHEMA_VERSION, DesignRecord
from .serialization import read_record, write_json, write_jsonl, write_record
from .splitting import (
    assign_grouped_splits,
    records_by_split,
    split_statistics,
    validate_split_ratios,
)
from .validation import validate_dataset, validate_record, write_validation_report


BUILD_PIPELINE_VERSION = "1.2.0"


@dataclass(frozen=True)
class BuildConfig:
    input_dir: Path
    output_dir: Path
    seed: int = 20260816
    train_ratio: float = 0.8
    validation_ratio: float = 0.1
    test_ratio: float = 0.1
    preview_width: int = 256
    preview_height: int = 256
    lineage_csv: Path | None = None
    pair_metadata: Path | None = None


@dataclass(frozen=True)
class BuildResult:
    discovered_count: int
    record_count: int
    built_count: int
    reused_count: int
    failed_count: int
    validation_error_count: int
    output_dir: Path


class DatasetBuilder:
    def __init__(self, config: BuildConfig):
        self.config = config
        self.input_dir = config.input_dir.resolve()
        self.output_dir = config.output_dir.resolve()
        if self.input_dir == self.output_dir or self.input_dir.is_relative_to(
            self.output_dir
        ):
            raise ValueError(
                "output directory cannot be the input directory or one of its parents"
            )
        if config.preview_width < 17 or config.preview_height < 17:
            raise ValueError(
                "preview dimensions must be at least 17x17 for the default padding"
            )
        validate_split_ratios(
            {
                "train": config.train_ratio,
                "validation": config.validation_ratio,
                "test": config.test_ratio,
            }
        )
        self.lineage = (
            LineageIndex.from_csv(config.lineage_csv)
            if config.lineage_csv is not None
            else LineageIndex()
        )
        self.pairs = (
            PairMetadataIndex.from_json(config.pair_metadata)
            if config.pair_metadata is not None
            else PairMetadataIndex()
        )

    def discover(self) -> list[Path]:
        if not self.input_dir.is_dir():
            raise FileNotFoundError(f"input directory does not exist: {self.input_dir}")
        files = []
        for path in self.input_dir.rglob("*"):
            if not path.is_file() or path.suffix.casefold() not in SUPPORTED_SUFFIXES:
                continue
            try:
                path.resolve().relative_to(self.output_dir)
            except ValueError:
                files.append(path)
        return sorted(files, key=lambda path: path.relative_to(self.input_dir).as_posix().casefold())

    def _fingerprint(self, lineage: dict[str, Any], pair_metadata: dict[str, Any] | None) -> str:
        value = json.dumps(
            {
                "schema": SCHEMA_VERSION,
                "pipeline": BUILD_PIPELINE_VERSION,
                "lineage": lineage,
                "pair": pair_metadata,
                "renderer": "ml_dataset.raster_v1",
                "preview_width": self.config.preview_width,
                "preview_height": self.config.preview_height,
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _source_artifact_key(relative_path: str) -> str:
        return hashlib.sha256(relative_path.casefold().encode("utf-8")).hexdigest()

    def _record_path(self, relative_path: str) -> Path:
        return (
            self.output_dir
            / "records"
            / f"{self._source_artifact_key(relative_path)}.json"
        )

    @staticmethod
    def _resolve_source_reference(
        source_reference: str, discovered_paths: list[str]
    ) -> str:
        matches = [
            candidate
            for candidate in discovered_paths
            if path_keys_match(source_reference, candidate)
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(
                f"original source reference is ambiguous: {source_reference}"
            )
        return source_reference

    def _load_cached(
        self,
        record_path: Path,
        relative_path: str,
        content_hash: str,
        fingerprint: str,
    ) -> DesignRecord | None:
        if not record_path.is_file():
            return None
        try:
            record = read_record(record_path)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None
        cache_matches = (
            record.identity.get("source_path") == relative_path
            and record.identity.get("content_sha256") == content_hash
            and record.source_metadata.get("build_fingerprint") == fingerprint
            and not any(
                issue.severity == "error" for issue in validate_record(record)
            )
        )
        if not cache_matches:
            return None
        if record.geometry.get("absolute_stitch_coordinates"):
            expected_preview = (
                f"previews/{self._source_artifact_key(relative_path)}.png"
            )
            if (
                record.rendering.get("preview_path") != expected_preview
                or record.rendering.get("width_px") != self.config.preview_width
                or record.rendering.get("height_px") != self.config.preview_height
                or record.rendering.get("renderer") != "ml_dataset.raster_v1"
            ):
                return None
        return record

    def build(self) -> BuildResult:
        files = self.discover()
        discovered_paths = [
            path.relative_to(self.input_dir).as_posix() for path in files
        ]
        self.output_dir.mkdir(parents=True, exist_ok=True)
        records: list[DesignRecord] = []
        failures: list[dict[str, str]] = []
        built_count = 0
        reused_count = 0

        for path in files:
            relative_path = path.relative_to(self.input_dir).as_posix()
            try:
                content_hash = sha256_file(path)
                lineage = self.lineage.lookup(relative_path)
                pair_metadata = self.pairs.lookup(relative_path)
                source_design_key = lineage.source_design_key
                augmentation = lineage.as_augmentation()
                if lineage.relation == "translated_variant":
                    resolved_source = self._resolve_source_reference(
                        source_design_key, discovered_paths
                    )
                    if resolved_source != source_design_key:
                        augmentation["metadata"][
                            "reported_original_source_path"
                        ] = augmentation["original_source_path"]
                        augmentation["original_source_path"] = resolved_source
                        source_design_key = resolved_source
                if pair_metadata is not None and lineage.relation == "original":
                    normalized_name = pair_metadata.get("normalized_name")
                    if isinstance(normalized_name, str) and normalized_name:
                        source_design_key = f"pair:{normalized_name}"
                        augmentation["relation"] = "paired_format"
                        augmentation["original_source_path"] = str(
                            pair_metadata.get("emb_file") or relative_path
                        ).replace("\\", "/")
                fingerprint = self._fingerprint(augmentation, pair_metadata)
                record_path = self._record_path(relative_path)
                record = self._load_cached(record_path, relative_path, content_hash, fingerprint)
                if record is None:
                    parsed = parse_source(path)
                    record = canonicalize_design(
                        source_path=relative_path,
                        source_format=parsed.source_format,
                        content_sha256=content_hash,
                        commands=parsed.commands,
                        observed_metadata=parsed.observed_metadata,
                        source_design_key=source_design_key,
                        augmentation=augmentation,
                        pair_metadata=pair_metadata,
                        unit_mm=parsed.unit_mm,
                        diagnostics=parsed.diagnostics,
                    )
                    record.source_metadata["build_fingerprint"] = fingerprint
                    record.source_metadata[
                        "build_pipeline_version"
                    ] = BUILD_PIPELINE_VERSION
                    if record.geometry["absolute_stitch_coordinates"]:
                        preview_relative = (
                            f"previews/{self._source_artifact_key(relative_path)}.png"
                        )
                        render_preview(
                            record,
                            self.output_dir / preview_relative,
                            width=self.config.preview_width,
                            height=self.config.preview_height,
                        )
                        record.rendering.update(
                            {
                                "preview_path": preview_relative,
                                "width_px": self.config.preview_width,
                                "height_px": self.config.preview_height,
                                "renderer": "ml_dataset.raster_v1",
                            }
                        )
                    write_record(record_path, record)
                    built_count += 1
                else:
                    preview_relative = record.rendering.get("preview_path")
                    if (
                        record.geometry.get("absolute_stitch_coordinates")
                        and isinstance(preview_relative, str)
                        and not (self.output_dir / preview_relative).is_file()
                    ):
                        render_preview(
                            record,
                            self.output_dir / preview_relative,
                            width=self.config.preview_width,
                            height=self.config.preview_height,
                        )
                    reused_count += 1
                records.append(record)
            except Exception as error:  # noqa: BLE001 - per-file isolation is intentional
                failures.append(
                    {
                        "source_path": relative_path,
                        "error_type": type(error).__name__,
                        "error": str(error),
                    }
                )

        records.sort(key=lambda record: (record.source_path.casefold(), record.design_id))
        assignments = assign_grouped_splits(
            records,
            seed=self.config.seed,
            ratios={
                "train": self.config.train_ratio,
                "validation": self.config.validation_ratio,
                "test": self.config.test_ratio,
            },
        )
        splits = records_by_split(records, assignments)

        write_jsonl(self.output_dir / "manifest.jsonl", [record.to_dict() for record in records])
        for split_name, split_records in splits.items():
            write_jsonl(
                self.output_dir / "splits" / f"{split_name}.jsonl",
                [record.to_dict() for record in split_records],
            )
        write_jsonl(self.output_dir / "failed.jsonl", failures)
        statistics = split_statistics(splits)
        write_json(
            self.output_dir / "manifest.json",
            {
                "schema_version": SCHEMA_VERSION,
                "build_pipeline_version": BUILD_PIPELINE_VERSION,
                "record_count": len(records),
                "failed_count": len(failures),
                "manifest": "manifest.jsonl",
                "split_statistics": statistics,
                "split_seed": self.config.seed,
                "split_ratios": {
                    "train": self.config.train_ratio,
                    "validation": self.config.validation_ratio,
                    "test": self.config.test_ratio,
                },
            },
        )
        report = validate_dataset(
            records,
            input_root=self.input_dir,
            output_root=self.output_dir,
            splits=splits,
        )
        write_validation_report(self.output_dir, report)
        write_json(
            self.output_dir / "build_report.json",
            {
                "discovered_count": len(files),
                "record_count": len(records),
                "built_count": built_count,
                "reused_count": reused_count,
                "failed_count": len(failures),
                "validation_error_count": report.issue_counts.get("error", 0),
                "validation_warning_count": report.issue_counts.get("warning", 0),
            },
        )
        return BuildResult(
            discovered_count=len(files),
            record_count=len(records),
            built_count=built_count,
            reused_count=reused_count,
            failed_count=len(failures),
            validation_error_count=report.issue_counts.get("error", 0),
            output_dir=self.output_dir,
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the Stage 2 embroidery ML dataset")
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--seed", type=int, default=20260816)
    parser.add_argument("--lineage-csv", type=Path)
    parser.add_argument("--pair-metadata", type=Path)
    parser.add_argument("--preview-width", type=int, default=256)
    parser.add_argument("--preview-height", type=int, default=256)
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--validation-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    return parser


def main() -> int:
    args = _parser().parse_args()
    result = DatasetBuilder(
        BuildConfig(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            seed=args.seed,
            lineage_csv=args.lineage_csv,
            pair_metadata=args.pair_metadata,
            preview_width=args.preview_width,
            preview_height=args.preview_height,
            train_ratio=args.train_ratio,
            validation_ratio=args.validation_ratio,
            test_ratio=args.test_ratio,
        )
    ).build()
    print(json.dumps({**result.__dict__, "output_dir": str(result.output_dir)}, indent=2))
    return 0 if result.failed_count == 0 and result.validation_error_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
