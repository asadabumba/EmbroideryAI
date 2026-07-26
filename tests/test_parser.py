from pathlib import Path
from src.emb_reader import EmbReader
from src.contents_parser import ContentsParser
import zlib


BASE_DIR = Path(__file__).resolve().parent.parent

emb_path = (
    BASE_DIR
    / "dataset"
    / "raw"
    / "1 Kareta-последний вариант.EMB"
)

reader = EmbReader(emb_path)

data = reader.extract_stream("Contents")
result = zlib.decompress(data[4:])

parser = ContentsParser(result)

print("\nRECORDS")

records = parser.read_records(
    20084,
    40
)

for record in records:
    print(record)