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


def test_build_document_canvas_candidate() -> None:
    candidate = automation.build_document_canvas_candidate(
        hwnd=123,
        class_name="AfxFrameOrView140u",
        visible=True,
        rectangle=(100, 200, 900, 700),
    )

    assert candidate == (
        400_000,
        123,
        500,
        450,
    )


@pytest.mark.parametrize(
    (
        "class_name",
        "visible",
        "rectangle",
    ),
    [
        (
            "OtherWindowClass",
            True,
            (0, 0, 1000, 800),
        ),
        (
            "AfxFrameOrView140u",
            False,
            (0, 0, 1000, 800),
        ),
        (
            "AfxFrameOrView140u",
            True,
            (0, 0, 199, 800),
        ),
        (
            "AfxFrameOrView140u",
            True,
            (0, 0, 1000, 149),
        ),
    ],
)
def test_build_document_canvas_candidate_rejects_invalid(
    class_name: str,
    visible: bool,
    rectangle: tuple[int, int, int, int],
) -> None:
    assert automation.build_document_canvas_candidate(
        hwnd=123,
        class_name=class_name,
        visible=visible,
        rectangle=rectangle,
    ) is None


def test_choose_document_canvas_candidate_uses_largest() -> None:
    selected = automation.choose_document_canvas_candidate(
        [
            (100_000, 10, 100, 200),
            (900_000, 20, 300, 400),
            (500_000, 30, 500, 600),
        ]
    )

    assert selected == (20, 300, 400)


def test_choose_document_canvas_candidate_handles_empty_list() -> None:
    assert (
        automation.choose_document_canvas_candidate([])
        is None
    )


def test_send_ctrl_a_win32_uses_expected_event_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[int, int, int, int]] = []

    def record_event(
        virtual_key: int,
        scan_code: int,
        flags: int,
        extra_info: int,
    ) -> None:
        events.append(
            (
                virtual_key,
                scan_code,
                flags,
                extra_info,
            )
        )

    monkeypatch.setattr(
        automation.win32api,
        "keybd_event",
        record_event,
    )
    monkeypatch.setattr(
        automation.time,
        "sleep",
        lambda _: None,
    )

    automation.send_ctrl_a_win32()

    assert events == [
        (
            automation.win32con.VK_CONTROL,
            0,
            0,
            0,
        ),
        (
            ord("A"),
            0,
            0,
            0,
        ),
        (
            ord("A"),
            0,
            automation.win32con.KEYEVENTF_KEYUP,
            0,
        ),
        (
            automation.win32con.VK_CONTROL,
            0,
            automation.win32con.KEYEVENTF_KEYUP,
            0,
        ),
    ]


def test_send_ctrl_a_win32_releases_ctrl_when_a_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[int, int]] = []

    def fail_on_a_press(
        virtual_key: int,
        _scan_code: int,
        flags: int,
        _extra_info: int,
    ) -> None:
        events.append(
            (
                virtual_key,
                flags,
            )
        )

        if virtual_key == ord("A") and flags == 0:
            raise RuntimeError("A press failed")

    monkeypatch.setattr(
        automation.win32api,
        "keybd_event",
        fail_on_a_press,
    )
    monkeypatch.setattr(
        automation.time,
        "sleep",
        lambda _: None,
    )

    with pytest.raises(
        RuntimeError,
        match="A press failed",
    ):
        automation.send_ctrl_a_win32()

    assert events[-2:] == [
        (
            ord("A"),
            automation.win32con.KEYEVENTF_KEYUP,
        ),
        (
            automation.win32con.VK_CONTROL,
            automation.win32con.KEYEVENTF_KEYUP,
        ),
    ]


def test_select_all_design_objects_supports_both_methods(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    focus_calls: list[int] = []
    win32_calls: list[str] = []
    pywinauto_calls: list[
        tuple[str, float, bool]
    ] = []

    monkeypatch.setattr(
        automation,
        "focus_window",
        focus_calls.append,
    )
    monkeypatch.setattr(
        automation,
        "find_document_canvas",
        lambda _: None,
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetWindowRect",
        lambda _: (0, 0, 1000, 800),
    )
    monkeypatch.setattr(
        automation.mouse,
        "click",
        lambda **_: None,
    )
    monkeypatch.setattr(
        automation.time,
        "sleep",
        lambda _: None,
    )
    monkeypatch.setattr(
        automation,
        "send_ctrl_a_win32",
        lambda: win32_calls.append("win32"),
    )
    monkeypatch.setattr(
        automation.keyboard,
        "send_keys",
        lambda keys, pause, vk_packet: (
            pywinauto_calls.append(
                (
                    keys,
                    pause,
                    vk_packet,
                )
            )
        ),
    )
    automation._LOGGED_SELECTION_METHODS.clear()

    automation.select_all_design_objects(
        123,
        method="win32",
    )
    automation.select_all_design_objects(
        123,
        method="pywinauto",
    )

    assert focus_calls == [
        123,
        123,
        123,
        123,
    ]
    assert win32_calls == ["win32"]
    assert pywinauto_calls == [
        (
            "^a",
            0.05,
            False,
        )
    ]


def test_select_all_design_objects_rejects_unknown_method() -> None:
    with pytest.raises(
        ValueError,
        match="Неизвестный метод выделения",
    ):
        automation.select_all_design_objects(
            123,
            method="unknown",
        )


def test_wait_for_selected_design_alternates_methods(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    methods: list[str] = []
    control_checks = 0

    class FakeWindow:
        def set_focus(self) -> None:
            pass

    def select_objects(
        _main_hwnd: int,
        method: str,
    ) -> None:
        methods.append(method)

    def get_controls(
        _window,
        require_enabled: bool,
    ):
        nonlocal control_checks
        control_checks += 1
        assert require_enabled

        if control_checks < 3:
            raise RuntimeError("Поля неактивны")

        return "controls"

    monkeypatch.setattr(
        automation,
        "raise_for_known_open_error_dialog",
        lambda: None,
    )
    monkeypatch.setattr(
        automation,
        "focus_window",
        lambda _: None,
    )
    monkeypatch.setattr(
        automation,
        "select_all_design_objects",
        select_objects,
    )
    monkeypatch.setattr(
        automation,
        "get_position_controls",
        get_controls,
    )
    monkeypatch.setattr(
        automation.time,
        "sleep",
        lambda _: None,
    )

    result = automation.wait_for_selected_design(
        FakeWindow(),
        main_hwnd=123,
        timeout=1.0,
    )

    assert result == "controls"
    assert methods == [
        "win32",
        "pywinauto",
        "win32",
    ]
