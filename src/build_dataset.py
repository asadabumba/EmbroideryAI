from pathlib import Path
from src.emb_reader import EmbReader

BASE_DIR = Path(__file__).resolve().parent.parent

INPUT_DIR = BASE_DIR / "dataset" / "raw"

OUTPUT_DIR = BASE_DIR / "dataset" / "processed"

def build_dataset():

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    emb_files = list(
        INPUT_DIR.rglob("*.EMB")
    )

    print(
        f"Найдено файлов: {len(emb_files)}"
    )

    errors = []

    processed = 0

    for emb_path in emb_files:


        try:
            print("\nОбработка:", emb_path)

            reader = EmbReader(emb_path)

            output_folder = OUTPUT_DIR / emb_path.stem

            reader.export_all(output_folder)

            processed += 1

            print("Готово:", output_folder)

        except Exception as e:
            errors.append(
                f"{emb_path}: {e}"
            )

    if errors:
        (BASE_DIR / "logs").mkdir(
            exist_ok=True
        )

        (BASE_DIR / "logs" / "errors.txt").write_text(
            "\n".join(errors),
            encoding="utf-8"
        )

    print(f"Обработано: {processed}")
    print(f"Ошибок: {len(errors)}")

if __name__ == "__main__":
    build_dataset()