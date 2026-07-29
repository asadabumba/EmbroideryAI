from __future__ import annotations

import ast
import hashlib
import json
import math
import random
import statistics
import struct
import sys
import zlib
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ddd_parser import DDDParser
from src.dst_parser import DSTParser
from src.emb_reader import EmbReader


OUTPUT_DIR = ROOT / "logs" / "audit_pipeline"
JSON_PATH = OUTPUT_DIR / "report.json"
MARKDOWN_PATH = OUTPUT_DIR / "report.md"

EMB_DIR = ROOT / "dataset" / "raw"
DST_DIR = ROOT / "archive" / "originals" / "dst"

RANDOM_SEED = 20260727
NEGATIVE_CONTROL_ROUNDS = 200
CONTENTS_CONTROL_FILES = 20
CONTENTS_SHUFFLES_PER_FILE = 5


def normalize_stem(path: Path) -> str:
    import re
    import unicodedata

    value = unicodedata.normalize("NFKC", path.stem).casefold().replace("ё", "е")
    return re.sub(r"[^a-zа-я0-9]+", "", value)


def relative_error(a: float | int | None, b: float | int | None) -> float | None:
    if a is None or b is None:
        return None
    return abs(float(a) - float(b)) / max(abs(float(a)), abs(float(b)), 1.0)


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round((len(ordered) - 1) * p)
    return ordered[index]


def collect_files(folder: Path, suffix: str) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(
        path
        for path in folder.rglob("*")
        if path.is_file() and path.suffix.casefold() == suffix.casefold()
    )


