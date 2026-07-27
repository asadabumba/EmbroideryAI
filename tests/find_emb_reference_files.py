import re
import unicodedata
from collections import defaultdict
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

EMB_DIR = BASE_DIR / "dataset" / "raw"

REFERENCE_FOLDERS = {
    "dst": BASE_DIR / "archive" / "originals" / "dst",
    "edr": BASE_DIR / "archive" / "originals" / "edr",
    "eof": BASE_DIR / "archive" / "originals" / "eof",
    "pes": BASE_DIR / "archive" / "originals" / "pes",
    "exp": BASE_DIR / "archive" / "originals" / "exp",
}


def normalize_name(name: str) -> str:
    """
    Нормализует имя дизайна для сравнения:

    Rose-2.EMB
    rose_2.dst
    ROSE 2.eof

    превращаются в:

    rose2
    """

    value = unicodedata.normalize(
        "NFKD",
        name
    )

    value = value.casefold()
    value = value.replace("ё", "е")

    value = re.sub(
        r"[^a-zа-я0-9]+",
        "",
        value
    )

    return value


def relaxed_name(name: str) -> str:
    """
    Дополнительная нормализация.

    Удаляет цифры в начале имени:

    001rose -> rose
    12tiger -> tiger
    """

    value = normalize_name(name)

    value = re.sub(
        r"^\d+",
        "",
        value
    )

    return value


def collect_files(
    folder: Path,
    suffix: str
) -> list[Path]:

    if not folder.exists():
        print(f"Папка не найдена: {folder}")
        return []

    return sorted(
        path
        for path in folder.rglob("*")
        if path.is_file()
        and path.suffix.casefold() == suffix.casefold()
    )


def build_index(
    files: list[Path],
    relaxed: bool = False
) -> dict[str, list[Path]]:

    index = defaultdict(list)

    for path in files:

        if relaxed:
            key = relaxed_name(path.stem)
        else:
            key = normalize_name(path.stem)

        if key:
            index[key].append(path)

    return dict(index)


def print_matches(
    title: str,
    emb_index: dict[str, list[Path]],
    reference_indexes: dict[
        str,
        dict[str, list[Path]]
    ]
) -> int:

    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)

    match_count = 0

    for emb_name, emb_paths in sorted(
        emb_index.items()
    ):

        matched_formats = {}

        for format_name, format_index in (
            reference_indexes.items()
        ):
            if emb_name in format_index:
                matched_formats[format_name] = (
                    format_index[emb_name]
                )

        if not matched_formats:
            continue

        match_count += 1

        print(f"\nНормализованное имя: {emb_name}")

        for emb_path in emb_paths:
            print(
                "  EMB:",
                emb_path.relative_to(BASE_DIR)
            )

        for format_name, paths in (
            matched_formats.items()
        ):
            for path in paths:
                print(
                    f"  {format_name.upper()}:",
                    path.relative_to(BASE_DIR)
                )

    print("\nКоличество совпадений:", match_count)

    return match_count


def main():

    emb_files = collect_files(
        EMB_DIR,
        ".emb"
    )

    print("EMB файлов:", len(emb_files))

    reference_files = {}

    for format_name, folder in (
        REFERENCE_FOLDERS.items()
    ):

        files = collect_files(
            folder,
            f".{format_name}"
        )

        reference_files[format_name] = files

        print(
            f"{format_name.upper()} файлов:",
            len(files)
        )

    exact_emb_index = build_index(
        emb_files,
        relaxed=False
    )

    exact_reference_indexes = {
        format_name: build_index(
            files,
            relaxed=False
        )
        for format_name, files
        in reference_files.items()
    }

    exact_count = print_matches(
        "ТОЧНЫЕ СОВПАДЕНИЯ ПО ИМЕНИ",
        exact_emb_index,
        exact_reference_indexes
    )

    if exact_count == 0:

        relaxed_emb_index = build_index(
            emb_files,
            relaxed=True
        )

        relaxed_reference_indexes = {
            format_name: build_index(
                files,
                relaxed=True
            )
            for format_name, files
            in reference_files.items()
        }

        print_matches(
            "ПРИБЛИЗИТЕЛЬНЫЕ СОВПАДЕНИЯ",
            relaxed_emb_index,
            relaxed_reference_indexes
        )


if __name__ == "__main__":
    main()