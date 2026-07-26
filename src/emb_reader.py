from pathlib import Path
import json
import olefile
import zlib


class EmbReader:
    def __init__(self, emb_path):
        self.emb_path = Path(emb_path)

        if not self.emb_path.exists():
            raise FileNotFoundError(self.emb_path)

    def extract_stream(self, stream_name):
        """
        Извлекает поток из OLE-контейнера EMB
        """

        with olefile.OleFileIO(self.emb_path) as ole:
            data = ole.openstream(stream_name).read()

        return data

    def list_streams(self):
        """
        Возвращает список потоков внутри EMB-файла
        """

        with olefile.OleFileIO(self.emb_path) as ole:
            streams = ole.listdir()

        return streams

    def has_stream(self, stream_name):
        """
        Проверяет наличие потока внутри EMB
        """

        streams = self.list_streams()

        return any(
            item[-1] == stream_name
            for item in streams
        )

    def get_metadata(self):
        """
        Возвращает базовую информацию об EMB
        """

        streams = self.list_streams()

        return {
            "filename": self.emb_path.name,
            "size_bytes": self.emb_path.stat().st_size,
            "streams": [
                item[-1] for item in streams
            ]
        }

    def extract_preview(self, output_path):
        """
        Извлекает TRUEVIEW_ICON и сохраняет JPEG
        """

        compressed = self.extract_stream("TRUEVIEW_ICON")

        # Первые 4 байта служебные
        jpeg_data = zlib.decompress(compressed[4:])

        output_path = Path(output_path)
        output_path.write_bytes(jpeg_data)

        return output_path

    def extract_icon(self, output_path):
        """
        Извлекает DESIGN_ICON и сохраняет BMP
        """

        compressed = self.extract_stream("DESIGN_ICON")

        # Первые 4 байта служебные
        bmp_data = zlib.decompress(compressed[4:])

        output_path = Path(output_path)
        output_path.write_bytes(bmp_data)

        return output_path

    def export_all(self, output_dir):
        """
        Экспортирует метаданные, превью и иконку
        """

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        result = {}

        # Сохраняем метаданные
        metadata = self.get_metadata()
        metadata_path = output_dir / "metadata.json"

        metadata_path.write_text(
            json.dumps(
                metadata,
                indent=4,
                ensure_ascii=False
            ),
            encoding="utf-8"
        )

        result["metadata"] = metadata_path

        # Сохраняем превью
        if self.has_stream("TRUEVIEW_ICON"):
            preview_path = output_dir / "preview.jpg"
            self.extract_preview(preview_path)
            result["preview"] = preview_path

        # Сохраняем маленькую иконку
        if self.has_stream("DESIGN_ICON"):
            icon_path = output_dir / "icon.bmp"
            self.extract_icon(icon_path)
            result["icon"] = icon_path

        return result