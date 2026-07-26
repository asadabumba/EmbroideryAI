from pathlib import Path
import olefile


file_path = Path(
    r"/dataset/samples/Ghost\Hatch_Halloween-Quilt - Ghost.EMB"
)

ole = olefile.OleFileIO(file_path)

for name in ["DESIGN_ICON", "TRUEVIEW_ICON"]:
    data = ole.openstream(name).read()

    out = Path(f"{name}.bin")
    out.write_bytes(data)

    print(name, len(data), "bytes saved")

ole.close()



# if not file_path.exists():
#     raise FileNotFoundError(f"Файл не найден: {file_path}")
#
# data = file_path.read_bytes()
#
# print(f"Файл: {file_path.name}")
# print(f"Размер: {len(data)} байт")
# print(f"Первые 64 байта:")
# print(data[:64])
# print()
# print("Первые 64 байта в HEX:")
# print(data[:64].hex(" "))