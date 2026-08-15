# Real data needed for Stage 2 validation

No raw EMB or DST file is present on this machine. The checked-in strict-pair manifest references files that are also absent.

The smallest useful validation package is ten original-design families. Ten groups are requested because the default 80/10/10 splitter can then place exactly 8/1/1 original groups while still exercising leakage checks.

Provide:

1. Ten original `.EMB` files, unchanged from the source corpus. Prefer a mix of stitch counts, dimensions, color counts, and at least one file with each commonly seen OLE preview stream.
2. The exact ten matching `.DST` exports, one per EMB, with filenames or a mapping that unambiguously identifies each pair.
3. For two of those originals, at least two translated `.EMB` variants each (four variants total), plus the actual batch-results CSV with these columns: `relative_source_file`, `relative_output_file`, `requested_x`, `requested_y`, `actual_x`, `actual_y`, `status`, `attempts`.
4. A strict-pair JSON containing rows for the supplied pairs, or the original `logs/emb_dst_ranking/ranking.json` used to produce the checked-in pair manifest.
5. A SHA-256 manifest for every supplied file and a short note stating the Wilcom/export version used. This is provenance, not a request for generated EMB files on this machine.

Preserve relative paths where practical:

```text
dataset/raw/<design>.EMB
archive/originals/dst/<design>.DST
<variant-root>/<family>/positioned_variants/<variant>.EMB
batch_results.csv
```

With that package, the next validation run can immediately check OLE/DDD extraction, DST trajectories, real preview rendering, EMB–DST pair evidence, deterministic IDs, grouped 8/1/1 splits, and translated-variant leakage. A larger corpus is not needed for the first validation pass.

Native object labels, source artwork, thread catalogs, fabric/stabilizer context, and sew-out outcomes are not required to validate the Stage 2 foundation. They will be required later to supervise object type, density, underlay, fill direction, compensation, and production quality.
