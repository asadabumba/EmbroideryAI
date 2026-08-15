# Stage 2 data model and extraction audit

Schema version: `2.0.0`

The canonical record is JSON-compatible and deliberately keeps observed source metadata separate from derived ML features. A record represents one physical source file. Related formats and translated variants share a `source_design_id`, so they are always split as one original-design group.

## What the existing parsers establish

### DST

Directly observed or decoded:

- the 512-byte Tajima header fields, including label and declared stitch/color-change/extents fields when present;
- three-byte command records;
- command-relative integer `dx`/`dy` values;
- command types `stitch`, `jump`, `color_change`, `end`, `sequin_mode`, and state-dependent `sequin_eject`;
- cumulative integer coordinates and the specified `0.1 mm` DST coordinate unit.

Derived by Stage 2:

- millimetre command coordinates and deltas;
- stitch-only absolute coordinates;
- bounding box, dimensions, center, and total movement path length;
- translation-invariant, aspect-preserving normalization around the stitch bounding-box center, scaled by its largest dimension;
- stitch-length and movement-length summary statistics;
- command frequencies and color-block boundaries;
- deterministic raster previews.

Not available from the current DST parser:

- explicit trim commands (jump patterns must not be relabeled as trims without evidence);
- RGB/thread catalog identities or material properties;
- Wilcom object types, satin/tatami classification, density, underlay, pull compensation, or fill direction.

### EMB and DDD

Directly observed or extracted:

- file size, OLE stream names, and file content hash;
- compressed `DESIGN_ICON` and `TRUEVIEW_ICON` streams through `EmbReader` when present;
- DDD scalar properties recognized by `DDDParser`: color/stop/trim/stitch/object counts, thread and bobbin lengths, left/right/up/down/end coordinates, design height/width, machine name, function count, shortest/longest stitch, jumps per trim, color-change count, file type, fabric thickness, and bobbin adjustment;
- the byte/string length of DDD property 18, exposed only as `sequence_list_size`.

The DDD values above are retained under `source_metadata.observed`. They are source properties, not proof of a reconstructed stitch sequence. The current audit does not establish a reliable general conversion of DDD geometry fields to canonical millimetres.

Unavailable with the current EMB parser:

- decoded stitch coordinates or commands;
- decoded color sequence or actual thread catalog entries;
- object-level geometry and digitizing decisions;
- satin/tatami, density, underlay, fill angle, pull compensation, tie-in/tie-off, or sewing-order semantics.

`ContentsParser` is an exploratory binary-record reader. The repository audit explicitly concludes that record boundaries and field semantics are not proven. Stage 2 records therefore note that `Contents` exists but never treat guessed numeric values as labels.

### Checked-in strict-pair metadata

`dataset/paired/strict_pairs.json` directly contains 57 pair references and matching evidence fields: normalized name, EMB/DST paths, DDD and DST stitch counts, relative stitch/width errors, DDD color counts/changes, DST color changes, quality score, coverage percentage, and machine name. Those are historical pair-selection metadata. The declared `pair_count` and all path mappings are checked when the index is loaded.

On this machine, the referenced EMB/DST files and the source ranking JSON are absent. Consequently, Stage 2 does not claim that the 57 pairs were revalidated locally. When the files arrive, the pair index groups the EMB and DST representations under one source design and retains the row as provenance.

## Canonical record

Each JSON/JSONL record contains:

- `identity`: deterministic design and source-group IDs, source path, format, SHA-256;
- `geometry`: units, dimensions, bounding box, center, absolute and normalized stitch coordinates, stitch deltas, path length, normalization method;
- `stitch`: counts, full command/event sequence, color blocks;
- `color_thread`: nullable color sequence and thread information (never fabricated);
- `augmentation`: original source path, relation, translations, and lineage metadata;
- `statistics`: length summaries and command frequencies;
- `rendering`: deterministic preview location/configuration when a path exists;
- `source_metadata`: observed parser output, derived-field declaration, optional pair evidence, and cache fingerprint;
- `parse_diagnostics`: detectable structural warnings/errors.

Large numeric arrays remain JSON in schema 2.0 because this keeps the first real-data audit inspectable. The API is isolated behind `DesignRecord` and the serialization module so an NPZ or Parquet array store can be added without changing extraction semantics.

## Dataset artifacts

The builder writes:

- `manifest.jsonl` and an inspectable `manifest.json` summary;
- one cached record JSON per source;
- `splits/train.jsonl`, `validation.jsonl`, and `test.jsonl`;
- deterministic PNG previews where DST paths exist;
- `failed.jsonl` for per-file parse failures;
- `validation.json` and `validation.md`;
- `build_report.json` with run-specific built/reused/failure counts.

JSON readers and writers reject non-standard `NaN` and infinity values. Validation checks deterministic identities, safe relative paths, finite and internally consistent geometry, command/count consistency, lineage, declared preview files, duplicate records, complete split membership, and original-family leakage.

Data artifacts are deterministically ordered. Cache and preview names use stable source-path hashes, so changing a source atomically replaces that source's derived artifacts. Cached records are reused only when the content hash, schema, build-pipeline version, lineage, pair metadata, renderer configuration, and canonical validation all match. Ambiguous suffix matches in lineage or pair metadata are errors rather than silent fallbacks; a uniquely prefixed original reference is reconciled to the discovered source path while retaining the reported path as provenance.
