from pathlib import Path
import struct
import zlib

from src.emb_reader import EmbReader
from src.contents_parser import ContentsParser


BASE_DIR = Path(__file__).resolve().parent.parent

FILES = [
    BASE_DIR / "dataset" / "raw" / "1 Kareta-последний вариант.EMB",
    BASE_DIR / "dataset" / "raw" / "1.F-BEGEMOTI.EMB",
]

SIGNATURE = struct.pack(
    "<III",
    16508,
    0x60000,
    4
)

COMPARE_FROM = 12

all_records = []
raw_blocks = []
contents_list = []
starts = []


for emb_path in FILES:

    print(f"\n{emb_path.name}")

    if not emb_path.exists():
        print("Файл не найден:", emb_path)
        continue

    reader = EmbReader(emb_path)

    packed = reader.extract_stream("Contents")

    if packed is None:
        print("Поток Contents не найден")
        continue

    try:
        data = zlib.decompress(
            packed[4:]
        )

    except zlib.error as error:
        print("Ошибка распаковки:", error)
        continue

    start = data.find(SIGNATURE)

    print("Начало блока:", start)
    print("Размер Contents:", len(data))

    if start == -1:
        print("Сигнатура не найдена")
        continue

    contents_list.append(data)
    starts.append(start)
    raw_blocks.append(data[start:])

    parser = ContentsParser(data)

    records = parser.read_records(
        start,
        200
    )

    all_records.append(records)


if (
    len(all_records) < 2
    or len(raw_blocks) < 2
    or len(contents_list) < 2
):
    raise SystemExit(
        "\nНе удалось получить данные из двух файлов"
    )


def record_values(record):
    return (
        record["id"],
        record["type"],
        record["value"],
        record.get("payload")
    )


# Сравнение распарсенных записей

print("\nFIRST RECORD DIFFERENCE")

first_records = all_records[0]
second_records = all_records[1]

record_difference_found = False

for index, (first, second) in enumerate(
    zip(first_records, second_records)
):

    if record_values(first) != record_values(second):

        print("Номер записи:", index)
        print("Kareta:", first)
        print("Begemoti:", second)

        record_difference_found = True
        break


if not record_difference_found:

    if len(first_records) != len(second_records):
        print(
            "Количество записей отличается:",
            len(first_records),
            len(second_records)
        )

    else:
        print(
            "В прочитанных записях различий нет"
        )


# Сравнение служебного хвоста после сигнатуры

print("\nRAW FIRST DIFFERENCE")

first_block = raw_blocks[0]
second_block = raw_blocks[1]

print("Kareta bytes:", len(first_block))
print("Begemoti bytes:", len(second_block))

raw_difference_found = False

for offset, (first_byte, second_byte) in enumerate(
    zip(first_block, second_block)
):

    if first_byte != second_byte:

        print("Относительное смещение:", offset)
        print("Kareta byte:", first_byte)
        print("Begemoti byte:", second_byte)

        left = max(
            0,
            offset - 16
        )

        right = offset + 32

        print(
            "Kareta:",
            first_block[left:right].hex(" ")
        )

        print(
            "Begemoti:",
            second_block[left:right].hex(" ")
        )

        raw_difference_found = True
        break


if not raw_difference_found:

    if len(first_block) != len(second_block):
        print(
            "Совпадающая часть одинакова, "
            "но длины блоков отличаются"
        )

    else:
        print("Блоки полностью одинаковые")


# Сравнение данных до найденной сигнатуры

print("\nPREFIX FIRST DIFFERENCE")

first_prefix = contents_list[0][:starts[0]]
second_prefix = contents_list[1][:starts[1]]

print("Kareta prefix:", len(first_prefix))
print("Begemoti prefix:", len(second_prefix))
print("Сравнение начинается со смещения:", COMPARE_FROM)

prefix_difference_found = False

first_part = first_prefix[COMPARE_FROM:]
second_part = second_prefix[COMPARE_FROM:]

for relative_offset, (first_byte, second_byte) in enumerate(
    zip(first_part, second_part)
):

    if first_byte != second_byte:

        offset = COMPARE_FROM + relative_offset

        print("Первое различие:", offset)
        print("Kareta byte:", first_byte)
        print("Begemoti byte:", second_byte)

        left = max(
            0,
            offset - 16
        )

        right = offset + 32

        print(
            "Kareta:",
            first_prefix[left:right].hex(" ")
        )

        print(
            "Begemoti:",
            second_prefix[left:right].hex(" ")
        )

        prefix_difference_found = True
        break


if not prefix_difference_found:

    if len(first_prefix) != len(second_prefix):
        print(
            "Совпадающая часть префиксов одинакова, "
            "но их длины отличаются"
        )

    else:
        print("Префиксы полностью одинаковые")


print("\nHEADER UINT32 DIFFERENCES")

HEADER_SIZE = 200

for offset in range(12, HEADER_SIZE, 4):

    first_value = struct.unpack_from(
        "<I",
        contents_list[0],
        offset
    )[0]

    second_value = struct.unpack_from(
        "<I",
        contents_list[1],
        offset
    )[0]

    if first_value != second_value:
        print(
            offset,
            "| Kareta:",
            first_value,
            "| Begemoti:",
            second_value
        )

def read_text(data, length_offset):

    length = struct.unpack_from(
        "<I",
        data,
        length_offset
    )[0]

    raw = data[
        length_offset + 4:
        length_offset + 4 + length
    ]

    return raw.rstrip(b"\x00").decode(
        "ascii",
        errors="replace"
    )


print("\nMACHINE FORMAT")

print(
    "Kareta:",
    read_text(contents_list[0], 176)
)

print(
    "Begemoti:",
    read_text(contents_list[1], 176)
)