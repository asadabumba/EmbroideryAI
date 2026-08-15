from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.ddd_parser import DDDParser
from src.dst_parser import DSTParser
from src.emb_reader import EmbReader


SUPPORTED_SUFFIXES = {".dst", ".emb"}


@dataclass
class ParsedSource:
    source_format: str
    observed_metadata: dict[str, Any]
    commands: list[dict[str, Any]] = field(default_factory=list)
    unit_mm: float = 1.0
    diagnostics: list[dict[str, Any]] = field(default_factory=list)


def parse_dst(path: Path) -> ParsedSource:
    data = path.read_bytes()
    parser = DSTParser(data)
    header = parser.read_header()
    commands = parser.parse()
    diagnostics: list[dict[str, Any]] = []
    command_bytes = data[DSTParser.HEADER_SIZE :]
    if len(command_bytes) % 3:
        diagnostics.append(
            {
                "severity": "error",
                "code": "trailing_command_bytes",
                "message": f"DST command block has {len(command_bytes) % 3} trailing byte(s)",
            }
        )
    if not commands or commands[-1].get("type") != "end":
        diagnostics.append(
            {
                "severity": "error",
                "code": "missing_end_command",
                "message": "DST sequence does not contain a decoded end command",
            }
        )
    frequencies = Counter(command.get("type") for command in commands)
    declared_commands = header.get("ST")
    if isinstance(declared_commands, int) and declared_commands != len(commands):
        diagnostics.append(
            {
                "severity": "error",
                "code": "header_command_count_mismatch",
                "message": (
                    f"DST header declares {declared_commands} commands, "
                    f"but {len(commands)} were decoded"
                ),
            }
        )
    declared_color_changes = header.get("CO")
    decoded_color_changes = frequencies.get("color_change", 0)
    if (
        isinstance(declared_color_changes, int)
        and declared_color_changes != decoded_color_changes
    ):
        diagnostics.append(
            {
                "severity": "error",
                "code": "header_color_change_count_mismatch",
                "message": (
                    f"DST header declares {declared_color_changes} color changes, "
                    f"but {decoded_color_changes} were decoded"
                ),
            }
        )

    observed: dict[str, Any] = {
        "dst_header": header,
        "coordinate_unit_mm": DSTParser.UNIT_MM,
    }
    if isinstance(header.get("ST"), int):
        observed["header_command_count"] = header["ST"]
    if isinstance(header.get("CO"), int):
        observed["header_color_change_count"] = header["CO"]

    return ParsedSource(
        source_format="dst",
        observed_metadata=observed,
        commands=commands,
        unit_mm=DSTParser.UNIT_MM,
        diagnostics=diagnostics,
    )


def parse_emb(path: Path) -> ParsedSource:
    reader = EmbReader(path)
    streams = reader.list_streams()
    observed: dict[str, Any] = {
        "file_size_bytes": path.stat().st_size,
        "streams": streams,
    }
    diagnostics: list[dict[str, Any]] = []
    if reader.has_stream(DDDParser.STREAM_NAME):
        observed.update(DDDParser(path).parse())
    else:
        diagnostics.append(
            {
                "severity": "warning",
                "code": "ddd_stream_unavailable",
                "message": "EMB file has no WilcomDesignInformationDDD stream",
            }
        )

    if reader.has_stream("Contents"):
        diagnostics.append(
            {
                "severity": "info",
                "code": "contents_not_interpreted",
                "message": (
                    "Contents is present, but the current exploratory parser does not "
                    "establish stitch-coordinate semantics"
                ),
            }
        )
    return ParsedSource(
        source_format="emb",
        observed_metadata=observed,
        commands=[],
        diagnostics=diagnostics,
    )


def parse_source(path: Path) -> ParsedSource:
    suffix = path.suffix.casefold()
    if suffix == ".dst":
        return parse_dst(path)
    if suffix == ".emb":
        return parse_emb(path)
    raise ValueError(f"unsupported embroidery format: {path.suffix}")
