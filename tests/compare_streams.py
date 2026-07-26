from pathlib import Path
import hashlib

import olefile


BASE_DIR = Path(__file__).resolve().parent.parent

FILES = [
    BASE_DIR / "dataset" / "raw" / "1 Kareta-последний вариант.EMB",
    BASE_DIR / "dataset" / "raw" / "1.F-BEGEMOTI.EMB",
]


def read_streams(emb_path):

    streams = {}

    with olefile.OleFileIO(emb_path) as ole:

        for stream_parts in ole.listdir(
            streams=True,
            storages=False
        ):
            stream_name = "/".join(stream_parts)

            data = ole.openstream(
                stream_parts
            ).read()

            streams[stream_name] = {
                "size": len(data),
                "hash": hashlib.sha256(data).hexdigest()
            }

    return streams


first_streams = read_streams(FILES[0])
second_streams = read_streams(FILES[1])

all_names = sorted(
    set(first_streams) | set(second_streams)
)


print("\nSTREAM COMPARISON")

for name in all_names:

    first = first_streams.get(name)
    second = second_streams.get(name)

    print(f"\n{name}")

    if first is None:
        print("Kareta: отсутствует")
        print("Begemoti:", second["size"], "байт")
        continue

    if second is None:
        print("Kareta:", first["size"], "байт")
        print("Begemoti: отсутствует")
        continue

    same = first["hash"] == second["hash"]

    print("Kareta:", first["size"], "байт")
    print("Begemoti:", second["size"], "байт")
    print("Одинаковые:", same)