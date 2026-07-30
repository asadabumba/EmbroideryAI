from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "automate_wilcom_file.py"
)
SPEC = importlib.util.spec_from_file_location(
    "automate_wilcom_file_window_tests",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
automation = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = automation
SPEC.loader.exec_module(automation)


@pytest.mark.parametrize(
    (
        "title",
        "class_name",
        "width",
        "height",
        "visible",
    ),
    [
        (
            "Wilcom EmbroideryStudio",
            "XTPFrameShadow",
            1200,
            800,
            True,
        ),
        (
            "XTPFrameShadow",
            "AfxFrameOrView140u",
            1200,
            800,
            True,
        ),
        (
            "Невозможно открыть дизайн",
            "#32770",
            800,
            500,
            True,
        ),
        ("", "AfxFrameOrView140u", 1200, 800, True),
        ("   ", "AfxFrameOrView140u", 1200, 800, True),
        (
            "Wilcom EmbroideryStudio",
            "AfxFrameOrView140u",
            299,
            800,
            True,
        ),
        (
            "Wilcom EmbroideryStudio",
            "AfxFrameOrView140u",
            1200,
            299,
            True,
        ),
        (
            "Wilcom EmbroideryStudio",
            "AfxFrameOrView140u",
            1200,
            800,
            False,
        ),
    ],
)
def test_es_main_window_filter_rejects_technical_windows(
    title: str,
    class_name: str,
    width: int,
    height: int,
    visible: bool,
) -> None:
    assert not automation.is_es_main_window_candidate(
        title=title,
        class_name=class_name,
        width=width,
        height=height,
        visible=visible,
    )


def test_es_main_window_filter_accepts_generic_wilcom_window() -> None:
    assert automation.is_es_main_window_candidate(
        title="Wilcom EmbroideryStudio",
        class_name="AfxFrameOrView140u",
        width=1200,
        height=800,
        visible=True,
    )


def test_es_main_window_sort_prefers_ultimate_title() -> None:
    preferred = automation.es_main_window_sort_key(
        "Wilcom - Ultimate Special Edition",
        area=100,
    )
    generic = automation.es_main_window_sort_key(
        "Wilcom EmbroideryStudio",
        area=10_000_000,
    )

    assert preferred > generic


def test_describe_known_open_error() -> None:
    description = automation.describe_open_design_error(
        [
            "Невозможно открыть дизайн",
            "Файл был создан в более поздней версии программы.",
            "Данная версия не может открыть этот дизайн.",
            "OK",
        ]
    )

    assert description == (
        "Wilcom не смог открыть файл: дизайн создан "
        "в более поздней версии программы."
    )
