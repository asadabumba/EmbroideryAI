from collections import Counter
from typing import Any


class DSTParser:
    """
    Парсер Tajima DST.

    Структура файла:
    - первые 512 байт — текстовый заголовок;
    - далее команды по 3 байта;
    - одна координатная единица = 0.1 мм.
    """

    HEADER_SIZE = 512
    UNIT_MM = 0.1

    def __init__(self, data: bytes):
        if not isinstance(data, bytes):
            raise TypeError("data должен иметь тип bytes")

        if len(data) < self.HEADER_SIZE:
            raise ValueError(
                f"Файл слишком маленький: {len(data)} байт"
            )

        self.data = data

    @staticmethod
    def _get_bit(value: int, position: int) -> int:
        """Возвращает один бит из числа."""
        return (value >> position) & 1

    def read_header(self) -> dict[str, Any]:
        """
        Читает текстовый DST-заголовок.

        Пример результата:
        {
            "LA": "ROSE",
            "ST": 8890,
            "CO": 0,
            "+X": 500,
            "-X": 499
        }
        """

        raw_header = self.data[:self.HEADER_SIZE]

        result: dict[str, Any] = {}

        for raw_line in raw_header.split(b"\r"):
            line = (
                raw_line
                .decode("ascii", errors="ignore")
                .replace("\x00", "")
                .replace("\x1a", "")
                .strip()
            )

            if ":" not in line:
                continue

            key, value = line.split(":", maxsplit=1)

            key = key.strip()
            value = value.strip()

            if not key:
                continue

            compact_value = "".join(
                value.split()
            )

            try:
                result[key] = int(
                    compact_value
                )
            except ValueError:
                result[key] = value

        return result

    def read_commands(self) -> bytes:
        """Возвращает бинарный блок команд после заголовка."""
        return self.data[self.HEADER_SIZE:]

    def decode_dx(self, b0: int, b1: int, b2: int) -> int:
        """
        Декодирует относительное смещение по X.

        DST использует веса:
        ±1, ±3, ±9, ±27, ±81.
        """

        x = 0

        x += self._get_bit(b2, 2) * 81
        x -= self._get_bit(b2, 3) * 81

        x += self._get_bit(b1, 2) * 27
        x -= self._get_bit(b1, 3) * 27

        x += self._get_bit(b0, 2) * 9
        x -= self._get_bit(b0, 3) * 9

        x += self._get_bit(b1, 0) * 3
        x -= self._get_bit(b1, 1) * 3

        x += self._get_bit(b0, 0)
        x -= self._get_bit(b0, 1)

        return x

    def decode_dy(self, b0: int, b1: int, b2: int) -> int:
        """
        Декодирует относительное смещение по Y.

        Здесь сохраняем обычную декартову систему:
        положительный Y направлен вверх.
        """

        y = 0

        y += self._get_bit(b2, 5) * 81
        y -= self._get_bit(b2, 4) * 81

        y += self._get_bit(b1, 5) * 27
        y -= self._get_bit(b1, 4) * 27

        y += self._get_bit(b0, 5) * 9
        y -= self._get_bit(b0, 4) * 9

        y += self._get_bit(b1, 7) * 3
        y -= self._get_bit(b1, 6) * 3

        y += self._get_bit(b0, 7)
        y -= self._get_bit(b0, 6)

        return y

    @staticmethod
    def command_type(b2: int) -> str:
        """
        Определяет тип DST-команды.

        Порядок проверок важен:
        END также содержит биты других команд.
        """

        if b2 & 0xF3 == 0xF3:
            return "end"

        if b2 & 0xC3 == 0xC3:
            return "color_change"

        if b2 & 0x43 == 0x43:
            return "sequin_mode"

        if b2 & 0x83 == 0x83:
            return "jump"

        return "stitch"

    def decode_command(
        self,
        command: bytes,
        index: int = 0
    ) -> dict[str, Any]:
        """Декодирует одну трёхбайтовую DST-команду."""

        if len(command) != 3:
            raise ValueError(
                "DST-команда должна содержать ровно 3 байта"
            )

        b0, b1, b2 = command

        return {
            "index": index,
            "offset": self.HEADER_SIZE + index * 3,
            "raw": command.hex(" "),
            "dx": self.decode_dx(b0, b1, b2),
            "dy": self.decode_dy(b0, b1, b2),
            "type": self.command_type(b2),
        }

    def parse(self) -> list[dict[str, Any]]:
        """
        Разбирает команды и переводит относительные смещения
        dx/dy в абсолютные координаты x/y.
        """

        raw_commands = self.read_commands()

        result: list[dict[str, Any]] = []

        current_x = 0
        current_y = 0

        sequin_mode_active = False

        command_index = 0

        for offset in range(0, len(raw_commands) - 2, 3):
            raw_command = raw_commands[offset:offset + 3]

            command = self.decode_command(
                raw_command,
                command_index
            )

            if command["type"] == "sequin_mode":
                sequin_mode_active = not sequin_mode_active

            elif (
                    command["type"] == "jump"
                    and sequin_mode_active
            ):
                command["type"] = "sequin_eject"

            current_x += command["dx"]
            current_y += command["dy"]

            command["x"] = current_x
            command["y"] = current_y
            command["x_mm"] = round(
                current_x * self.UNIT_MM,
                1
            )
            command["y_mm"] = round(
                current_y * self.UNIT_MM,
                1
            )

            result.append(command)

            command_index += 1

            if command["type"] == "end":
                break

        return result

    @staticmethod
    def get_bounds(
        commands: list[dict[str, Any]]
    ) -> dict[str, int]:
        """Возвращает границы абсолютных координат."""

        movement_commands = [
            command
            for command in commands
            if command["type"] != "end"
        ]

        if not movement_commands:
            return {
                "min_x": 0,
                "max_x": 0,
                "min_y": 0,
                "max_y": 0,
                "width": 0,
                "height": 0,
            }

        x_values = [
            0,
            *[
                command["x"]
                for command in movement_commands
            ]
        ]

        y_values = [
            0,
            *[
                command["y"]
                for command in movement_commands
            ]
        ]

        min_x = min(x_values)
        max_x = max(x_values)
        min_y = min(y_values)
        max_y = max(y_values)

        return {
            "min_x": min_x,
            "max_x": max_x,
            "min_y": min_y,
            "max_y": max_y,
            "width": max_x - min_x,
            "height": max_y - min_y,
        }

    @staticmethod
    def count_types(
        commands: list[dict[str, Any]]
    ) -> dict[str, int]:
        """Считает количество команд каждого типа."""

        counter = Counter(
            command["type"]
            for command in commands
        )

        return dict(counter)