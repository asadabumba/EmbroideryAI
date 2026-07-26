from pathlib import Path
import olefile
import zlib


class EmbReader:
    def __init__(self, emb_path):
        self.emb_path = Path(emb_path)

        if not self.emb_path.exists():
            raise FileNotFoundError(self.emb_path)

    def extract_stream(self, stream_name):
        """
        Извлечение потока из OLE контейнера EMB
        """
        ole = olefile.OleFileIO(self.emb_path)

        try:
            data = ole.openstream(stream_name).read()
        finally:
            ole.close()

        return data

    def list_streams(self):
        """
        Возвращает список потоков внутри EMB файла
        """

        ole = olefile.OleFileIO(self.emb_path)

        try:
            streams = ole.listdir()
        finally:
            ole.close()

        return streams

    def get_metadata(self):
        """
        Возвращает базовую информацию о EMB
        """

        streams = self.list_streams()

        return {
            "filename": self.emb_path.name,
            "size_bytes": self.emb_path.stat().st_size,
            "streams": [
                item[0] for item in streams
            ]
        }

    def extract_preview(self, output_path):
        """
        Извлекает TRUEVIEW_ICON и сохраняет JPEG
        """

        compressed = self.extract_stream("TRUEVIEW_ICON")

        # первые 4 байта - служебные
        jpeg_data = zlib.decompress(compressed[4:])

        output_path = Path(output_path)
        output_path.write_bytes(jpeg_data)

        return output_path