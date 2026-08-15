from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .schema import DesignRecord


def _reject_non_standard_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON numeric constant: {value}")


def _atomic_text_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def write_json(path: Path, value: Any) -> None:
    _atomic_text_write(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
    )


def read_json(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=_reject_non_standard_constant,
    )


def write_record(path: Path, record: DesignRecord) -> None:
    write_json(path, record.to_dict())


def read_record(path: Path) -> DesignRecord:
    value = read_json(path)
    if not isinstance(value, dict):
        raise TypeError(f"record must be a JSON object: {path}")
    return DesignRecord.from_dict(value)


def write_jsonl(path: Path, values: Iterable[dict[str, Any]]) -> None:
    lines = [
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        for value in values
    ]
    _atomic_text_write(path, "\n".join(lines) + ("\n" if lines else ""))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line, parse_constant=_reject_non_standard_constant)
        if not isinstance(value, dict):
            raise TypeError(f"line {line_number} in {path} is not a JSON object")
        result.append(value)
    return result
