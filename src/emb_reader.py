import json
import zlib
from pathlib import Path

import olefile


class EmbReader:

    def __init__(self, emb_path):

        self.emb_path = Path(emb_path)

        if not self.emb_path.exists():
            raise FileNotFoundError(
                f"EMB-файл не найден: {self.emb_path}"
            )

        if not olefile.isOleFile(
            str(self.emb_path)
        ):
            raise ValueError(
                f"Файл не является OLE-контейнером: "
                f"{self.emb_path}"
            )

    def has_stream(self, stream_name):
        """
        Проверяет наличие потока внутри EMB.
        """

        with olefile.OleFileIO(
            str(self.emb_path)
        ) as ole:

            return ole.exists(
                stream_name
            )

    def extract_stream(self, stream_name):
        """
        Извлекает сырой поток из OLE-контейнера EMB.
        """

        with olefile.OleFileIO(
            str(self.emb_path)
        ) as ole:

            if not ole.exists(stream_name):
                raise ValueError(
                    f"Поток не найден: {stream_name}"
                )

            return ole.openstream(
                stream_name
            ).read()

    def list_streams(self):
        """
        Возвращает список потоков внутри EMB-файла.
        """

        with olefile.OleFileIO(
            str(self.emb_path)
        ) as ole:

            streams = ole.listdir(
                streams=True,
                storages=False
            )

        return [
            "/".join(stream_parts)
            for stream_parts in streams
        ]

    def get_metadata(self):
        """
        Возвращает базовую информацию об EMB-файле.
        """

        return {
            "filename": self.emb_path.name,
            "size_bytes": self.emb_path.stat().st_size,
            "streams": self.list_streams()
        }

    def extract_preview(self, output_path):
        """
        Извлекает TRUEVIEW_ICON и сохраняет JPEG.
        """

        if not self.has_stream(
            "TRUEVIEW_ICON"
        ):
            return None

        compressed = self.extract_stream(
            "TRUEVIEW_ICON"
        )

        if len(compressed) <= 4:
            raise ValueError(
                "Поток TRUEVIEW_ICON повреждён"
            )

        jpeg_data = zlib.decompress(
            compressed[4:]
        )

        output_path = Path(output_path)

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        output_path.write_bytes(
            jpeg_data
        )

        return output_path

    def extract_icon(self, output_path):
        """
        Извлекает DESIGN_ICON и сохраняет BMP.
        """

        if not self.has_stream(
            "DESIGN_ICON"
        ):
            return None

        compressed = self.extract_stream(
            "DESIGN_ICON"
        )

        if len(compressed) <= 4:
            raise ValueError(
                "Поток DESIGN_ICON повреждён"
            )

        bmp_data = zlib.decompress(
            compressed[4:]
        )

        output_path = Path(output_path)

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        output_path.write_bytes(
            bmp_data
        )

        return output_path

    def export_metadata(self, output_path):
        """
        Сохраняет основные метаданные в JSON.
        """

        output_path = Path(output_path)

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        metadata = self.get_metadata()

        output_path.write_text(
            json.dumps(
                metadata,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

        return output_path

    def export_all(self, output_dir):
        """
        Извлекает все поддерживаемые данные из EMB.
        """

        output_dir = Path(output_dir)

        output_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        exported = {
            "metadata": None,
            "preview": None,
            "icon": None
        }

        metadata_path = (
            output_dir
            / "metadata.json"
        )

        self.export_metadata(
            metadata_path
        )

        exported["metadata"] = (
            metadata_path
        )

        if self.has_stream(
            "TRUEVIEW_ICON"
        ):
            exported["preview"] = (
                self.extract_preview(
                    output_dir
                    / "preview.jpg"
                )
            )

        if self.has_stream(
            "DESIGN_ICON"
        ):
            exported["icon"] = (
                self.extract_icon(
                    output_dir
                    / "icon.bmp"
                )
            )

        return exported