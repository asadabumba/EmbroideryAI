from pathlib import Path
import struct

import olefile


class DDDParser:

    STREAM_NAME = "\x05WilcomDesignInformationDDD"

    PROPERTY_MAP = {
        "number of colours": "color_count",
        "number of stops": "stop_count",
        "number of trims": "trim_count",
        "number of stitches": "stitch_count",
        "number of objects": "object_count",
        "thread length": "thread_length",
        "bobbin length": "bobbin_length",
        "design left": "design_left",
        "design right": "design_right",
        "design up": "design_up",
        "design down": "design_down",
        "end x": "end_x",
        "end y": "end_y",
        "design height": "design_height",
        "design width": "design_width",
        "embroidery machine name": "machine",
        "number of funtions in the file": "function_count",
        "shortest stitch in design": "shortest_stitch",
        "longest stitch in design": "longest_stitch",
        "number of jumps per trim": "jumps_per_trim",
        "number of colour changes": "color_change_count",
        "filetype": "filetype",
        "fabricthickness": "fabric_thickness",
        "adjustbobbin": "adjust_bobbin",
    }

    SIGNED_FIELDS = {
        "design_left",
        "design_right",
        "design_up",
        "design_down",
        "end_x",
        "end_y",
    }

    def __init__(self, emb_path):
        self.emb_path = Path(emb_path)

    @staticmethod
    def _read_uint16(data, offset):
        return struct.unpack_from(
            "<H",
            data,
            offset
        )[0]

    @staticmethod
    def _read_uint32(data, offset):
        return struct.unpack_from(
            "<I",
            data,
            offset
        )[0]

    @staticmethod
    def _align_4(value):
        return (value + 3) & ~3

    @staticmethod
    def _to_signed32(value):

        if value is None:
            return None

        if not isinstance(value, int):
            return value

        if value >= 2 ** 31:
            return value - 2 ** 32

        return value

    @staticmethod
    def _decode_text(value):

        if value is None:
            return None

        if isinstance(value, str):
            return value.rstrip("\x00")

        if isinstance(value, bytes):

            for encoding in (
                "utf-8",
                "cp1251",
                "cp1252"
            ):
                try:
                    return value.decode(
                        encoding
                    ).rstrip("\x00")
                except UnicodeDecodeError:
                    continue

            return value.hex(" ")

        return value

    def _parse_property_names(self, data):

        if data[:2] != b"\xfe\xff":
            raise ValueError(
                "DDD использует неизвестный порядок байтов"
            )

        number_of_sections = self._read_uint32(
            data,
            24
        )

        if number_of_sections < 1:
            raise ValueError(
                "В DDD не найдены секции"
            )

        section_offset = self._read_uint32(
            data,
            44
        )

        property_count = self._read_uint32(
            data,
            section_offset + 4
        )

        property_offsets = {}

        table_offset = section_offset + 8

        for index in range(property_count):

            entry_offset = (
                table_offset
                + index * 8
            )

            property_id = self._read_uint32(
                data,
                entry_offset
            )

            relative_offset = self._read_uint32(
                data,
                entry_offset + 4
            )

            property_offsets[property_id] = (
                section_offset
                + relative_offset
            )

        codepage = 1252

        if 1 in property_offsets:

            codepage_offset = property_offsets[1]

            value_type = self._read_uint16(
                data,
                codepage_offset
            )

            if value_type in (2, 18):
                codepage = self._read_uint16(
                    data,
                    codepage_offset + 4
                )

        if 0 not in property_offsets:
            return {}

        dictionary_offset = property_offsets[0]

        number_of_entries = self._read_uint32(
            data,
            dictionary_offset
        )

        position = dictionary_offset + 4
        names = {}

        for _ in range(number_of_entries):

            if position + 8 > len(data):
                raise ValueError(
                    "Словарь DDD выходит за границы потока"
                )

            property_id = self._read_uint32(
                data,
                position
            )

            name_length = self._read_uint32(
                data,
                position + 4
            )

            position += 8

            if codepage == 1200:
                byte_length = name_length * 2
                encoding = "utf-16le"
            else:
                byte_length = name_length
                encoding = f"cp{codepage}"

            if position + byte_length > len(data):
                raise ValueError(
                    f"Название свойства {property_id} "
                    f"выходит за границы DDD"
                )

            raw_name = data[
                position:
                position + byte_length
            ]

            try:
                name = raw_name.decode(
                    encoding,
                    errors="replace"
                )
            except LookupError:
                name = raw_name.decode(
                    "cp1251",
                    errors="replace"
                )

            names[property_id] = (
                name.rstrip("\x00")
            )

            if codepage == 1200:
                position += self._align_4(
                    byte_length
                )
            else:
                position += byte_length

        return names

    def parse(self):

        if not self.emb_path.exists():
            raise FileNotFoundError(
                f"EMB-файл не найден: {self.emb_path}"
            )

        with olefile.OleFileIO(
            str(self.emb_path)
        ) as ole:

            if not ole.exists(
                self.STREAM_NAME
            ):
                raise ValueError(
                    "Поток WilcomDesignInformationDDD "
                    "не найден"
                )

            raw_data = ole.openstream(
                self.STREAM_NAME
            ).read()

            properties = ole.getproperties(
                self.STREAM_NAME
            )

        property_names = (
            self._parse_property_names(
                raw_data
            )
        )

        metadata: dict[str, object] = {
            "filename": self.emb_path.name
        }

        for property_id, value in properties.items():

            property_name = property_names.get(
                property_id
            )

            if property_name not in self.PROPERTY_MAP:
                continue

            result_name = self.PROPERTY_MAP[
                property_name
            ]

            if result_name == "machine":
                value = self._decode_text(value)

            if result_name in self.SIGNED_FIELDS:
                value = self._to_signed32(value)

            metadata[result_name] = value

        sequence_list = properties.get(18)

        if isinstance(
            sequence_list,
            (bytes, str)
        ):
            metadata["sequence_list_size"] = len(
                sequence_list
            )

        return metadata