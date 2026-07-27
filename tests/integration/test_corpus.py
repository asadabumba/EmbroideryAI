from __future__ import annotations

import os
import struct
import zlib
from pathlib import Path

import pytest

from src.ddd_parser import DDDParser
from src.dst_parser import DSTParser
from src.emb_reader import EmbReader


ROOT = Path(__file__).resolve().parents[2]
LIMIT = int(os.getenv("EMB_AUDIT_LIMIT", "50"))


def _files(folder: Path, suffix: str) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.casefold() == suffix)


@pytest.mark.integration
def test_dst_header_counts_on_corpus() -> None:
    files = _files(ROOT / "archive" / "originals" / "dst", ".dst")[:LIMIT]
    if not files:
        pytest.skip("DST corpus отсутствует")

    failures = []
    for path in files:
        parser = DSTParser(path.read_bytes())
        header = parser.read_header()
        commands = parser.parse()
        if header.get("ST") != len(commands):
            failures.append((str(path), header.get("ST"), len(commands)))
    assert failures == []


@pytest.mark.integration
def test_length_prefixed_zlib_streams_on_corpus() -> None:
    files = _files(ROOT / "dataset" / "raw", ".emb")[:LIMIT]
    if not files:
        pytest.skip("EMB corpus отсутствует")

    failures = []
    checked = 0
    for path in files:
        reader = EmbReader(path)
        for name in ("Contents", "DESIGN_ICON", "TRUEVIEW_ICON"):
            if not reader.has_stream(name):
                continue
            raw = reader.extract_stream(name)
            if len(raw) < 5:
                failures.append((str(path), name, "too short"))
                continue
            expected = struct.unpack_from("<I", raw, 0)[0]
            try:
                unpacked = zlib.decompress(raw[4:])
            except zlib.error as exc:
                failures.append((str(path), name, f"zlib: {exc}"))
                continue
            checked += 1
            if expected != len(unpacked):
                failures.append((str(path), name, expected, len(unpacked)))
    assert checked > 0
    assert failures == []


@pytest.mark.integration
def test_ddd_parser_on_corpus() -> None:
    files = _files(ROOT / "dataset" / "raw", ".emb")[:LIMIT]
    if not files:
        pytest.skip("EMB corpus отсутствует")

    parsed = 0
    failures = []
    for path in files:
        reader = EmbReader(path)
        if not reader.has_stream(DDDParser.STREAM_NAME):
            continue
        try:
            metadata = DDDParser(path).parse()
        except Exception as exc:  # noqa: BLE001 — интеграционный аудит
            failures.append((str(path), type(exc).__name__, str(exc)))
            continue
        parsed += 1
        if metadata.get("filename") != path.name:
            failures.append((str(path), "wrong filename"))
    assert parsed > 0
    assert failures == []
