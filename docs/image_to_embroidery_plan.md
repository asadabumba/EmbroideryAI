# Practical image-to-embroidery research plan

The eventual system should be a staged planner, not a single opaque image-to-EMB network. Each stage can be evaluated against embroidery constraints before a backend compiles the result.

## 1. Image geometry

Input cleanup, foreground segmentation, region boundaries, centerlines, and scale estimation produce a layered geometric scene. Raster/vector artwork with manually corrected regions is the right first supervision source.

Current Stage 2 supervision: deterministic stitch previews can supply an image paired with a normalized DST trajectory, but they do not identify artwork regions or object boundaries.

Extra data needed: source artwork, physical target dimensions, foreground masks, region polygons, holes, centerlines, and registration between artwork and embroidery.

## 2. Embroidery object planning

Convert visual regions into embroidery objects and choose whether each becomes a run, satin column, fill region, appliqué, or is omitted. Preserve overlaps and intended visual hierarchy.

Current supervision: none. DST is a flattened machine sequence and the current EMB parser does not expose Wilcom objects.

Extra labels: object boundaries, object class, overlap/depth order, maximum satin width decisions, and operator corrections from native design files or an export API.

## 3. Stitch parameters

For every object choose fill direction, density/spacing, stitch length limits, edge travel, underlay, compensation, tie-in/tie-off, and thread/color assignment. These should be explicit constrained predictions so operator policy and machine/fabric profiles can modify them.

Current supervision: DST trajectories provide realized movement and coarse color blocks. DDD provides some design-level scalar totals. Neither proves object-level density, underlay, or compensation.

Extra labels: per-object stitch type, angles, density, underlay recipe, compensation, fabric/stabilizer, needle/thread specifications, machine profile, and quality outcome.

## 4. Sewing sequence planning

Order objects and color blocks to control registration, travel, trims, color changes, push/pull effects, and hoop stability. Model this as constrained graph ordering before generating individual stitches.

Current supervision: DST command order, jumps, and color-change boundaries can supervise flattened sequence statistics. Explicit trims are not reliably decoded by the current DST parser.

Extra labels: mapping from commands back to objects, explicit trim/tie events, intentional versus incidental travel, operator sequence edits, and failure annotations.

## 5. Stitch trajectory generation

Generate bounded-length trajectories for each planned object, then combine them with travel commands. Begin with deterministic geometry algorithms and use learned residuals only where data demonstrates value. Enforce machine limits during decoding.

Current supervision: normalized DST stitch trajectories, deltas, movement statistics, and command events can supervise trajectory reconstruction and sequence checks. Grouped splitting prevents translated copies of one design from leaking between evaluation partitions.

Extra labels: object-to-stitch alignment and the planning parameters from stages 2–4. Without them, a model can imitate flattened paths but cannot learn controllable digitizing intent.

## 6. Validation and compilation

Run structural checks, path-length and jump limits, collision/registration heuristics, density heatmaps, thread-change checks, and a machine-profile simulator. A reviewed plan then goes to Wilcom or another supported backend for compilation. Stage 2 does not generate or reverse-engineer EMB output.

Production validation eventually needs sew-out photographs, fabric/stabilizer/thread context, machine logs, breakage and puckering annotations, dimensional deviation, and expert accept/reject or correction data.

## Recommended experiment order

1. Validate paired EMB/DST extraction and lineage on a small real sample.
2. Establish normalized-trajectory reconstruction and deterministic renderer checks.
3. Collect artwork-to-object labels and train/evaluate segmentation separately.
4. Export object-level native labels before attempting stitch-type or density prediction.
5. Build deterministic object-to-stitch baselines, then compare learned components against them.
6. Add sequence planning with hard constraints and grouped, family-level evaluation.
7. Run controlled sew-out evaluation before any production claim.

Metrics should be stage-specific: region IoU/boundary distance, object classification, parameter error, sequence constraint violations, trajectory distance after alignment, jump/trim/color counts, simulated density, and blinded sew-out quality. Pixel similarity to a preview is not a sufficient production metric.
