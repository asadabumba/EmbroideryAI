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


def test_wait_for_document_open_sees_expected_stem_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    title = (
        "Wilcom - "
        "[Hatch_Halloween-Quilt - Pumpkin_e3 Janome]"
    )

    monkeypatch.setattr(
        automation,
        "raise_for_known_open_error_dialog",
        lambda: None,
    )
    monkeypatch.setattr(
        automation,
        "find_save_changes_dialog",
        lambda *_: None,
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetWindowText",
        lambda _: title,
    )

    result = automation.wait_for_document_open(
        123,
        Path("Hatch_Halloween-Quilt - Pumpkin_e3.EMB"),
    )

    assert result == title


def test_wait_for_document_open_waits_for_title_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    titles = iter(
        [
            "Wilcom - [Ghost_e3]",
            "Wilcom - [Pumpkin_e3]",
        ]
    )

    monkeypatch.setattr(
        automation,
        "raise_for_known_open_error_dialog",
        lambda: None,
    )
    monkeypatch.setattr(
        automation,
        "find_save_changes_dialog",
        lambda *_: None,
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetWindowText",
        lambda _: next(titles),
    )
    monkeypatch.setattr(
        automation.time,
        "sleep",
        lambda _: None,
    )

    result = automation.wait_for_document_open(
        123,
        Path("Pumpkin_e3.EMB"),
    )

    assert result == "Wilcom - [Pumpkin_e3]"


def test_wait_for_document_open_is_case_insensitive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        automation,
        "raise_for_known_open_error_dialog",
        lambda: None,
    )
    monkeypatch.setattr(
        automation,
        "find_save_changes_dialog",
        lambda *_: None,
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetWindowText",
        lambda _: "Wilcom - [PUMPKIN_E3]",
    )

    result = automation.wait_for_document_open(
        123,
        Path("pumpkin_e3.EMB"),
    )

    assert result == "Wilcom - [PUMPKIN_E3]"


def test_wait_for_document_open_timeout_shows_titles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    times = iter(
        [
            0.0,
            0.0,
            61.0,
        ]
    )

    monkeypatch.setattr(
        automation,
        "raise_for_known_open_error_dialog",
        lambda: None,
    )
    monkeypatch.setattr(
        automation,
        "find_save_changes_dialog",
        lambda *_: None,
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetWindowText",
        lambda _: "Wilcom - [Ghost_e3]",
    )
    monkeypatch.setattr(
        automation.time,
        "time",
        lambda: next(times),
    )
    monkeypatch.setattr(
        automation.time,
        "sleep",
        lambda _: None,
    )

    with pytest.raises(TimeoutError) as error_info:
        automation.wait_for_document_open(
            123,
            Path("Pumpkin_e3.EMB"),
            timeout=60.0,
        )

    message = str(error_info.value)
    assert "за 60 секунд" in message
    assert "Ожидался: Pumpkin_e3" in message
    assert (
        "Фактический заголовок: "
        "Wilcom - [Ghost_e3]"
        in message
    )


