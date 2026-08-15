# Stage 2 status

## Current stage

Foundation implemented, documented, and validated against the complete locally runnable test suite. Real-corpus validation is pending because the corpus is absent from this machine.

## Completed components

- Audited `EmbReader`, `DSTParser`, `DDDParser`, `ContentsParser`, legacy builders, generated-variant metadata, strict-pair metadata, tests, and the audit pipeline.
- Implemented canonical schema `2.0.0` with deterministic identities, geometry, events, lineage, statistics, nullable unavailable fields, and provenance separation.
- Implemented adapters that reuse the working DST/DDD/EMB parsers and refuse to promote exploratory `Contents` values to labels.
- Implemented deterministic original-design grouped 80/10/10 splitting and explicit leakage detection.
- Implemented a dependency-free, deterministic, headless PNG stitch renderer.
- Implemented validation with JSON and Markdown reports.
- Implemented a resumable, incremental, per-file-isolated builder with JSON/JSONL manifests, split manifests, preview output, and failure logging.
- Implemented deterministic normalized-trajectory and sequence-feature baselines; no trained-model result is claimed.
- Added focused synthetic unit tests for canonicalization, normalization, deltas, geometry, IDs, serialization, grouping, leakage, validation, rendering, malformed inputs, lineage, resumability, and deterministic rebuilds.
- Documented the supported fields and staged image-to-embroidery research plan.

## Tests

- Baseline before Stage 2 changes: 16 passed, 3 skipped for absent corpus, 1 failed because `logs/emb_dst_ranking/ranking.json` is absent.
- New Stage 2 focused tests: 13 passed.
- Full final test result: **262 passed, 4 skipped** in 2.80 seconds.
- All four skips have explicit missing-data reasons: three absent EMB/DST corpus checks and one absent strict-pair ranking source.
- Empty-corpus CLI smoke test: builder exit 0, baseline exit 0, 0 discovered/failed/validation errors.
- The strict-pair integration test now skips when its real ranking source is unavailable, matching the corpus-aware behavior of the other integration tests.

## Real files available

- Raw EMB: 0.
- Raw DST: 0.
- Checked-in `dataset/paired/strict_pairs.json`: 71 historical references/metadata rows; referenced files are unavailable and were not revalidated.

## Real files still needed

See `REAL_DATA_NEEDED.md`: ten paired original EMB/DST families, four translated variants across two families, their actual lineage CSV, pair provenance, and SHA-256 manifest.

## Schema version

`2.0.0`

## Next work

1. When the requested sample arrives, run the builder/audit and record field coverage and validation results without extrapolating to the full corpus.
2. Confirm the historical strict-pair rows against their source ranking and supplied files.
3. Use measured JSON array sizes to decide whether an NPZ/Parquet array backend is justified; schema 2.0 remains format-independent.

## Latest commit

Latest repository commit: the current status/documentation milestone (`Document Stage 2 dataset contract and roadmap`; use `git log -1 --oneline` for its self-referential hash). Latest validated implementation commit: `8b40d58` (`Build Stage 2 ML dataset foundation`).
