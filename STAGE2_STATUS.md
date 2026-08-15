# Stage 2 status

## Current stage

Stage 2 foundation and locally testable hardening are complete. Real-corpus validation is pending because the corpus is absent from this machine.

## Completed components

- Audited `EmbReader`, `DSTParser`, `DDDParser`, `ContentsParser`, legacy builders, generated-variant metadata, strict-pair metadata, tests, and the audit pipeline.
- Implemented canonical schema `2.0.0` with deterministic identities, geometry, events, lineage, statistics, nullable unavailable fields, and provenance separation.
- Implemented adapters that reuse the working DST/DDD/EMB parsers and refuse to promote exploratory `Contents` values to labels.
- Implemented deterministic original-design grouped 80/10/10 splitting and explicit leakage detection.
- Implemented a dependency-free, deterministic, headless PNG stitch renderer.
- Implemented validation with JSON and Markdown reports.
- Reject non-standard `NaN`/`Infinity` values on both serialization and deserialization, and validate canonical geometry, count, command, identity, and translation-lineage invariants.
- Implemented a resumable, incremental, per-file-isolated builder with JSON/JSONL manifests, split manifests, preview output, and failure logging.
- Hardened lineage and pair indexes against duplicate/ambiguous mappings; uniquely prefixed original references are reconciled to discovered source paths without losing reported provenance.
- Added stable source-keyed cache/preview artifacts, pipeline-version invalidation (`1.2.0`), corrupt-cache rebuilding, configurable CLI split ratios, and safe input/output layout checks.
- Made preview bounds depend on drawn segments, so hidden positioning jumps no longer change normalized render scale.
- Added DST header command/color-count diagnostics and validation of declared preview files and complete split membership.
- Implemented deterministic normalized-trajectory and sequence-feature baselines; no trained-model result is claimed.
- Added focused synthetic unit tests for canonicalization, normalization, deltas, geometry, IDs, serialization, grouping, leakage, validation, rendering, malformed inputs, lineage, resumability, and deterministic rebuilds.
- Documented the supported fields and staged image-to-embroidery research plan.

## Tests

- Baseline before Stage 2 changes: 16 passed, 3 skipped for absent corpus, 1 failed because `logs/emb_dst_ranking/ranking.json` is absent.
- Stage 2 focused tests: **33 passed** in 1.57 seconds.
- Latest full-suite result: **281 passed, 1 failed, 4 skipped** in 3.46 seconds.
- Full suite excluding the protected known Wilcom failure: **281 passed, 4 skipped, 1 deselected** in 3.18 seconds.
- The one failure is the deterministic, out-of-scope Wilcom GUI test `test_close_returns_immediately_when_active_stem_disappears`: its mocks do not intercept a real `EnumWindows` call, which raises WinError 1400. The mission-protected Wilcom automation files were not modified.
- All four skips have explicit missing-data reasons: three absent EMB/DST corpus checks and one absent strict-pair ranking source.
- Empty-corpus CLI smoke test: builder exit 0, baseline exit 0, 0 discovered/failed/validation errors.
- Empty-corpus audit pipeline: exit 0; 0 EMB, 0 DST, 0 shared names, and 0 strict candidates (no corpus conclusion claimed).
- Checked-in strict-pair metadata index load: passed; declared and actual row counts are both 57.
- The strict-pair integration test now skips when its real ranking source is unavailable, matching the corpus-aware behavior of the other integration tests.

## Real files available

- Raw EMB: 0.
- Raw DST: 0.
- Checked-in `dataset/paired/strict_pairs.json`: 57 historical references/metadata rows; referenced files are unavailable and were not revalidated.

## Real files still needed

See `REAL_DATA_NEEDED.md`: ten paired original EMB/DST families, four translated variants across two families, their actual lineage CSV, pair provenance, and SHA-256 manifest.

## Schema version

`2.0.0`

Builder pipeline version: `1.2.0`.

## Blockers

- No raw EMB/DST corpus or strict-pair ranking source is available, so real extraction statistics and pair revalidation cannot be produced.
- The repository `.git` directory is read-only in this session. An explicit milestone commit failed because Git could not create `.git/index.lock`; all work remains uncommitted.
- One pre-existing Wilcom GUI unit test fails outside Stage 2 scope as described above; protected Wilcom files were left untouched.

## Next work

1. When the requested sample arrives, run the builder/audit and record field coverage and validation results without extrapolating to the full corpus.
2. Confirm the historical strict-pair rows against their source ranking and supplied files.
3. Use measured JSON array sizes to decide whether an NPZ/Parquet array backend is justified; schema 2.0 remains format-independent.
4. Commit the validated working-tree changes once `.git` write access is available.

## Latest commit

Latest repository commit: `13ba12b` (`Document Stage 2 dataset contract and roadmap`). The validated hardening work described above is uncommitted because `.git` is read-only.
