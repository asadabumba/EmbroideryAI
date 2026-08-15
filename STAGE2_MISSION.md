# EMBROIDERYAI — STAGE 2 ML DATASET MISSION

You are working on the SECOND independent EmbroideryAI development machine.

Repository:
C:\Users\LiL_Onik$\EmbroideryAI-Stage2

Branch:
codex-stage2-ml-dataset

Baseline:
12e7398

This branch is intentionally independent from another machine that is
currently improving Wilcom GUI automation and generating positioned EMB files.

============================================================
PRIMARY GOAL
============================================================

Build the ML data layer that will eventually support:

IMAGE
-> embroidery structure
-> digitizing decisions
-> stitch plan
-> Wilcom/backend
-> production EMB

This machine is NOT responsible for Wilcom GUI automation.

Do not install Wilcom.
Do not attempt to generate EMB files.
Do not reverse engineer EMB writing.

The immediate goal is to turn existing embroidery files and metadata into
a clean, validated, machine-learning-ready representation.

============================================================
FIRST: UNDERSTAND THE EXISTING PROJECT
============================================================

Before changing code, inspect:

src/emb_reader.py
src/dst_parser.py
src/ddd_parser.py
src/contents_parser.py
src/build_dataset.py
src/generated_dataset.py
src/export_stricts_pairs.py
dataset/paired/strict_pairs.json
tests/
audit/

Run the existing relevant tests.

Do not replace working parsers without evidence that they are inadequate.

Document what information can ACTUALLY be extracted today from:

- EMB
- DST
- DDD
- existing pair metadata

Separate:

1. directly observed/extracted fields
2. derived fields
3. fields unavailable with current files/parsers

Never invent embroidery metadata.

============================================================
CANONICAL DATA MODEL
============================================================

Design and implement a canonical per-design representation.

Where available, represent:

identity:
- design_id
- source_design_id
- source_path
- format
- content hash

geometry:
- width
- height
- bounding box
- center
- absolute stitch coordinates
- normalized stitch coordinates
- per-stitch dx/dy
- total path length

stitch information:
- stitch count
- jump count
- trim count
- color-change count
- command/event sequence
- segmentation into color blocks where possible

color/thread:
- color sequence
- thread information when actually available

augmentation lineage:
- original source design
- x translation
- y translation
- other augmentation metadata in future

statistics:
- min/max/mean stitch length
- quantiles
- movement statistics
- command frequencies

rendering:
- deterministic preview rendering from stitch paths where possible
- configurable output resolution
- stable coordinate normalization

Do not claim unavailable EMB object-level properties such as satin/tatami,
density, underlay or pull compensation unless they can actually be extracted.

============================================================
IMPORTANT: ORIGINAL DESIGN GROUPING
============================================================

The current project creates many translated versions of the SAME original
design.

These are NOT independent designs.

Example:

Ghost original
Ghost x=-10 y=-10
Ghost x=-10 y=-5
...
Ghost x=10 y=10

ALL variants belonging to the same original design MUST remain in the same
train/validation/test partition.

Otherwise there will be catastrophic dataset leakage.

Implement split logic by source_design_id / original-design group.

Never split individual augmented variants independently.

============================================================
TRAIN / VALIDATION / TEST
============================================================

Implement deterministic grouped splitting.

Target defaults:

train 80%
validation 10%
test 10%

Requirements:

- deterministic seed
- split at ORIGINAL DESIGN level
- all variants inherit original's split
- no source_design_id overlap between splits
- validator that explicitly detects leakage
- useful statistics for each split

============================================================
OUTPUT FORMAT
============================================================

Do not prematurely lock the whole project to one storage format.

Create a clean schema and serialization layer.

Use simple inspectable representations first, such as:

JSON / JSONL for metadata

and appropriate numerical storage for large stitch arrays if justified.

Keep the API format-independent enough that Parquet/NPZ can be added later.

============================================================
PREVIEW RENDERING
============================================================

Implement a deterministic renderer using parsed stitch paths when possible.

Goals:

- convert embroidery sequence into image
- preserve aspect ratio
- normalize translation
- optionally show different color blocks
- no requirement for Wilcom

This preview will later become one side of image/embroidery ML experiments.

Tests must not depend on a GUI.

============================================================
DATASET BUILDER
============================================================

Create a Stage 2 builder capable of:

input directory
-> discover supported embroidery files
-> parse
-> canonicalize
-> validate
-> assign lineage
-> render preview where possible
-> produce manifest
-> produce grouped split manifests
-> report errors without crashing entire corpus

Requirements:

- resumable
- deterministic
- failed files logged separately
- do not silently discard malformed data
- do not overwrite source files
- safe incremental rebuild
- hashes/identifiers stable across runs

