from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters import SUPPORTED_SUFFIXES, parse_source
from .canonicalize import canonicalize_design, sha256_file
from .lineage import LineageIndex, PairMetadataIndex
from .rendering import render_preview
from .schema import SCHEMA_VERSION, DesignRecord
from .serialization import read_record, write_json, write_jsonl, write_record
from .splitting import assign_grouped_splits, records_by_split, split_statistics
from .validation import validate_dataset, write_validation_report


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
                "lineage": lineage,
                "pair": pair_metadata,
                "renderer": "ml_dataset.raster_v1",
                "preview_width": self.config.preview_width,
                "preview_height": self.config.preview_height,
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _record_path(self, relative_path: str, design_id: str) -> Path:
        path_key = hashlib.sha256(relative_path.casefold().encode("utf-8")).hexdigest()[:12]
        return self.output_dir / "records" / f"{path_key}__{design_id}.json"

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
        if (
            record.source_path == relative_path
            and record.identity.get("content_sha256") == content_hash
            and record.source_metadata.get("build_fingerprint") == fingerprint
        ):
            return record
        return None

    def build(self) -> BuildResult:
        files = self.discover()
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
                if pair_metadata is not None and lineage.relation == "original":
                    normalized_name = pair_metadata.get("normalized_name")
                    if isinstance(normalized_name, str) and normalized_name:
                        source_design_key = f"pair:{normalized_name}"
                        augmentation["relation"] = "paired_format"
                        augmentation["original_source_path"] = str(
                            pair_metadata.get("emb_file") or relative_path
                        ).replace("\\", "/")
                fingerprint = self._fingerprint(augmentation, pair_metadata)
                provisional_id = canonicalize_design(
                    source_path=relative_path,
                    source_format=path.suffix.lstrip("."),
                    content_sha256=content_hash,
                ).design_id
                record_path = self._record_path(relative_path, provisional_id)
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
                    if record.geometry["absolute_stitch_coordinates"]:
                        preview_relative = f"previews/{record.design_id}.png"
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
        report = validate_dataset(records, input_root=self.input_dir, splits=splits)
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
        )
    ).build()
    print(json.dumps({**result.__dict__, "output_dir": str(result.output_dir)}, indent=2))
    return 0 if result.failed_count == 0 and result.validation_error_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
