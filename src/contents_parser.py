import struct


class ContentsParser:

    def __init__(self, data):
        self.data = data

    def read_properties(self, start, count=20):

        properties = []

        pos = start

        for _ in range(count):

            prop_id = struct.unpack(
                "<I",
                self.data[pos:pos + 4]
            )[0]

            prop_type = struct.unpack(
                "<I",
                self.data[pos + 4:pos + 8]
            )[0]

            value = struct.unpack(
                "<I",
                self.data[pos + 8:pos + 12]
            )[0]

            if prop_id >= 16530:
                break

            properties.append({
                "id": prop_id,
                "type": prop_type,
                "value": value
            })

            pos += 12

        return properties

    def read_nested(self, start, count=10):

        result = []

        pos = start

        for _ in range(count):
            a = struct.unpack(
                "<I",
                self.data[pos:pos + 4]
            )[0]

            b = struct.unpack(
                "<I",
                self.data[pos + 4:pos + 8]
            )[0]

            c = struct.unpack(
                "<I",
                self.data[pos + 8:pos + 12]
            )[0]

            result.append({
                "a": a,
                "b": b,
                "c": c
            })

            pos += 12

        return result

    def read_links(self, start, count=10):

        links = []

        pos = start

        for _ in range(count):
            a = struct.unpack(
                "<I",
                self.data[pos:pos + 4]
            )[0]

            b = struct.unpack(
                "<I",
                self.data[pos + 4:pos + 8]
            )[0]

            c = struct.unpack(
                "<I",
                self.data[pos + 8:pos + 12]
            )[0]

            links.append({
                "source": a,
                "target": b,
                "type": c
            })

            pos += 12

        return links

    def read_raw_block(self, start, size=100):


        pos = start

        for i in range(size):
            value = struct.unpack(
                "<I",
                self.data[pos:pos + 4]
            )[0]

            print(
                pos,
                value
            )

            pos += 4

    def read_container(self, start, size=50):

        result = []

        pos = start

        for _ in range(size):
            a = struct.unpack(
                "<I",
                self.data[pos:pos + 4]
            )[0]

            b = struct.unpack(
                "<I",
                self.data[pos + 4:pos + 8]
            )[0]

            c = struct.unpack(
                "<I",
                self.data[pos + 8:pos + 12]
            )[0]

            result.append(
                {
                    "id": a,
                    "type": b,
                    "value": c
                }
            )

            pos += 12

        return result

    def read_child_properties(self, start, count=20):

        result = []

        pos = start

        for _ in range(count):
            prop_id = struct.unpack(
                "<I",
                self.data[pos:pos + 4]
            )[0]

            prop_type = struct.unpack(
                "<I",
                self.data[pos + 4:pos + 8]
            )[0]

            value = struct.unpack(
                "<I",
                self.data[pos + 8:pos + 12]
            )[0]

            result.append({
                "id": prop_id,
                "type": prop_type,
                "value": value
            })

            pos += 12

        return result

    def scan_block(self, start, count=30):

        pos = start

        for i in range(count):
            a = struct.unpack(
                "<I",
                self.data[pos:pos + 4]
            )[0]

            b = struct.unpack(
                "<I",
                self.data[pos + 4:pos + 8]
            )[0]

            c = struct.unpack(
                "<I",
                self.data[pos + 8:pos + 12]
            )[0]

            print(
                pos,
                "|",
                a,
                b,
                c
            )

            pos += 12

    def find_property(self, start, end):

        for pos in range(start, end, 4):

            a = struct.unpack(
                "<I",
                self.data[pos:pos + 4]
            )[0]

            b = struct.unpack(
                "<I",
                self.data[pos + 4:pos + 8]
            )[0]

            c = struct.unpack(
                "<I",
                self.data[pos + 8:pos + 12]
            )[0]

            if (
                    16000 < a < 20000
                    and b in [65536, 131072, 393216]
            ):
                print(
                    "Нашли свойство:",
                    pos,
                    a,
                    b,
                    c
                )

    def read_record(self, pos):

        if pos + 12 > len(self.data):
            raise ValueError("Недостаточно данных для чтения записи")

        prop_id, prop_type, value = struct.unpack_from(
            "<III",
            self.data,
            pos
        )

        record = {
            "offset": pos,
            "id": prop_id,
            "type": prop_type,
            "type_hex": hex(prop_type),
            "value": value
        }

        if prop_type == 0x60000:
            record["size"] = 12
            next_pos = pos + 12

        elif prop_type in (0x10000, 0x20000):

            if pos + 16 > len(self.data):
                raise ValueError("Недостаточно данных для payload")

            payload = struct.unpack_from(
                "<I",
                self.data,
                pos + 12
            )[0]

            record["payload"] = payload
            record["size"] = 16

            next_pos = pos + 16

        else:
            record["size"] = 12
            record["unknown_type"] = True

            next_pos = pos + 12

        return record, next_pos

    def read_records(self, start, count=20):

        records = []
        pos = start

        for _ in range(count):

            record, pos = self.read_record(pos)

            records.append(record)

            if record.get("unknown_type"):
                break

        return records
