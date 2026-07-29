from __future__ import annotations

from src.ddd_parser import DDDParser


def test_align_4() -> None:
    assert DDDParser._align_4(0) == 0
    assert DDDParser._align_4(1) == 4
    assert DDDParser._align_4(4) == 4
    assert DDDParser._align_4(5) == 8


def test_signed32() -> None:
    assert DDDParser._to_signed32(0) == 0
    assert DDDParser._to_signed32(2**31 - 1) == 2**31 - 1
    assert DDDParser._to_signed32(2**32 - 1) == -1


def test_decode_text() -> None:
    assert DDDParser._decode_text(b"Tajima\x00") == "Tajima"
    assert DDDParser._decode_text("Wilcom\x00") == "Wilcom"
