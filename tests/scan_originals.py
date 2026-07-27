from collections import defaultdict
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
ORIGINALS_DIR = BASE_DIR / "archive" / "originals"

formats = [
    "emb",
    "dst",
    "pes",
    "exp",
    "eof",
    "edr",
]

files_by_stem = defaultdict(dict)


for extension in formats:

    folder = ORIGINALS_DIR / extension

    if not folder.exists():
        print(f"{extension.upper()}: папка не найдена")
        continue

    files = [
        path
        for path in folder.rglob("*")
        if path.is_file()
    ]

    print(
        f"{extension.upper()}: {len(files)} файлов"
    )

    for path in files:

        stem = path.stem.strip().lower()

        files_by_stem[stem][extension] = path


print("\nОДИНАКОВЫЕ ДИЗАЙНЫ В РАЗНЫХ ФОРМАТАХ")

matches = []

for stem, versions in files_by_stem.items():

    if len(versions) < 2:
        continue

    matches.append(
        (stem, versions)
    )


matches.sort(
    key=lambda item: len(item[1]),
    reverse=True
)


for stem, versions in matches[:50]:

    print(f"\n{stem}")

    for extension, path in sorted(
        versions.items()
    ):
        print(
            f"  {extension.upper()}: "
            f"{path.name}"
        )


print("\nВсего совпадающих дизайнов:", len(matches))