def test_wait_for_document_open_checks_known_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checks = 0

    def raise_known_error() -> None:
        nonlocal checks
        checks += 1
        raise RuntimeError("Известная ошибка открытия")

    monkeypatch.setattr(
        automation,
        "raise_for_known_open_error_dialog",
        raise_known_error,
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetWindowText",
        lambda _: pytest.fail(
            "Заголовок не должен читаться после известной ошибки"
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="Известная ошибка открытия",
    ):
        automation.wait_for_document_open(
            123,
            Path("Pumpkin_e3.EMB"),
        )

    assert checks == 1


def test_wait_for_document_closed_waits_for_stem_to_disappear(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    titles = iter(
        [
            "Wilcom - [Pumpkin_e3]",
            "Wilcom - No Design",
        ]
    )

    monkeypatch.setattr(
        automation.win32gui,
        "IsWindow",
        lambda _: True,
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetWindowText",
        lambda _: next(titles),
    )
    monkeypatch.setattr(
        automation.time,
        "sleep",
        lambda _: None,
    )

    result = automation.wait_for_document_closed(
        123,
        "Pumpkin_e3",
    )

    assert result == "Wilcom - No Design"


def test_wait_for_document_closed_handles_destroyed_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        automation.win32gui,
        "IsWindow",
        lambda _: False,
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetWindowText",
        lambda _: pytest.fail(
            "У уничтоженного окна нельзя читать заголовок"
        ),
    )

    result = automation.wait_for_document_closed(
        123,
        "Pumpkin_e3",
    )

    assert result == ""


def test_close_document_waits_after_ctrl_f4(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []

    class FakeWindow:
        def set_focus(self) -> None:
            events.append("set_focus")

    titles = iter(
        [
            "Wilcom - [Pumpkin_e3]",
            "Wilcom - No Design",
        ]
    )

    monkeypatch.setattr(
        automation,
        "focus_window",
        lambda hwnd: events.append(
            (
                "focus",
                hwnd,
            )
        ),
    )
    monkeypatch.setattr(
        automation,
        "send_ctrl_virtual_key",
        lambda vk_code: events.append(
            (
                "hotkey",
                vk_code,
            )
        ),
    )
    monkeypatch.setattr(
        automation.win32gui,
        "IsWindow",
        lambda _: True,
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetWindowText",
        lambda _: next(titles),
    )
    monkeypatch.setattr(
        automation,
        "find_save_changes_dialog",
        lambda *_: None,
    )
    monkeypatch.setattr(
        automation.time,
        "sleep",
        lambda _: None,
    )

    result = automation.close_document_and_wait(
        FakeWindow(),
        main_hwnd=123,
        document_stem="Pumpkin_e3",
    )

    assert result == "Wilcom - No Design"
    assert events == [
        (
            "focus",
            123,
        ),
        "set_focus",
        (
            "hotkey",
            automation.win32con.VK_F4,
        ),
    ]


def test_process_creates_uia_only_after_document_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_path = tmp_path / "Pumpkin_e3.EMB"
    file_path.write_bytes(b"EMB")
    events: list[str] = []

    class FakeWindow:
        pass

    fake_window = FakeWindow()

    class FakeDesktop:
        def window(self, handle: int):
            assert handle == 123
            events.append("uia_window")
            return fake_window

    def desktop_factory(backend: str) -> FakeDesktop:
        assert backend == "uia"
        events.append("desktop")
        return FakeDesktop()

    def wait_open(
        main_hwnd: int,
        opened_path: Path,
        timeout: float,
    ) -> str:
        assert main_hwnd == 123
        assert opened_path == file_path
        assert timeout == 60.0
        events.append("wait_open")
        return "Wilcom - [Pumpkin_e3]"

    def process_document(
        window,
        hwnd: int,
        x: str,
        y: str,
    ) -> dict[str, str]:
        assert window is fake_window
        assert hwnd == 123
        assert x == "14"
        assert y == "0.74"
        events.append("process")
        return {
            "old_x": "0.00",
            "old_y": "0.78",
            "new_x": "14.00",
            "new_y": "0.74",
        }

    def close_document(
        window,
        main_hwnd: int,
        document_stem: str,
        timeout: float,
        save: bool,
    ) -> str:
        assert window is fake_window
        assert main_hwnd == 123
        assert document_stem == "Pumpkin_e3"
        assert timeout == 20.0
        assert save is True
        events.append("close")
        return "Wilcom - No Design"

    monkeypatch.setattr(
        automation,
        "find_es_exe",
        lambda _: Path("ES.EXE"),
    )
    monkeypatch.setattr(
        automation,
        "list_es_main_windows",
        lambda: [],
    )
    monkeypatch.setattr(
        automation.os,
        "startfile",
        lambda _: events.append("startfile"),
    )
    monkeypatch.setattr(
        automation,
        "raise_for_known_open_error_dialog",
        lambda: None,
    )
    monkeypatch.setattr(
        automation,
        "wait_for_es_main_window",
        lambda timeout: 123,
    )
    monkeypatch.setattr(
        automation,
        "wait_for_document_open",
        wait_open,
    )
    monkeypatch.setattr(
        automation.time,
        "sleep",
        lambda _: None,
    )
    monkeypatch.setattr(
        automation,
        "Desktop",
        desktop_factory,
    )
    monkeypatch.setattr(
        automation,
        "process_open_document",
        process_document,
    )
    monkeypatch.setattr(
        automation,
        "close_document_and_wait",
        close_document,
    )

    result = automation.process_emb_file(
        file_path=file_path,
        x="14",
        y="0.74",
        close=True,
    )

    assert events.index("wait_open") < events.index("desktop")
    assert events.index("uia_window") < events.index("process")
    assert events.index("process") < events.index("close")
    assert result["status"] == "success"
    assert result["new_x"] == "14.00"


def test_process_cleanup_does_not_hide_original_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_path = tmp_path / "Pumpkin_e3.EMB"
    file_path.write_bytes(b"EMB")
    fake_window = object()
    cleanup_calls: list[
        tuple[int, str, object]
    ] = []

    class FakeDesktop:
        def window(self, handle: int):
            assert handle == 123
            return fake_window

    def fail_processing(*_) -> dict[str, str]:
        raise ValueError("Исходная ошибка обработки")

    def fail_cleanup(
        main_hwnd: int,
        document_stem: str,
        window,
    ) -> None:
        cleanup_calls.append(
            (
                main_hwnd,
                document_stem,
                window,
            )
        )
        raise RuntimeError("Ошибка cleanup")

    monkeypatch.setattr(
        automation,
        "find_es_exe",
        lambda _: Path("ES.EXE"),
    )
    monkeypatch.setattr(
        automation,
        "list_es_main_windows",
        lambda: [],
    )
    monkeypatch.setattr(
        automation.os,
        "startfile",
        lambda _: None,
    )
    monkeypatch.setattr(
        automation,
        "raise_for_known_open_error_dialog",
        lambda: None,
    )
    monkeypatch.setattr(
        automation,
        "wait_for_es_main_window",
        lambda timeout: 123,
    )
    monkeypatch.setattr(
        automation,
        "wait_for_document_open",
        lambda *_, **__: "Wilcom - [Pumpkin_e3]",
    )
    monkeypatch.setattr(
        automation.time,
        "sleep",
        lambda _: None,
    )
    monkeypatch.setattr(
        automation,
        "Desktop",
        lambda backend: FakeDesktop(),
    )
    monkeypatch.setattr(
        automation,
        "process_open_document",
        fail_processing,
    )
    monkeypatch.setattr(
        automation,
        "close_document_best_effort",
        fail_cleanup,
    )

    with pytest.raises(
        ValueError,
        match="Исходная ошибка обработки",
    ):
        automation.process_emb_file(
            file_path=file_path,
            x="14",
            y="0.74",
            close=True,
        )

    assert cleanup_calls == [
        (
            123,
            "Pumpkin_e3",
            fake_window,
        )
    ]


def test_send_ctrl_virtual_key_releases_both_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[int, int]] = []

    def record_event(
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

    automation.send_ctrl_virtual_key(
        ord("S")
    )

    assert events == [
        (
            automation.win32con.VK_CONTROL,
            0,
        ),
        (
            ord("S"),
            0,
        ),
        (
            ord("S"),
            automation.win32con.KEYEVENTF_KEYUP,
        ),
        (
            automation.win32con.VK_CONTROL,
            automation.win32con.KEYEVENTF_KEYUP,
        ),
    ]


def test_send_save_command_uses_vk_s_without_type_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []

    class FakeWindow:
        def set_focus(self) -> None:
            events.append("set_focus")

        def type_keys(self, *_: object, **__: object) -> None:
            pytest.fail(
                "Ctrl+S не должен отправляться через type_keys"
            )

    monkeypatch.setattr(
        automation,
        "focus_window",
        lambda hwnd: events.append(
            (
                "focus",
                hwnd,
            )
        ),
    )
    monkeypatch.setattr(
        automation,
        "send_ctrl_virtual_key",
        lambda vk_code: events.append(
            (
                "hotkey",
                vk_code,
            )
        ),
    )
    monkeypatch.setattr(
        automation.time,
        "sleep",
        lambda _: None,
    )

    automation.send_save_command(
        FakeWindow(),
        123,
    )

    assert events == [
        (
            "focus",
            123,
        ),
        "set_focus",
        (
            "hotkey",
            ord("S"),
        ),
    ]


def configure_save_dialog_windows(
    monkeypatch: pytest.MonkeyPatch,
    texts_by_hwnd: dict[int, list[str]],
    classes_by_hwnd: dict[int, str] | None = None,
) -> None:
    classes = classes_by_hwnd or {}

    def enum_windows(callback, data) -> None:
        for hwnd in texts_by_hwnd:
            callback(hwnd, data)

    monkeypatch.setattr(
        automation.win32gui,
        "EnumWindows",
        enum_windows,
    )
    monkeypatch.setattr(
        automation.win32gui,
        "IsWindowVisible",
        lambda _: True,
    )
    monkeypatch.setattr(
        automation,
        "is_es_process_window",
        lambda _: True,
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetClassName",
        lambda hwnd: classes.get(
            hwnd,
            "#32770",
        ),
    )
    monkeypatch.setattr(
        automation,
        "get_window_texts",
        lambda hwnd: texts_by_hwnd[hwnd],
    )


def test_find_russian_save_changes_dialog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    texts = [
        "EmbroideryStudio",
        "Сохранить изменения в design.EMB?",
        "Да",
        "Нет",
        "Отмена",
    ]
    configure_save_dialog_windows(
        monkeypatch,
        {100: texts},
    )

    assert automation.find_save_changes_dialog() == (
        100,
        texts,
    )


def test_find_save_dialog_prefers_requested_document_stem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other_texts = [
        "Сохранить изменения в Other.EMB?",
        "Да",
        "Нет",
    ]
    target_texts = [
        "Сохранить изменения в Pumpkin_e3.EMB?",
        "Да",
        "Нет",
    ]
    configure_save_dialog_windows(
        monkeypatch,
        {
            100: other_texts,
            200: target_texts,
        },
    )

    assert automation.find_save_changes_dialog(
        "pumpkin_E3"
    ) == (
        200,
        target_texts,
    )


def test_find_save_dialog_ignores_unrelated_dialog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_save_dialog_windows(
        monkeypatch,
        {
            100: [
                "Невозможно открыть дизайн",
                "Данная версия не может открыть этот дизайн",
                "OK",
            ]
        },
    )

    assert (
        automation.find_save_changes_dialog()
        is None
    )


@pytest.mark.parametrize(
    ("save", "button_id"),
    [
        (
            True,
            lambda: automation.win32con.IDYES,
        ),
        (
            False,
            lambda: automation.win32con.IDNO,
        ),
    ],
)
def test_dismiss_save_dialog_uses_standard_button_id(
    save: bool,
    button_id,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    posted: list[tuple[int, int]] = []

    monkeypatch.setattr(
        automation,
        "find_save_changes_dialog",
        lambda *_: (
            100,
            ["Сохранить изменения в design.EMB?"],
        ),
    )

    def get_dialog_item(
        hwnd: int,
        requested_id: int,
    ) -> int:
        assert hwnd == 100
        assert requested_id == button_id()
        return 200

    monkeypatch.setattr(
        automation.win32gui,
        "GetDlgItem",
        get_dialog_item,
    )
    monkeypatch.setattr(
        automation.win32gui,
        "PostMessage",
        lambda hwnd, message, _wparam, _lparam: (
            posted.append(
                (
                    hwnd,
                    message,
                )
            )
        ),
    )
    monkeypatch.setattr(
        automation.win32gui,
        "IsWindow",
        lambda _: False,
    )

    assert automation.dismiss_save_changes_dialog(
        "design",
        save=save,
    )
    assert posted == [
        (
            200,
            automation.win32con.BM_CLICK,
        )
    ]


@pytest.mark.parametrize(
    ("save", "target_text"),
    [
        (True, "&Да"),
        (False, "&Нет"),
    ],
)
def test_dismiss_save_dialog_falls_back_to_button_text(
    save: bool,
    target_text: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    posted: list[int] = []
    button_texts = {
        301: "Отмена",
        302: target_text,
    }

    monkeypatch.setattr(
        automation,
        "find_save_changes_dialog",
        lambda *_: (
            100,
            ["Сохранить изменения в design.EMB?"],
        ),
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetDlgItem",
        lambda *_: 0,
    )

    def enum_children(hwnd: int, callback, data) -> None:
        assert hwnd == 100

        for child_hwnd in button_texts:
            callback(child_hwnd, data)

    monkeypatch.setattr(
        automation.win32gui,
        "EnumChildWindows",
        enum_children,
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetClassName",
        lambda _: "Button",
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetWindowText",
        lambda hwnd: button_texts[hwnd],
    )
    monkeypatch.setattr(
        automation.win32gui,
        "PostMessage",
        lambda hwnd, *_: posted.append(hwnd),
    )
    monkeypatch.setattr(
        automation.win32gui,
        "IsWindow",
        lambda _: False,
    )

    assert automation.dismiss_save_changes_dialog(
        "design",
        save=save,
    )
    assert posted == [302]


def test_dismiss_save_dialog_never_clicks_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    posted: list[int] = []

    monkeypatch.setattr(
        automation,
        "find_save_changes_dialog",
        lambda *_: (
            100,
            ["Сохранить изменения в design.EMB?"],
        ),
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetDlgItem",
        lambda *_: 0,
    )
    monkeypatch.setattr(
        automation.win32gui,
        "EnumChildWindows",
        lambda _hwnd, callback, data: callback(
            301,
            data,
        ),
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetClassName",
        lambda _: "Button",
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetWindowText",
        lambda _: "Отмена",
    )
    monkeypatch.setattr(
        automation.win32gui,
        "PostMessage",
        lambda hwnd, *_: posted.append(hwnd),
    )

    assert not automation.dismiss_save_changes_dialog(
        "design",
        save=True,
    )
    assert posted == []


def test_close_document_clicks_yes_and_waits_for_title_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    titles = iter(
        [
            "Wilcom - [design]",
            "Wilcom - No Design",
        ]
    )
    dismiss_calls: list[tuple[str | None, bool]] = []
    dialogs = iter(
        [
            (
                500,
                ["Сохранить изменения в design.EMB?"],
            ),
            None,
        ]
    )

    class FakeWindow:
        def set_focus(self) -> None:
            pass

    monkeypatch.setattr(
        automation,
        "focus_window",
        lambda _: None,
    )
    monkeypatch.setattr(
        automation,
        "send_ctrl_virtual_key",
        lambda vk: (
            vk == automation.win32con.VK_F4
            or pytest.fail("Ожидался VK_F4")
        ),
    )
    monkeypatch.setattr(
        automation.win32gui,
        "IsWindow",
        lambda _: True,
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetWindowText",
        lambda _: next(titles),
    )
    monkeypatch.setattr(
        automation,
        "find_save_changes_dialog",
        lambda *_: next(dialogs),
    )
    monkeypatch.setattr(
        automation,
        "dismiss_save_changes_dialog",
        lambda document_stem, save, timeout: (
            dismiss_calls.append(
                (
                    document_stem,
                    save,
                )
            )
            or True
        ),
    )
    monkeypatch.setattr(
        automation.time,
        "sleep",
        lambda _: None,
    )

    result = automation.close_document_and_wait(
        FakeWindow(),
        123,
        "design",
        save=True,
    )

    assert result == "Wilcom - No Design"
    assert dismiss_calls == [
        (
            "design",
            True,
        )
    ]


def test_close_document_best_effort_clicks_no(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    titles = iter(
        [
            "Wilcom - [design]",
            "Wilcom - [design]",
            "Wilcom - No Design",
        ]
    )
    dismiss_values: list[bool] = []
    dialogs = iter(
        [
            (
                500,
                ["Сохранить изменения в design.EMB?"],
            ),
            (
                500,
                ["Сохранить изменения в design.EMB?"],
            ),
            None,
        ]
    )

    class FakeWindow:
        def set_focus(self) -> None:
            pass

    monkeypatch.setattr(
        automation.win32gui,
        "IsWindow",
        lambda _: True,
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetWindowText",
        lambda _: next(titles),
    )
    monkeypatch.setattr(
        automation,
        "find_save_changes_dialog",
        lambda *_: next(dialogs),
    )
    monkeypatch.setattr(
        automation,
        "focus_window",
        lambda _: None,
    )
    monkeypatch.setattr(
        automation,
        "send_ctrl_virtual_key",
        lambda _: None,
    )
    monkeypatch.setattr(
        automation,
        "dismiss_save_changes_dialog",
        lambda _stem, save, timeout: (
            dismiss_values.append(save)
            or True
        ),
    )
    monkeypatch.setattr(
        automation.time,
        "sleep",
        lambda _: None,
    )

    automation.close_document_best_effort(
        123,
        "design",
        window=FakeWindow(),
    )

    assert dismiss_values == [False]


def test_wait_for_document_open_discards_blocking_save_dialog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dismiss_calls: list[tuple[str | None, bool, float]] = []

    monkeypatch.setattr(
        automation,
        "raise_for_known_open_error_dialog",
        lambda: None,
    )
    monkeypatch.setattr(
        automation,
        "find_save_changes_dialog",
        lambda *_: (
            500,
            [
                "Сохранить изменения в "
                "old.__processing_123.EMB?",
                "Да",
                "Нет",
                "Отмена",
            ],
        ),
    )
    monkeypatch.setattr(
        automation,
        "dismiss_save_changes_dialog",
        lambda document_stem, save, timeout: (
            dismiss_calls.append(
                (
                    document_stem,
                    save,
                    timeout,
                )
            )
            or True
        ),
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetWindowText",
        lambda _: pytest.fail(
            "Title не должен проверяться при блокирующем диалоге"
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="заблокировано диалогом сохранения.*"
        "Диалог закрыт без сохранения",
    ):
        automation.wait_for_document_open(
            123,
            Path("new.EMB"),
        )

    assert dismiss_calls == [
        (
            None,
            False,
            3.0,
        )
    ]


def test_close_document_timeout_contains_dialog_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    times = iter(
        [
            0.0,
            0.0,
            0.0,
            21.0,
        ]
    )

    class FakeWindow:
        def set_focus(self) -> None:
            pass

    monkeypatch.setattr(
        automation,
        "focus_window",
        lambda _: None,
    )
    monkeypatch.setattr(
        automation,
        "send_ctrl_virtual_key",
        lambda _: None,
    )
    monkeypatch.setattr(
        automation.win32gui,
        "IsWindow",
        lambda _: True,
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetWindowText",
        lambda _: "Wilcom - [design]",
    )
    monkeypatch.setattr(
        automation,
        "find_save_changes_dialog",
        lambda *_: (
            500,
            [
                "EmbroideryStudio",
                "Сохранить изменения в design.EMB?",
            ],
        ),
    )
    monkeypatch.setattr(
        automation,
        "dismiss_save_changes_dialog",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        automation.time,
        "time",
        lambda: next(times),
    )
    monkeypatch.setattr(
        automation.time,
        "sleep",
        lambda _: None,
    )

    with pytest.raises(TimeoutError) as captured:
        automation.close_document_and_wait(
            FakeWindow(),
            123,
            "design",
            timeout=20.0,
        )

    message = str(captured.value)
    assert "Фактический заголовок: Wilcom - [design]" in message
    assert "Диалог сохранения найден: да" in message
    assert "Сохранить изменения в design.EMB?" in message
