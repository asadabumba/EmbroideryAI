# EmbroideryAI

Python toolkit for parsing and analyzing Wilcom `.EMB` embroidery files.

## About

EmbroideryAI is a Python project focused on reverse engineering and analysis of Wilcom embroidery files.

The project extracts and parses internal OLE streams from `.EMB` containers, including design metadata, binary structures and embroidery information.

The main goal is to build tools for automatic embroidery file analysis and prepare data for future ML/CV applications.

## Features

- OLE container reader for EMB files
- Internal stream extraction
- WilcomDesignInformationDDD parser
- Contents binary parser
- EMB metadata extraction
- Dataset builder
- Design information analysis

## Supported data

Currently extracted:

- Design information
- Stitch count
- Object count
- Color count
- Stop count
- Trim count
- Machine format
- Thread information
- File properties
- Design dimensions
- Sequence information

## Project structure

```text
EmbroideryAI/
│
├── src/
│   ├── emb_reader.py
│   ├── ddd_parser.py
│   ├── contents_parser.py
│   └── build_dataset.py
│
├── tests/
│   ├── test_parser.py
│   ├── test_ddd_parser.py
│   ├── compare_records.py
│   └── compare_streams.py
│
├── requirements.txt
└── README.md
```

## Installation

Clone the repository:

```bash
git clone https://github.com/asadabumba/EmbroideryAI.git

cd EmbroideryAI
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

### Extract EMB metadata

```python
from src.emb_reader import EmbReader

reader = EmbReader("design.EMB")

metadata = reader.get_metadata()

print(metadata)
```

### Build dataset

Place your `.EMB` files into:

```text
dataset/raw/
```

Run:

```bash
python src/build_dataset.py
```

The extracted information will be saved into:

```text
dataset/processed/
```

### Build the Stage 2 ML dataset

The Stage 2 builder supports `.DST` trajectories and metadata-only `.EMB` records, keeps translated variants and paired formats in one source-design split, renders deterministic headless previews where trajectories exist, and logs per-file failures.

```powershell
python -m src.ml_dataset.builder dataset/raw dataset/stage2 `
  --lineage-csv path/to/batch_results.csv `
  --pair-metadata dataset/paired/strict_pairs.json `
  --train-ratio 0.8 --validation-ratio 0.1 --test-ratio 0.1
```

The metadata and ratio arguments may be omitted; the split defaults are 80/10/10. Outputs use inspectable strict JSON/JSONL plus PNG previews. See [the Stage 2 data model](docs/stage2_data_model.md), [real-data request](REAL_DATA_NEEDED.md), and [image-to-embroidery roadmap](docs/image_to_embroidery_plan.md).

Lightweight deterministic trajectory checks can be run after a manifest exists:

```powershell
python -m src.ml_dataset.baselines dataset/stage2/manifest.jsonl dataset/stage2/baselines.json
```

## Supported EMB streams

Currently analyzed streams:

- `WilcomDesignInformationDDD`
- `Contents`
- `DESIGN_ICON`
- `TRUEVIEW_ICON`

## Roadmap

### Completed

- [x] EMB OLE container reader
- [x] Stream extraction
- [x] Wilcom DDD metadata parser
- [x] Contents binary parser
- [x] Metadata extraction
- [x] Dataset builder

### Planned

- [ ] Stitch coordinate extraction
- [ ] Object reconstruction
- [ ] Embroidery visualization
- [ ] Automatic stitch sequence analysis
- [ ] Embroidery dataset generation
- [ ] ML/CV models

## Dataset

The repository does not include embroidery files.

Users should provide their own `.EMB` datasets.

Example:

```text
dataset/
│
├── raw/
│   ├── design_001.EMB
│   ├── design_002.EMB
│
└── processed/
    ├── metadata.json
    ├── ddd_metadata.json
    └── extracted_data/
```

## License

MIT License
