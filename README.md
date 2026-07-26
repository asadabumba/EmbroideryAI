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