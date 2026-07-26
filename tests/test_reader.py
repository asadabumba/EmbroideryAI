from pathlib import Path
from src.emb_reader import EmbReader


emb_path = Path(
    r"C:\Users\SA88\EmbroideryAI\dataset\samples\Ghost\Hatch_Halloween-Quilt - Ghost.EMB"
)


reader = EmbReader(emb_path)


print("=== STREAMS ===")

streams = reader.list_streams()

for stream in streams:
    print(stream)


print("\n=== METADATA ===")

print(reader.get_metadata())


print("\n=== EXPORT ALL ===")

files = reader.export_all(
    "export_test"
)

print("Созданные файлы:")

for name, path in files.items():
    print(name, "->", path)


print("Готово!")