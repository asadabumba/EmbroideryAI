from pathlib import Path

from src.dst_parser import DSTParser


BASE_DIR = Path(__file__).resolve().parent.parent

dst_path = (
    BASE_DIR
    / "archive"
    / "originals"
    / "dst"
    / "rose.dst"
)


print("Файл:")
print(dst_path)


if not dst_path.exists():
    raise FileNotFoundError(
        f"Файл не найден: {dst_path}"
    )


data = dst_path.read_bytes()

parser = DSTParser(data)


print("\nРазмер файла:")
print(len(data), "байт")


header = parser.read_header()

print("\nHEADER:")

for key, value in header.items():
    print(f"{key}: {value}")


commands = parser.parse()

print("\nКоличество разобранных команд:")
print(len(commands))


print("\nПервые 20 команд:")

for command in commands[:20]:
    print(command)


print("\nКоличество команд по типам:")

types = parser.count_types(commands)

for command_type, count in types.items():
    print(f"{command_type}: {count}")


bounds = parser.get_bounds(commands)

print("\nГраницы, рассчитанные по командам:")

for key, value in bounds.items():
    print(f"{key}: {value}")


print("\nГраницы из заголовка:")

for key in ["+X", "-X", "+Y", "-Y"]:
    print(f"{key}: {header.get(key)}")


print("\nРазмер дизайна:")

print(
    f"{bounds['width']} × {bounds['height']} единиц"
)

print(
    f"{bounds['width'] * 0.1:.1f} × "
    f"{bounds['height'] * 0.1:.1f} мм"
)