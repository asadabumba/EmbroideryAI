from pathlib import Path
import json

from src.ddd_parser import DDDParser


BASE_DIR = Path(__file__).resolve().parent.parent

FILES = [
    BASE_DIR
    / "dataset"
    / "raw"
    / "1 Kareta-последний вариант.EMB",

    BASE_DIR
    / "dataset"
    / "raw"
    / "1.F-BEGEMOTI.EMB",
]


for emb_path in FILES:

    print("\n" + "=" * 60)

    try:
        parser = DDDParser(emb_path)
        metadata = parser.parse()

        print(
            json.dumps(
                metadata,
                ensure_ascii=False,
                indent=2
            )
        )

    except Exception as error:
        print(
            emb_path.name,
            "Ошибка:",
            error
        )