============================================================
VALIDATOR
============================================================

Implement a validator that can detect at least:

- missing files
- duplicate design IDs
- duplicate source IDs when unexpected
- invalid coordinates
- NaN/inf
- impossible/empty stitch paths
- corrupt metadata
- train/val/test leakage
- augmentation lineage errors
- duplicate output records
- malformed command sequences when detectable

Produce a human-readable report and machine-readable summary.

============================================================
TESTING
============================================================

Add focused unit tests for:

- canonicalization
- coordinate normalization
- stitch deltas
- geometry/bounding box
- deterministic IDs
- grouped splitting
- leakage detection
- serialization round trip
- renderer
- malformed input handling
- resumability
- deterministic rebuild

Use existing real fixtures if present.

Synthetic tiny fixtures are acceptable for unit tests.

Never fabricate conclusions about the real 717-design corpus from synthetic
fixtures.

============================================================
REAL DATA AVAILABILITY
============================================================

The full raw corpus may NOT exist on this second machine yet.

This is not a blocker for implementing and testing the architecture.

If real raw files are unavailable:

1. finish the code that can be safely built without them
2. run unit tests
3. identify the SMALLEST useful real sample needed
4. write REAL_DATA_NEEDED.md containing exact file requirements
5. continue all work that does not depend on those files

Do NOT stop just because the 717 raw EMB files are not present.

Do NOT generate fake corpus statistics.

============================================================
FUTURE IMAGE -> EMBROIDERY RESEARCH
============================================================

Create:

docs/image_to_embroidery_plan.md

It should describe a practical staged ML architecture for eventually
turning an image into production embroidery.

Clearly distinguish what the current dataset can supervise from what it
cannot.

Consider stages such as:

image
-> segmentation / geometry
-> embroidery object planning
-> stitch-type decisions
-> fill direction / density decisions
-> sewing sequence planning
-> stitch trajectory
-> validation
-> Wilcom/backend compilation

For properties currently unavailable from the dataset, document what extra
labels/data will later be necessary.

Do not implement a huge neural network yet.

First build reliable data foundations.

============================================================
INITIAL EXPERIMENTS
============================================================

Once the data layer exists, create lightweight baseline experiments only
where the available data supports them.

Useful possibilities include:

- translation-invariant design representation
- reconstructing normalized stitch trajectories
- classifying transformed variants back to original design family
- simple sequence statistics baselines

Do NOT start expensive model training without a validated real dataset.

============================================================
CODE QUALITY
============================================================

Prefer:

src/ml_dataset/
or another clean dedicated package.

Keep responsibilities separated:

schema
parsing adapters
canonicalization
rendering
splitting
validation
building

Use type hints where useful.

Avoid giant monolithic scripts.

Do not duplicate existing parsers unnecessarily.

============================================================
FILES NOT TO TOUCH
============================================================

Do NOT modify Wilcom GUI automation unless absolutely required for an
interface definition:

tests/automate_wilcom_file.py
tests/automate_wilcom_batch.py
tests/automate_wilcom_grouped_file.py

Another machine owns that work.

Do not modify compare_shift_* research files unless the Stage 2 task
strictly requires reading them.

Do not merge the other Codex branch.

============================================================
GIT
============================================================

Work only on:

codex-stage2-ml-dataset

Make small coherent commits after tests pass.

Explicitly stage files.

Never use:

git add .
git clean
git reset --hard
git restore .
git checkout .

Do not force push.

Do not merge main.

Local commits are encouraged.

Do not push unless needed; the user can push reviewed work later.

============================================================
STATUS
============================================================

Maintain:

STAGE2_STATUS.md

Include:

- current stage
- completed components
- tests passing/failing
- real files available
- real files still needed
- schema version
- next work
- latest commit

Update it at meaningful milestones.

============================================================
DEFINITION OF STAGE 2 SUCCESS
============================================================

Stage 2 foundation is successful when:

- existing parsers were audited
- canonical schema exists
- dataset builder exists
- grouped split system exists
- leakage validator exists
- preview renderer exists where stitch data permits
- validators exist
- unit tests pass
- documentation explains actual supported fields
- image-to-embroidery roadmap exists
- real-data validation can be performed immediately after sample files arrive

If real data is available, validate on it.

If real data is unavailable, state exactly what sample is needed.

============================================================
AUTONOMY
============================================================

Work autonomously.

Do not ask the user routine implementation questions.

Inspect the repository and make sensible engineering choices.

Do not stop after merely writing a plan.

Implement, test, review, improve, document and commit usable Stage 2 code.

Do not claim results that were not actually tested.
