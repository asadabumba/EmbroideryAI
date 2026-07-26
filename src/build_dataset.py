import json
from pathlib import Path

from src.emb_reader import EmbReader
from src.ddd_parser import DDDParser


BASE_DIR = Path(__file__).resolve().parent.parent

INPUT_DIR = BASE_DIR / "dataset" / "raw"
OUTPUT_DIR = BASE_DIR / "dataset" / "processed"
LOGS_DIR = BASE_DIR / "logs"
ERRORS_FILE = LOGS_DIR / "errors.txt"


def build_dataset():

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    emb_files = sorted(
        INPUT_DIR.rglob("*.EMB")
    )

    print(
        f"Найдено файлов: {len(emb_files)}"
    )

    errors = []
    processed = 0

    for emb_path in emb_files:

        try:
            print(
                "\nОбработка:",
                emb_path
            )

            output_folder = (
                OUTPUT_DIR
                / emb_path.stem.strip()
            )

            output_folder.mkdir(
                parents=True,
                exist_ok=True
            )

            # Извлечение обычных данных EMB

            reader = EmbReader(
                emb_path
            )

            reader.export_all(
                output_folder
            )

            # Извлечение метаданных DDD


            if reader.has_stream(DDDParser.STREAM_NAME):

                ddd_parser = DDDParser(emb_path)
                ddd_metadata = ddd_parser.parse()

            else:

                ddd_metadata = {
                    "filename": emb_path.name,
                    "ddd_available": False,
                    "reason": "Поток WilcomDesignInformationDDD отсутствует"
                }

            ddd_path = output_folder / "ddd_metadata.json"

            ddd_path.write_text(
                json.dumps(
                    ddd_metadata,
                    ensure_ascii=False,
                    indent=2
                ),
                encoding="utf-8"
            )

            processed += 1

            print(
                "Готово:",
                output_folder
            )

        except Exception as error:

            error_message = (
                f"{emb_path}: "
                f"{type(error).__name__}: "
                f"{error}"
            )

            errors.append(
                error_message
            )

            print(
                "Ошибка:",
                error_message
            )

    LOGS_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    if errors:

        ERRORS_FILE.write_text(
            "\n".join(errors),
            encoding="utf-8"
        )

    elif ERRORS_FILE.exists():

        ERRORS_FILE.unlink()

    print("\n" + "=" * 50)
    print(f"Обработано: {processed}")
    print(f"Ошибок: {len(errors)}")
    print("=" * 50)


if __name__ == "__main__":
    build_dataset()