def test_inventory() -> dict[str, Any]:
    tests_dir = ROOT / "tests"
    files = sorted(tests_dir.rglob("*.py")) if tests_dir.exists() else []
    details = []

    for path in files:
        source = path.read_text(encoding="utf-8-sig")
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            details.append(
                {
                    "file": str(path.relative_to(ROOT)),
                    "syntax_error": f"{exc.msg} at line {exc.lineno}",
                }
            )
            continue

        functions = [
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        pytest_functions = [name for name in functions if name.startswith("test_")]

        executable_top_level = []
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                continue
            if isinstance(node, ast.If):
                test_text = ast.get_source_segment(source, node.test) or ""
                if "__name__" in test_text:
                    continue
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                # Константы конфигурации сами по себе не выполняют исследование.
                continue
            executable_top_level.append(
                {
                    "line": getattr(node, "lineno", None),
                    "kind": type(node).__name__,
                }
            )

        details.append(
            {
                "file": str(path.relative_to(ROOT)),
                "line_count": len(source.splitlines()),
                "functions": functions,
                "pytest_functions": pytest_functions,
                "top_level_executable": executable_top_level,
            }
        )

    return {
        "python_files": len(files),
        "pytest_test_functions": sum(len(item.get("pytest_functions", [])) for item in details),
        "test_named_files_without_tests": [
            item["file"]
            for item in details
            if Path(item["file"]).name.startswith("test_")
            and not item.get("pytest_functions")
        ],
        "test_named_files_with_top_level_execution": [
            item["file"]
            for item in details
            if Path(item["file"]).name.startswith("test_")
            and item.get("top_level_executable")
        ],
        "details": details,
    }


def independent_bounds(commands: list[dict[str, Any]]) -> dict[str, int]:
    # Для сравнения с DST header включаем исходную точку машины.
    xs = [0]
    ys = [0]
    for command in commands:
        if command["type"] == "end":
            continue
        xs.append(int(command["x"]))
        ys.append(int(command["y"]))
    return {
        "min_x": min(xs),
        "max_x": max(xs),
        "min_y": min(ys),
        "max_y": max(ys),
        "width": max(xs) - min(xs),
        "height": max(ys) - min(ys),
    }


def dst_audit() -> dict[str, Any]:
    paths = collect_files(DST_DIR, ".dst")
    failures = []
    header_st_mismatches = []
    header_color_mismatches = []
    current_bounds_differ_from_origin_bounds = []
    header_bounds_mismatches = []
    sequin_files = []
    trailing_partial_files = []
    no_end_files = []

    for path in paths:
        try:
            data = path.read_bytes()
            parser = DSTParser(data)
            header = parser.read_header()
            commands = parser.parse()
            types = parser.count_types(commands)
            current = parser.get_bounds(commands)
            independent = independent_bounds(commands)

            if header.get("ST") is not None and int(header["ST"]) != len(commands):
                header_st_mismatches.append(
                    {
                        "file": str(path.relative_to(ROOT)),
                        "header": header.get("ST"),
                        "parsed": len(commands),
                    }
                )

            if header.get("CO") is not None and int(header["CO"]) != types.get("color_change", 0):
                header_color_mismatches.append(
                    {
                        "file": str(path.relative_to(ROOT)),
                        "header": header.get("CO"),
                        "parsed": types.get("color_change", 0),
                    }
                )

            if current != independent:
                current_bounds_differ_from_origin_bounds.append(
                    {
                        "file": str(path.relative_to(ROOT)),
                        "current": current,
                        "with_origin": independent,
                    }
                )

            if all(key in header for key in ("+X", "-X", "+Y", "-Y")):
                header_width = int(header["+X"]) + int(header["-X"])
                header_height = int(header["+Y"]) + int(header["-Y"])
                if header_width != independent["width"] or header_height != independent["height"]:
                    header_bounds_mismatches.append(
                        {
                            "file": str(path.relative_to(ROOT)),
                            "header_width": header_width,
                            "header_height": header_height,
                            "parsed_width": independent["width"],
                            "parsed_height": independent["height"],
                        }
                    )

            if types.get("sequin_mode", 0):
                sequin_files.append(
                    {
                        "file": str(path.relative_to(ROOT)),
                        "sequin_mode_commands": types.get("sequin_mode", 0),
                        "jump_commands": types.get("jump", 0),
                    }
                )

            if not commands or commands[-1]["type"] != "end":
                no_end_files.append(str(path.relative_to(ROOT)))

            command_bytes = data[DSTParser.HEADER_SIZE :]
            if len(command_bytes) % 3:
                trailing_partial_files.append(
                    {
                        "file": str(path.relative_to(ROOT)),
                        "command_bytes": len(command_bytes),
                        "remainder": len(command_bytes) % 3,
                    }
                )
        except Exception as exc:  # noqa: BLE001
            failures.append(
                {
                    "file": str(path.relative_to(ROOT)),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )

    return {
        "files": len(paths),
        "failures": failures,
        "header_st_mismatches": header_st_mismatches,
        "header_color_mismatches": header_color_mismatches,
        "current_bounds_differ_from_origin_bounds": current_bounds_differ_from_origin_bounds,
        "header_bounds_mismatches": header_bounds_mismatches,
        "sequin_files": sequin_files,
        "trailing_partial_files": trailing_partial_files,
        "no_end_files": no_end_files,
    }


def unpack_prefixed_zlib(raw: bytes) -> tuple[int, bytes]:
    if len(raw) < 5:
        raise ValueError("stream is shorter than 5 bytes")
    expected = struct.unpack_from("<I", raw, 0)[0]
    unpacked = zlib.decompress(raw[4:])
    return expected, unpacked


def emb_audit() -> dict[str, Any]:
    paths = collect_files(EMB_DIR, ".emb")
    failures = []
    stream_presence = Counter()
    zlib_stats = defaultdict(lambda: Counter())
    zlib_failures = []
    ddd_failures = []
    ddd_coverage = Counter()
    ddd_available = 0
    icon_signatures = Counter()

    for path in paths:
        try:
            reader = EmbReader(path)
            streams = reader.list_streams()
            stream_presence.update(streams)

            for name in ("Contents", "DESIGN_ICON", "TRUEVIEW_ICON"):
                if not reader.has_stream(name):
                    continue
                zlib_stats[name]["present"] += 1
                raw = reader.extract_stream(name)
                try:
                    expected, unpacked = unpack_prefixed_zlib(raw)
                except Exception as exc:  # noqa: BLE001
                    zlib_stats[name]["decompression_failed"] += 1
                    zlib_failures.append(
                        {
                            "file": str(path.relative_to(ROOT)),
                            "stream": name,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        }
                    )
                    continue

                zlib_stats[name]["decompressed"] += 1
                if expected == len(unpacked):
                    zlib_stats[name]["length_matches"] += 1
                else:
                    zlib_stats[name]["length_mismatches"] += 1
                    zlib_failures.append(
                        {
                            "file": str(path.relative_to(ROOT)),
                            "stream": name,
                            "expected": expected,
                            "actual": len(unpacked),
                        }
                    )

                if name == "DESIGN_ICON":
                    icon_signatures[unpacked[:2].hex()] += 1
                elif name == "TRUEVIEW_ICON":
                    icon_signatures[unpacked[:4].hex()] += 1

            if reader.has_stream(DDDParser.STREAM_NAME):
                ddd_available += 1
                try:
                    metadata = DDDParser(path).parse()
                    for key, value in metadata.items():
                        if key != "filename" and value is not None:
                            ddd_coverage[key] += 1
                except Exception as exc:  # noqa: BLE001
                    ddd_failures.append(
                        {
                            "file": str(path.relative_to(ROOT)),
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        }
                    )
        except Exception as exc:  # noqa: BLE001
            failures.append(
                {
                    "file": str(path.relative_to(ROOT)),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )

    return {
        "files": len(paths),
        "failures": failures,
        "stream_presence": dict(stream_presence),
        "zlib_stats": {name: dict(values) for name, values in zlib_stats.items()},
        "zlib_failures": zlib_failures,
        "ddd_available": ddd_available,
        "ddd_failures": ddd_failures,
        "ddd_field_coverage": dict(ddd_coverage),
        "icon_signatures": dict(icon_signatures),
    }


def dedupe_by_sha256(paths: list[Path]) -> list[Path]:
    unique = {}
    for path in paths:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        unique.setdefault(digest, path)
    return list(unique.values())


def get_ddd_width_raw(metadata: dict[str, Any]) -> float | None:
    width = metadata.get("design_width")
    if isinstance(width, (int, float)) and not isinstance(width, bool):
        return abs(float(width))
    left = metadata.get("design_left")
    right = metadata.get("design_right")
    if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
        return None
    return abs(float(left)) + abs(float(right))


def pair_metrics(emb_path: Path, dst_path: Path) -> dict[str, Any]:
    ddd = DDDParser(emb_path).parse()
    dst = DSTParser(dst_path.read_bytes())
    header = dst.read_header()
    commands = dst.parse()
    types = dst.count_types(commands)
    bounds = independent_bounds(commands)

    stitches = ddd.get("stitch_count")
    colors = ddd.get("color_count")
    color_changes = ddd.get("color_change_count")
    width_raw = get_ddd_width_raw(ddd)
    dst_width = bounds["width"]

    stitch_error = relative_error(stitches, header.get("ST"))
    colors_exact = (
        isinstance(colors, (int, float))
        and isinstance(color_changes, (int, float))
        and header.get("CO") is not None
        and int(colors) == int(header["CO"]) + 1
        and int(color_changes) == int(header["CO"])
    )
    ratio = width_raw / dst_width if width_raw is not None and dst_width else None

    return {
        "emb_file": str(emb_path.relative_to(ROOT)),
        "dst_file": str(dst_path.relative_to(ROOT)),
        "ddd_stitches": stitches,
        "dst_header_st": header.get("ST"),
        "dst_parsed_commands": len(commands),
        "dst_stitch_commands": types.get("stitch", 0),
        "stitch_error": stitch_error,
        "ddd_colors": colors,
        "ddd_color_changes": color_changes,
        "dst_color_changes": header.get("CO"),
        "colors_exact": colors_exact,
        "ddd_width_raw": width_raw,
        "dst_width": dst_width,
        "width_ratio": ratio,
    }


def pair_audit() -> dict[str, Any]:
    emb_paths = collect_files(EMB_DIR, ".emb")
    dst_paths = collect_files(DST_DIR, ".dst")

    emb_index: dict[str, list[Path]] = defaultdict(list)
    dst_index: dict[str, list[Path]] = defaultdict(list)
    for path in emb_paths:
        emb_index[normalize_stem(path)].append(path)
    for path in dst_paths:
        dst_index[normalize_stem(path)].append(path)

    shared = sorted(set(emb_index) & set(dst_index))
    metrics = []
    errors = []

    for key in shared:
        unique_dst = dedupe_by_sha256(dst_index[key])
        for emb_path in emb_index[key]:
            for dst_path in unique_dst:
                try:
                    item = pair_metrics(emb_path, dst_path)
                    item["normalized_name"] = key
                    metrics.append(item)
                except Exception as exc:  # noqa: BLE001
                    errors.append(
                        {
                            "emb_file": str(emb_path.relative_to(ROOT)),
                            "dst_file": str(dst_path.relative_to(ROOT)),
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        }
                    )

    independent_candidates = [
        item
        for item in metrics
        if item["stitch_error"] is not None
        and item["stitch_error"] <= 0.001
        and item["colors_exact"]
        and item["width_ratio"] is not None
    ]
    ratios = [float(item["width_ratio"]) for item in independent_candidates]
    empirical_scale = statistics.median(ratios) if ratios else None

    strict_candidates = []
    if empirical_scale is not None:
        strict_candidates = [
            item
            for item in independent_candidates
            if abs(float(item["width_ratio"]) / empirical_scale - 1.0) <= 0.01
        ]

    # Отрицательный контроль: перемешиваем DST-части между EMB.
    rng = random.Random(RANDOM_SEED)
    negative_counts = []
    if empirical_scale is not None and metrics:
        dst_side = [
            {
                "st": item["dst_header_st"],
                "co": item["dst_color_changes"],
                "width": item["dst_width"],
            }
            for item in metrics
        ]
        for _ in range(NEGATIVE_CONTROL_ROUNDS):
            shuffled = dst_side.copy()
            rng.shuffle(shuffled)
            matches = 0
            for emb, dst in zip(metrics, shuffled):
                stitch_error = relative_error(emb["ddd_stitches"], dst["st"])
                colors_exact = (
                    isinstance(emb["ddd_colors"], (int, float))
                    and isinstance(emb["ddd_color_changes"], (int, float))
                    and dst["co"] is not None
                    and int(emb["ddd_colors"]) == int(dst["co"]) + 1
                    and int(emb["ddd_color_changes"]) == int(dst["co"])
                )
                ratio = (
                    float(emb["ddd_width_raw"]) / float(dst["width"])
                    if emb["ddd_width_raw"] is not None and dst["width"]
                    else None
                )
                if (
                    stitch_error is not None
                    and stitch_error <= 0.001
                    and colors_exact
                    and ratio is not None
                    and abs(ratio / empirical_scale - 1.0) <= 0.01
                ):
                    matches += 1
            negative_counts.append(matches)

    return {
        "shared_normalized_names": len(shared),
        "evaluated_combinations": len(metrics),
        "errors": errors,
        "independent_candidates": len(independent_candidates),
        "empirical_width_scale": {
            "count": len(ratios),
            "median": empirical_scale,
            "mean": statistics.mean(ratios) if ratios else None,
            "min": min(ratios) if ratios else None,
            "max": max(ratios) if ratios else None,
            "p05": percentile(ratios, 0.05),
            "p95": percentile(ratios, 0.95),
        },
        "strict_candidates": len(strict_candidates),
        "strict_examples": strict_candidates[:50],
        "negative_control": {
            "rounds": len(negative_counts),
            "mean_matches": statistics.mean(negative_counts) if negative_counts else None,
            "max_matches": max(negative_counts) if negative_counts else None,
            "nonzero_rounds": sum(value > 0 for value in negative_counts),
        },
    }


def scan_numeric_records(data: bytes) -> list[dict[str, Any]]:
    records = []
    for offset in range(0, max(0, len(data) - 12)):
        property_id, flags, type_code, count = struct.unpack_from("<IHHI", data, offset)
        if property_id == 0 or property_id > 0x00FFFFFF:
            continue
        if flags != 0 or type_code not in (2, 3) or not (1 <= count <= 16):
            continue
        value_size = 4 if type_code == 2 else 8
        end = offset + 12 + value_size * count
        if end > len(data):
            continue
        fmt = "<" + ("f" if type_code == 2 else "d") * count
        values = struct.unpack_from(fmt, data, offset + 12)
        if not all(math.isfinite(value) and abs(value) < 1e12 for value in values):
            continue
        if not any(value == 0 or abs(value) >= 1e-20 for value in values):
            continue
        records.append(
            {
                "offset": offset,
                "property_id": property_id,
                "type": type_code,
                "count": count,
                "size": 12 + value_size * count,
            }
        )
    return records


def contents_negative_control(pair_report: dict[str, Any]) -> dict[str, Any]:
    examples = pair_report.get("strict_examples", [])[:CONTENTS_CONTROL_FILES]
    rng = random.Random(RANDOM_SEED)
    files = []
    errors = []

    for example in examples:
        path = ROOT / example["emb_file"]
        try:
            raw = EmbReader(path).extract_stream("Contents")
            _, data = unpack_prefixed_zlib(raw)
            actual_records = scan_numeric_records(data)
            shuffled_counts = []
            for _ in range(CONTENTS_SHUFFLES_PER_FILE):
                shuffled = list(data)
                rng.shuffle(shuffled)
                shuffled_counts.append(len(scan_numeric_records(bytes(shuffled))))

            contiguous = 0
            for first, second in zip(actual_records, actual_records[1:]):
                if first["offset"] + first["size"] == second["offset"]:
                    contiguous += 1

            files.append(
                {
                    "file": example["emb_file"],
                    "contents_size": len(data),
                    "actual_records": len(actual_records),
                    "shuffled_records": shuffled_counts,
                    "shuffled_mean": statistics.mean(shuffled_counts) if shuffled_counts else None,
                    "contiguous_pairs": contiguous,
                    "possible_pairs": max(len(actual_records) - 1, 0),
                    "offset_mod_4": dict(Counter(record["offset"] % 4 for record in actual_records)),
                }
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {
                    "file": example.get("emb_file"),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )

    actual_counts = [item["actual_records"] for item in files]
    shuffled_counts = [count for item in files for count in item["shuffled_records"]]
    return {
        "files": files,
        "errors": errors,
        "actual_mean": statistics.mean(actual_counts) if actual_counts else None,
        "shuffled_mean": statistics.mean(shuffled_counts) if shuffled_counts else None,
        "note": (
            "Шаффл сохраняет размер и частоты байтов, но разрушает порядок. "
            "Сильно большее число записей в оригинале поддерживает гипотезу структуры, "
            "но не доказывает смысл полей."
        ),
    }


def generate_findings(report: dict[str, Any]) -> list[dict[str, str]]:
    findings = []
    tests = report["tests"]
    if tests["pytest_test_functions"] == 0:
        findings.append(
            {
                "severity": "critical",
                "title": "Текущие файлы tests не являются pytest-тестами",
                "detail": (
                    f"Найдено {tests['python_files']} Python-файлов и 0 функций test_*. "
                    "Pytest может выполнять верхнеуровневый код, но ничего не проверяет assertions."
                ),
            }
        )

    dst = report["dst"]
    if dst["current_bounds_differ_from_origin_bounds"]:
        findings.append(
            {
                "severity": "high",
                "title": "DST bounds не всегда учитывает origin",
                "detail": (
                    f"В {len(dst['current_bounds_differ_from_origin_bounds'])} файлах текущий get_bounds() "
                    "отличается от расчёта с включением (0,0)."
                ),
            }
        )
    if dst["sequin_files"]:
        findings.append(
            {
                "severity": "high",
                "title": "Sequin eject требует состояния",
                "detail": (
                    f"Найдено {len(dst['sequin_files'])} DST с sequin mode. Текущий command_type() "
                    "не различает jump и sequin eject после переключения режима."
                ),
            }
        )

    emb = report["emb"]
    zlib_mismatches = sum(
        values.get("length_mismatches", 0) + values.get("decompression_failed", 0)
        for values in emb["zlib_stats"].values()
    )
    findings.append(
        {
            "severity": "info" if zlib_mismatches == 0 else "high",
            "title": "Проверка 4-byte length + zlib",
            "detail": (
                f"Проверено на корпусе; проблем: {zlib_mismatches}. "
                "Этот формат обёртки можно считать подтверждённым только для потоков, прошедших проверку."
            ),
        }
    )

    pairs = report["pairs"]
    scale = pairs["empirical_width_scale"]
    findings.append(
        {
            "severity": "info",
            "title": "Коэффициент ширины проверен независимо",
            "detail": (
                f"Сначала отобраны пары только по стежкам и цветам: {pairs['independent_candidates']}. "
                f"Медианный DDD/DST коэффициент: {scale['median']}."
            ),
        }
    )

    findings.append(
        {
            "severity": "high",
            "title": "Contents scanner остаётся гипотезой",
            "detail": (
                "Даже если отрицательный контроль подтверждает неслучайную структуру, сканирование каждого offset "
                "не доказывает границы контейнеров, семантику type code или связь с геометрией."
            ),
        }
    )
    return findings


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# EmbroideryAI audit report", ""]
    for finding in report["findings"]:
        lines.append(f"## [{finding['severity'].upper()}] {finding['title']}")
        lines.append("")
        lines.append(finding["detail"])
        lines.append("")

    tests = report["tests"]
    lines += [
        "## Test inventory",
        "",
        f"- Python files under tests: {tests['python_files']}",
        f"- Real pytest functions: {tests['pytest_test_functions']}",
        f"- test_ files without tests: {len(tests['test_named_files_without_tests'])}",
        "",
        "## DST corpus",
        "",
        f"- Files: {report['dst']['files']}",
        f"- Parse failures: {len(report['dst']['failures'])}",
        f"- ST mismatches: {len(report['dst']['header_st_mismatches'])}",
        f"- CO mismatches: {len(report['dst']['header_color_mismatches'])}",
        f"- Bounds affected by missing origin: {len(report['dst']['current_bounds_differ_from_origin_bounds'])}",
        f"- Sequin files: {len(report['dst']['sequin_files'])}",
        "",
        "## EMB corpus",
        "",
        f"- Files: {report['emb']['files']}",
        f"- OLE/read failures: {len(report['emb']['failures'])}",
        f"- DDD available: {report['emb']['ddd_available']}",
        f"- DDD parse failures: {len(report['emb']['ddd_failures'])}",
        "",
        "## EMB–DST pairs",
        "",
        f"- Shared normalized names: {report['pairs']['shared_normalized_names']}",
        f"- Evaluated combinations: {report['pairs']['evaluated_combinations']}",
        f"- Independent candidates (stitches + colors): {report['pairs']['independent_candidates']}",
        f"- Strict candidates (+ width within 1%): {report['pairs']['strict_candidates']}",
        f"- Empirical scale median: {report['pairs']['empirical_width_scale']['median']}",
        f"- Negative control mean matches: {report['pairs']['negative_control']['mean_matches']}",
        f"- Negative control max matches: {report['pairs']['negative_control']['max_matches']}",
        "",
        "## Contents negative control",
        "",
        f"- Files checked: {len(report['contents_control']['files'])}",
        f"- Mean detected records in originals: {report['contents_control']['actual_mean']}",
        f"- Mean detected records after byte shuffle: {report['contents_control']['shuffled_mean']}",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/5] Инвентаризация тестов")
    tests = test_inventory()

    print("[2/5] Проверка DST корпуса")
    dst = dst_audit()

    print("[3/5] Проверка EMB/OLE/zlib/DDD")
    emb = emb_audit()

    print("[4/5] Независимая проверка EMB–DST пар и коэффициента")
    pairs = pair_audit()

    print("[5/5] Отрицательный контроль Contents")
    contents_control = contents_negative_control(pairs)

    report = {
        "settings": {
            "random_seed": RANDOM_SEED,
            "negative_control_rounds": NEGATIVE_CONTROL_ROUNDS,
            "contents_control_files": CONTENTS_CONTROL_FILES,
            "contents_shuffles_per_file": CONTENTS_SHUFFLES_PER_FILE,
        },
        "tests": tests,
        "dst": dst,
        "emb": emb,
        "pairs": pairs,
        "contents_control": contents_control,
    }
    report["findings"] = generate_findings(report)

    JSON_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    MARKDOWN_PATH.write_text(render_markdown(report), encoding="utf-8")

    print("\nГотово:")
    print(JSON_PATH)
    print(MARKDOWN_PATH)


if __name__ == "__main__":
    main()
