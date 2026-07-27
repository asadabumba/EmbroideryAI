from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


dst = (
    BASE_DIR
    / "archive"
    / "originals"
    / "dst"
    / "rose.dst"
)


data = dst.read_bytes()


print("Размер:", len(data))


print("\nHEADER:")
print(
    data[:512].decode(
        "ascii",
        errors="replace"
    )
)


print("\nFIRST BYTES:")

for i in range(0, 100, 16):

    chunk = data[i:i+16]

    print(
        i,
        chunk.hex(" ")
    )