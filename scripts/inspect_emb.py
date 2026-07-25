from pathlib import Path

file_path = Path("dataset/Ghost/Hatch_Halloween-Quilt - Ghost.EMB")

data = file_path.read_bytes()

print("Размер:", len(data), "байт")
print("Первые 64 байта:")
print(data[:64].hex(" "))