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


@pytest.fixture(autouse=True)
def reset_save_as_win32_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        automation,
        "SAVE_AS_MOUSE_CACHE",
        {},
    )
    monkeypatch.setattr(
        automation,
        "POSITION_CONTROLS_CACHE",
        {},
    )
    monkeypatch.setattr(
        automation,
        "_SAVE_AS_WIN32_COMMAND_ID",
        None,
    )
    monkeypatch.setattr(
        automation,
        "_SAVE_AS_WIN32_COMMAND_HWND",
        None,
    )
    monkeypatch.setattr(
        automation,
        "_SAVE_AS_WIN32_DISABLED_HWNDS",
        set(),
    )
    monkeypatch.setattr(
        automation,
        "_LOGGED_WIN32_FILE_MENUS",
        set(),
    )
    monkeypatch.setattr(
        automation.mouse,
        "click",
        lambda *_args, **_kwargs: None,
    )


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


def test_set_document_position_does_not_save(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []
    controls = (
        object(),
        object(),
        object(),
        object(),
    )
    values = iter(
        [
            "0.00",
            "0.50",
            "10.00",
            "-2.00",
        ]
    )

    class FakeWindow:
        def set_focus(self) -> None:
            events.append("focus")

    monkeypatch.setattr(
        automation,
        "focus_window",
        lambda hwnd: events.append(
            (
                "focus_window",
                hwnd,
            )
        ),
    )
    monkeypatch.setattr(
        automation,
        "raise_for_known_open_error_dialog",
        lambda: None,
    )
    monkeypatch.setattr(
        automation,
        "wait_for_selected_design",
        lambda *_args, **_kwargs: controls,
    )
    monkeypatch.setattr(
        automation,
        "wait_for_enabled_controls",
        lambda *_args, **_kwargs: controls,
    )
    monkeypatch.setattr(
        automation,
        "read_value",
        lambda *_: next(values),
    )
    monkeypatch.setattr(
        automation,
        "set_value",
        lambda edit, value: events.append(
            (
                "set",
                edit,
                value,
            )
        ),
    )
    monkeypatch.setattr(
        automation,
        "send_save_command",
        lambda *_: pytest.fail(
            "set_document_position не должен сохранять"
        ),
    )

    result = automation.set_document_position(
        FakeWindow(),
        123,
        "10.00",
        "-2.00",
    )

    assert result == {
        "old_x": "0.00",
        "old_y": "0.50",
        "new_x": "10.00",
        "new_y": "-2.00",
    }


def test_process_open_document_still_saves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_values = {
        "old_x": "0",
        "old_y": "0",
        "new_x": "1",
        "new_y": "2",
    }
    calls: list[object] = []
    window = object()
    monkeypatch.setattr(
        automation,
        "set_document_position",
        lambda *args: (
            calls.append(
                (
                    "position",
                    args,
                )
            )
            or result_values
        ),
    )
    monkeypatch.setattr(
        automation,
        "send_save_command",
        lambda *args: calls.append(
            (
                "save",
                args,
            )
        ),
    )

    result = automation.process_open_document(
        window,
        123,
        "1",
        "2",
    )

    assert result == result_values
    assert calls == [
        (
            "position",
            (
                window,
                123,
                "1",
                "2",
            ),
        ),
        (
            "save",
            (
                window,
                123,
            ),
        ),
    ]


class FakeWin32MenuApi:
    def __init__(self, save_as_text: str) -> None:
        self.entries = {
            10: [
                ("&File", 0xFFFFFFFF, 20),
            ],
            20: [
                ("Save", 100, 0),
                (save_as_text, 101, 0),
            ],
        }
        self.messages: list[
            tuple[int, int, int, int]
        ] = []

    def GetMenu(self, hwnd: int) -> int:
        assert hwnd == 123
        return 10

    def GetMenuItemCount(self, menu: int) -> int:
        return len(self.entries[menu])

    def GetMenuStringW(
        self,
        menu: int,
        position: int,
        buffer,
        _buffer_size: int,
        flags: int,
    ) -> int:
        assert flags == automation.win32con.MF_BYPOSITION
        text = self.entries[menu][position][0]
        buffer.value = text
        return len(text)

    def GetSubMenu(
        self,
        menu: int,
        position: int,
    ) -> int:
        return self.entries[menu][position][2]

    def GetMenuItemID(
        self,
        menu: int,
        position: int,
    ) -> int:
        return self.entries[menu][position][1]

    def PostMessageW(
        self,
        hwnd: int,
        message: int,
        command_id: int,
        lparam: int,
    ) -> int:
        self.messages.append(
            (
                hwnd,
                message,
                command_id,
                lparam,
            )
        )
        return 1


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Save &As...\tCtrl+Shift+S",
            "save as",
        ),
        (
            "Сохранить как…",
            "сохранить как",
        ),
        (
            "Speichern unter...",
            "speichern unter",
        ),
        (
            "Save\xa0  &As…\tCtrl+Shift+S",
            "save as",
        ),
    ],
)
def test_normalize_win32_menu_text(
    text: str,
    expected: str,
) -> None:
    assert automation.normalize_menu_text(text) == expected


def test_menu_text_match_accepts_localized_suffix() -> None:
    assert automation.menu_text_matches(
        "Save As - Design",
        automation.SAVE_AS_MENU_TEXTS,
    )


@pytest.mark.parametrize(
    "save_as_text",
    [
        "Сохранить как...",
        "Save &As...",
        "Speichern unter…",
    ],
)
def test_win32_menu_scan_finds_localized_save_as(
    save_as_text: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = FakeWin32MenuApi(save_as_text)
    monkeypatch.setattr(
        automation,
        "_USER32",
        api,
    )

    item = automation.scan_save_as_win32_menu(123)

    assert item is not None
    assert item.command_id == 101
    assert item.depth == 1
    assert automation.normalize_menu_text(
        item.text
    ) in automation.SAVE_AS_MENU_TEXTS


def test_plain_save_is_not_win32_save_as() -> None:
    item = automation.Win32MenuItem(
        depth=1,
        text="Save",
        command_id=100,
        submenu_handle=0,
        path=("File", "Save"),
    )

    assert automation.find_save_as_win32_menu_item(
        [item]
    ) is None


def test_win32_menu_command_posts_wm_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = FakeWin32MenuApi("Save As")
    monkeypatch.setattr(
        automation,
        "_USER32",
        api,
    )

    automation.post_win32_menu_command(123, 101)

    assert api.messages == [
        (
            123,
            automation.win32con.WM_COMMAND,
            101,
            0,
        )
    ]


def test_find_save_as_dialog_requires_owned_32770(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    windows = [200, 300, 400]
    classes = {
        200: "XTPFrameShadow",
        300: "#32770",
        400: "#32770",
    }
    titles = {
        200: "Сохранить как",
        300: "Другое окно",
        400: "Сохранить как",
    }
    owners = {
        200: 123,
        300: 123,
        400: 123,
    }
    monkeypatch.setattr(
        automation.win32gui,
        "EnumWindows",
        lambda callback, data: [
            callback(hwnd, data)
            for hwnd in windows
        ],
    )
    monkeypatch.setattr(
        automation.win32gui,
        "IsWindowVisible",
        lambda _: True,
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetClassName",
        lambda hwnd: classes[hwnd],
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetWindowText",
        lambda hwnd: titles[hwnd],
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetWindow",
        lambda hwnd, _kind: owners[hwnd],
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetParent",
        lambda _: 0,
    )

    assert automation.find_save_as_dialog(
        123
    ) == 400


def make_win32_save_as_item(
    command_id: int,
) -> object:
    return automation.Win32MenuItem(
        depth=1,
        text="Save &As...",
        command_id=command_id,
        submenu_handle=0,
        path=("File", "Save &As..."),
    )


def test_open_save_as_uses_win32_before_uia(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    posted: list[tuple[int, int]] = []
    monkeypatch.setattr(
        automation,
        "focus_window",
        lambda _hwnd: None,
    )
    monkeypatch.setattr(
        automation,
        "scan_save_as_win32_menu",
        lambda _hwnd, debug: make_win32_save_as_item(
            321
        ),
    )
    monkeypatch.setattr(
        automation,
        "post_win32_menu_command",
        lambda hwnd, command_id: posted.append(
            (hwnd, command_id)
        ),
    )
    monkeypatch.setattr(
        automation,
        "wait_for_save_as_dialog",
        lambda _hwnd, timeout: (
            700
            if timeout <= 5.0
            else pytest.fail("слишком длинный timeout")
        ),
    )
    monkeypatch.setattr(
        automation,
        "invoke_fast_save_as_menu",
        lambda *_args, **_kwargs: pytest.fail(
            "UIA не должен вызываться после WM_COMMAND"
        ),
    )

    timings: dict[str, float] = {}
    assert automation.open_save_as_dialog(
        123,
        timings=timings,
    ) == 700
    assert posted == [(123, 321)]
    assert automation._SAVE_AS_WIN32_COMMAND_ID == 321
    assert {
        "open_save_as_cached_win32_command",
        "open_save_as_scan_win32_menu",
        "open_save_as_send_wm_command",
        "open_save_as_wait_dialog_win32",
        "open_save_as_uia_fast_path",
        "open_save_as_legacy_fallback",
        "open_save_as_total",
    } <= timings.keys()


def test_cached_win32_command_is_used_next_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    posted: list[int] = []
    monkeypatch.setattr(
        automation,
        "_SAVE_AS_WIN32_COMMAND_ID",
        321,
    )
    monkeypatch.setattr(
        automation,
        "_SAVE_AS_WIN32_COMMAND_HWND",
        123,
    )
    monkeypatch.setattr(
        automation,
        "focus_window",
        lambda _hwnd: None,
    )
    monkeypatch.setattr(
        automation,
        "post_win32_menu_command",
        lambda _hwnd, command_id: posted.append(
            command_id
        ),
    )
    monkeypatch.setattr(
        automation,
        "wait_for_save_as_dialog",
        lambda _hwnd, timeout: (
            701
            if timeout
            <= automation.WIN32_CACHED_DIALOG_TIMEOUT
            else pytest.fail("cache должен ждать кратко")
        ),
    )
    monkeypatch.setattr(
        automation,
        "scan_save_as_win32_menu",
        lambda *_args, **_kwargs: pytest.fail(
            "При рабочем cache повторный scan не нужен"
        ),
    )

    assert automation.open_save_as_dialog(123) == 701
    assert posted == [321]


def test_stale_cached_win32_command_is_reset_and_rescanned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    posted: list[int] = []
    dialogs = iter([0, 702])
    monkeypatch.setattr(
        automation,
        "_SAVE_AS_WIN32_COMMAND_ID",
        111,
    )
    monkeypatch.setattr(
        automation,
        "_SAVE_AS_WIN32_COMMAND_HWND",
        123,
    )
    monkeypatch.setattr(
        automation,
        "focus_window",
        lambda _hwnd: None,
    )
    monkeypatch.setattr(
        automation,
        "post_win32_menu_command",
        lambda _hwnd, command_id: posted.append(
            command_id
        ),
    )
    monkeypatch.setattr(
        automation,
        "wait_for_save_as_dialog",
        lambda _hwnd, timeout: next(dialogs),
    )
    monkeypatch.setattr(
        automation,
        "scan_save_as_win32_menu",
        lambda _hwnd, debug: make_win32_save_as_item(
            222
        ),
    )

    assert automation.open_save_as_dialog(123) == 702
    assert posted == [111, 222]
    assert automation._SAVE_AS_WIN32_COMMAND_ID == 222


def test_get_menu_null_falls_back_to_fast_uia(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NoMenuApi:
        def __init__(self) -> None:
            self.calls = 0

        def GetMenu(self, _hwnd: int) -> int:
            self.calls += 1
            return 0

    api = NoMenuApi()
    monkeypatch.setattr(
        automation,
        "_USER32",
        api,
    )
    monkeypatch.setattr(
        automation,
        "focus_window",
        lambda _hwnd: None,
    )
    monkeypatch.setattr(
        automation,
        "invoke_fast_save_as_menu",
        lambda _hwnd, timings: 703,
    )
    monkeypatch.setattr(
        automation,
        "post_win32_menu_command",
        lambda *_args: pytest.fail(
            "При GetMenu == NULL WM_COMMAND не нужен"
        ),
    )

    assert automation.open_save_as_dialog(123) == 703
    assert automation.open_save_as_dialog(123) == 703
    assert api.calls == 1
    assert 123 in automation._SAVE_AS_WIN32_DISABLED_HWNDS


def test_open_save_as_dialog_uses_slow_fallback_once(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fallback_calls: list[
        tuple[int, set[str], object]
    ] = []
    monkeypatch.setattr(
        automation,
        "focus_window",
        lambda _: None,
    )
    monkeypatch.setattr(
        automation,
        "invoke_fast_save_as_menu",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        automation,
        "invoke_uia_file_menu_item",
        lambda hwnd, texts, timings: (
            fallback_calls.append(
                (hwnd, texts, timings)
            )
            or True
        ),
    )
    monkeypatch.setattr(
        automation,
        "scan_save_as_win32_menu",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        automation,
        "wait_for_save_as_dialog",
        lambda _hwnd, timeout: 500,
    )
    monkeypatch.setattr(
        automation,
        "send_ctrl_virtual_key",
        lambda *_: pytest.fail(
            "Save As не должен использовать hotkey"
        ),
    )

    assert automation.open_save_as_dialog(
        123
    ) == 500
    assert fallback_calls == [
        (
            123,
            automation.SAVE_AS_MENU_TEXTS,
            None,
        )
    ]
    assert (
        "Быстрые способы Save As не сработали, "
        "использую legacy fallback."
        in capsys.readouterr().out
    )


def test_legacy_fallback_records_internal_timings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []
    file_item = FakeFastMenuItem(
        "File",
        "file",
        events,
    )
    save_as_item = FakeFastMenuItem(
        "Save As",
        "save_as",
        events,
    )
    controls = iter(
        [
            [file_item],
            [file_item, save_as_item],
        ]
    )
    monkeypatch.setattr(
        automation,
        "collect_uia_menu_controls",
        lambda _hwnd: next(controls),
    )
    monkeypatch.setattr(
        automation.time,
        "sleep",
        lambda _seconds: None,
    )
    timings: dict[str, float] = {}

    assert automation.invoke_uia_file_menu_item(
        123,
        automation.SAVE_AS_MENU_TEXTS,
        timings=timings,
    )
    assert {
        "open_save_as_legacy_collect_initial",
        "open_save_as_legacy_find_initial",
        "open_save_as_legacy_find_file",
        "open_save_as_legacy_invoke_file",
        "open_save_as_legacy_collect_after_file",
        "open_save_as_legacy_find_after_file",
        "open_save_as_legacy_invoke_target",
    } <= timings.keys()


class FakeFastElementInfo:
    def __init__(
        self,
        name: str = "",
        handle: int = 0,
        process_id: int = 42,
    ) -> None:
        self.name = name
        self.handle = handle
        self.process_id = process_id
        self.automation_id = ""
        self.control_type = "MenuItem"


class FakeFastRectangle:
    left = 10
    top = 20
    right = 300
    bottom = 500


class FakeFastMenuItem:
    def __init__(
        self,
        title: str,
        role: str,
        events: list[object],
    ) -> None:
        self.title = title
        self.role = role
        self.events = events
        self.element_info = FakeFastElementInfo(
            name=title
        )

    def window_text(self) -> str:
        return self.title

    def is_visible(self) -> bool:
        return True

    def rectangle(self) -> FakeFastRectangle:
        return FakeFastRectangle()

    def invoke(self) -> None:
        self.events.append(
            (
                "invoke",
                self.role,
                self.title,
            )
        )

    def click_input(self) -> None:
        pytest.fail(
            "invoke() должен работать на fast path"
        )

    def descendants(self, *_args, **_kwargs):
        pytest.fail(
            "Fast path не должен вызывать descendants()"
        )

    def print_control_identifiers(self) -> None:
        pytest.fail(
            "Fast path не должен печатать UIA-дерево"
        )


class FakeFastRoot:
    def descendants(self, *_args, **_kwargs):
        pytest.fail(
            "Fast path не должен обходить всё окно Wilcom"
        )

    def print_control_identifiers(self) -> None:
        pytest.fail(
            "Fast path не должен печатать UIA-дерево"
        )


class FakeFastChildSpecification:
    def __init__(
        self,
        role: str,
        criteria: dict[str, object],
        target,
        events: list[object],
    ) -> None:
        self.role = role
        self.criteria = criteria
        self.target = target
        self.events = events

    def wrapper_object(self):
        self.events.append(
            (
                "resolve",
                self.role,
                dict(self.criteria),
                automation.Timings.window_find_timeout,
            )
        )
        if self.criteria.get("control_type") != "MenuBar":
            raise RuntimeError("locator not found")

        return self.target

    def exists(self, *_args, **_kwargs) -> bool:
        pytest.fail(
            "Fast path должен разрешать locator один раз"
        )


class FakeFastContainerSpecification:
    def __init__(
        self,
        role: str,
        title: str,
        events: list[object],
    ) -> None:
        self.role = role
        self.events = events
        self.item = FakeFastMenuItem(
            title,
            role,
            events,
        )
        self.menu_bar = FakeFastMenuContainer(
            role,
            [self.item],
            events,
        )

    def wrapper_object(self):
        self.events.append(
            (
                "root_wrapper",
                self.role,
            )
        )
        return FakeFastRoot()

    def child_window(self, **criteria):
        self.events.append(
            (
                "child_window",
                self.role,
                dict(criteria),
            )
        )
        return FakeFastChildSpecification(
            self.role,
            dict(criteria),
            self.menu_bar,
            self.events,
        )


class FakeFastMenuContainer:
    def __init__(
        self,
        role: str,
        items: list[FakeFastMenuItem],
        events: list[object],
    ) -> None:
        self.role = role
        self.items = items
        self.events = events

    def children(self, **criteria):
        self.events.append(
            (
                "children",
                self.role,
                dict(criteria),
            )
        )

        if criteria != {
            "control_type": "MenuItem"
        }:
            raise AssertionError(criteria)

        return list(self.items)

    def descendants(self, *_args, **_kwargs):
        pytest.fail(
            "Fast path не должен вызывать descendants()"
        )


class FakeFastPopupWindow:
    def __init__(
        self,
        save_as_title: str,
        events: list[object],
        nested_save_as: bool = False,
    ) -> None:
        self.events = events
        self.nested_save_as = nested_save_as
        self.element_info = FakeFastElementInfo(
            handle=500,
            process_id=42,
        )
        self.item = FakeFastMenuItem(
            save_as_title,
            "save_as",
            events,
        )
        self.direct_item = (
            FakeFastMenuItem(
                "Save",
                "plain_save",
                events,
            )
            if nested_save_as
            else self.item
        )

    def rectangle(self) -> FakeFastRectangle:
        return FakeFastRectangle()

    def children(self, **criteria):
        self.events.append(
            (
                "children",
                "save_as",
                dict(criteria),
            )
        )

        if criteria != {
            "control_type": "MenuItem"
        }:
            raise AssertionError(criteria)

        return [self.direct_item]

    def descendants(self, *_args, **kwargs):
        self.events.append(
            (
                "descendants",
                "popup",
                dict(kwargs),
            )
        )
        return [self.item]


class FakeFastDesktop:
    def __init__(
        self,
        file_title: str,
        save_as_title: str,
        events: list[object],
        nested_save_as: bool = False,
    ) -> None:
        self.file_title = file_title
        self.save_as_title = save_as_title
        self.events = events
        self.nested_save_as = nested_save_as
        self.popup_windows: list[
            FakeFastPopupWindow
        ] = []

    def window(self, *, handle: int):
        self.events.append(
            (
                "desktop_window",
                handle,
            )
        )

        if handle == 123:
            return FakeFastContainerSpecification(
                "file",
                self.file_title,
                self.events,
            )

        raise AssertionError(
            f"Неожиданный HWND: {handle}"
        )

    def windows(self, **criteria):
        self.events.append(
            (
                "desktop_windows",
                dict(criteria),
            )
        )
        popup = FakeFastPopupWindow(
            self.save_as_title,
            self.events,
            nested_save_as=self.nested_save_as,
        )
        self.popup_windows.append(popup)
        return [popup]


def configure_fast_save_as_uia(
    monkeypatch: pytest.MonkeyPatch,
    file_title: str,
    save_as_title: str,
    cache: dict[str, str] | None = None,
    nested_save_as: bool = False,
) -> tuple[FakeFastDesktop, list[object]]:
    events: list[object] = []
    desktop = FakeFastDesktop(
        file_title,
        save_as_title,
        events,
        nested_save_as=nested_save_as,
    )
    monkeypatch.setattr(
        automation,
        "SAVE_AS_MENU_CACHE",
        dict(cache or {}),
    )
    monkeypatch.setattr(
        automation,
        "Desktop",
        lambda backend: (
            desktop
            if backend == "uia"
            else pytest.fail(
                f"Неожиданный backend: {backend}"
            )
        ),
    )
    monkeypatch.setattr(
        automation.win32process,
        "GetWindowThreadProcessId",
        lambda _hwnd: (1, 42),
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetWindow",
        lambda hwnd, _kind: (
            123
            if hwnd == 500
            else 0
        ),
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetParent",
        lambda _hwnd: 0,
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetWindowRect",
        lambda _hwnd: (
            0,
            0,
            1200,
            900,
        ),
    )
    monkeypatch.setattr(
        automation,
        "wait_for_save_as_dialog",
        lambda _hwnd, timeout: 700,
    )

    return desktop, events


@pytest.mark.parametrize(
    ("file_title", "save_as_title"),
    [
        ("Файл", "Сохранить как"),
        ("File", "Save As..."),
        ("Datei", "Speichern unter…"),
    ],
    ids=["ru", "en", "de"],
)
def test_fast_save_as_supports_languages_and_caches_titles(
    file_title: str,
    save_as_title: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, events = configure_fast_save_as_uia(
        monkeypatch,
        file_title,
        save_as_title,
    )

    assert automation.invoke_fast_save_as_menu(
        123
    )
    assert automation.SAVE_AS_MENU_CACHE == {
        "file_title": file_title,
        "save_as_title": save_as_title,
    }
    child_calls = [
        event
        for event in events
        if event[0] == "child_window"
    ]
    assert len(child_calls) == 1
    assert child_calls[0][1] == "file"
    assert child_calls[0][2] == {
        "control_type": "MenuBar",
        "depth": 3,
    }
    children_calls = [
        event
        for event in events
        if event[0] == "children"
    ]
    assert [
        event[1]
        for event in children_calls
    ] == [
        "file",
        "save_as",
    ]


def test_fast_save_as_uses_popup_menu_not_wilcom_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, events = configure_fast_save_as_uia(
        monkeypatch,
        "Файл",
        "Сохранить как",
    )

    assert automation.invoke_fast_save_as_menu(
        123
    )
    event_names = [
        event[0]
        for event in events
    ]
    file_invoke_index = events.index(
        (
            "invoke",
            "file",
            "Файл",
        )
    )
    popup_index = next(
        index
        for index, name in enumerate(event_names)
        if (
            name == "desktop_windows"
            and index > file_invoke_index
        )
    )
    save_child_index = events.index(
        next(
            event
            for event in events
            if (
                event[0] == "children"
                and event[1] == "save_as"
            )
        )
    )
    assert file_invoke_index < popup_index < save_child_index
    popup_call = next(
        event
        for event in events
        if event[0] == "desktop_windows"
    )
    assert popup_call[1]["control_type"] == "Menu"
    assert popup_call[1]["visible_only"] is True
    assert popup_call[1]["top_level_only"] is True


def test_fast_save_as_allows_descendants_only_on_popup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, events = configure_fast_save_as_uia(
        monkeypatch,
        "File",
        "Save As",
        nested_save_as=True,
    )

    assert automation.invoke_fast_save_as_menu(123)
    descendants_calls = [
        event
        for event in events
        if event[0] == "descendants"
    ]
    assert descendants_calls == [
        (
            "descendants",
            "popup",
            {"control_type": "MenuItem"},
        )
    ]


def test_all_visible_popups_are_checked_for_save_as(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []
    wrong_popup = FakeFastPopupWindow(
        "Save",
        events,
    )
    right_popup = FakeFastPopupWindow(
        "Save &As...\tCtrl+Shift+S",
        events,
    )
    monkeypatch.setattr(
        automation,
        "get_visible_uia_popup_menus",
        lambda *_args: [wrong_popup, right_popup],
    )
    monkeypatch.setattr(
        automation,
        "popup_is_relevant_after_file",
        lambda *_args: True,
    )

    match, inspections = (
        automation.find_save_as_in_visible_popups(
            object(),
            123,
            before_handles=set(),
            timeout=0.0,
        )
    )

    assert len(inspections) == 2
    assert match is not None
    assert match[0] is right_popup.item
    assert match[1] == "Save &As...\tCtrl+Shift+S"


def test_nested_submenu_is_expanded_before_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expanded: list[str] = []
    target = object()

    class ExpandInterface:
        CurrentExpandCollapseState = 0

        def Expand(self) -> None:
            expanded.append("expand")

    class ParentMenuItem:
        iface_expand_collapse = ExpandInterface()

        @staticmethod
        def children(**_kwargs):
            return []

    parent = ParentMenuItem()
    inspection = automation.UiaPopupMenuInspection(
        popup=object(),
        hwnd=500,
        class_name="#32768",
        rectangle=None,
        title="File",
        items=[parent],
    )
    monkeypatch.setattr(
        automation,
        "snapshot_visible_uia_popup_handles",
        lambda *_args: {500},
    )
    monkeypatch.setattr(
        automation,
        "find_save_as_in_visible_popups",
        lambda *_args, **_kwargs: (
            (target, "Save As"),
            [],
        ),
    )

    assert automation.find_save_as_through_submenu(
        object(),
        123,
        [inspection],
        timeout=1.0,
        debug=False,
        timings=None,
    ) == (target, "Save As")
    assert expanded == ["expand"]


def test_save_as_item_uses_raw_mouse_click(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clicks: list[tuple[str, tuple[int, int]]] = []

    class SaveAsItem:
        def rectangle(self) -> FakeFastRectangle:
            return FakeFastRectangle()

        def invoke(self) -> None:
            pytest.fail("invoke() ?? ?????? ??????????????")

        def click_input(self) -> None:
            pytest.fail("click_input() ?? ?????? ??????????????")

        def select(self) -> None:
            pytest.fail("select() ?? ?????? ??????????????")

    monkeypatch.setattr(
        automation.mouse,
        "click",
        lambda *, button, coords: clicks.append(
            (button, coords)
        ),
    )
    monkeypatch.setattr(
        automation,
        "wait_for_save_as_dialog",
        lambda _hwnd, timeout: 700,
    )

    assert automation.invoke_save_as_item_and_wait(
        SaveAsItem(),
        123,
        timeout=3.0,
    ) == 700
    assert clicks == [
        ("left", (155, 260)),
    ]

def test_second_fast_save_as_call_uses_cached_exact_titles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    desktop, events = configure_fast_save_as_uia(
        monkeypatch,
        "Файл",
        "Сохранить как",
    )
    cached_titles: list[str] = []
    original_find = (
        automation.wait_for_shallow_uia_menu_item
    )

    def find_with_cache_spy(
        container,
        allowed_texts: set[str],
        cached_title: str = "",
        timeout: float = 1.0,
        **kwargs,
    ):
        cached_titles.append(cached_title)
        return original_find(
            container,
            allowed_texts,
            cached_title=cached_title,
            timeout=timeout,
            **kwargs,
        )

    monkeypatch.setattr(
        automation,
        "wait_for_shallow_uia_menu_item",
        find_with_cache_spy,
    )
    assert automation.invoke_fast_save_as_menu(
        123
    )
    second_call_start = len(events)
    assert automation.invoke_fast_save_as_menu(
        123
    )
    assert cached_titles[-1] == "Файл"
    assert automation.SAVE_AS_MENU_CACHE == {
        "file_title": "Файл",
        "save_as_title": "Сохранить как",
    }
    assert len(events) > second_call_start
    assert len(desktop.popup_windows) == 4
    assert len(
        {
            id(popup)
            for popup in desktop.popup_windows
        }
    ) == 4


def test_stale_save_as_cache_falls_back_to_normalized_language_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, events = configure_fast_save_as_uia(
        monkeypatch,
        "File",
        "Save As",
        cache={
            "file_title": "Файл",
            "save_as_title": "Сохранить как",
        },
    )

    assert automation.invoke_fast_save_as_menu(
        123
    )
    assert automation.SAVE_AS_MENU_CACHE == {
        "file_title": "File",
        "save_as_title": "Save As",
    }
    children_calls = [
        event
        for event in events
        if event[0] == "children"
    ]
    assert [
        event[1]
        for event in children_calls
    ] == [
        "file",
        "save_as",
    ]


def test_failed_fast_lookup_clears_stale_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_fast_save_as_uia(
        monkeypatch,
        "Edit",
        "Save",
        cache={
            "file_title": "Файл",
            "save_as_title": "Сохранить как",
        },
    )
    monkeypatch.setattr(
        automation,
        "FAST_UIA_LOOKUP_TIMEOUT",
        0.0,
    )

    assert not automation.invoke_fast_save_as_menu(
        123
    )
    assert automation.SAVE_AS_MENU_CACHE == {}


def test_shallow_menu_lookup_prefers_exact_cached_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []
    english = FakeFastMenuItem(
        "File",
        "file",
        events,
    )
    russian = FakeFastMenuItem(
        "Файл",
        "file",
        events,
    )
    container = FakeFastMenuContainer(
        "file",
        [english, russian],
        events,
    )
    monkeypatch.setattr(
        automation.time,
        "sleep",
        lambda *_: pytest.fail(
            "Exact cache должен находиться сразу"
        ),
    )

    match = automation.wait_for_shallow_uia_menu_item(
        container,
        automation.FILE_MENU_TEXTS,
        cached_title="Файл",
        timeout=1.0,
    )

    assert match is not None
    assert match[0] is russian
    assert match[1] == "Файл"


def test_fast_menu_lookups_share_short_multilingual_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, events = configure_fast_save_as_uia(
        monkeypatch,
        "File",
        "Save As",
    )

    assert automation.invoke_fast_save_as_menu(
        123
    )
    resolves = [
        event
        for event in events
        if event[0] == "resolve"
    ]
    assert len(resolves) == 1
    assert all(
        float(event[3]) <= 1.0
        for event in resolves
    )
    children_calls = [
        event
        for event in events
        if event[0] == "children"
    ]
    assert len(children_calls) == 2


def test_open_save_as_fast_path_skips_slow_fallback_and_times_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_fast_save_as_uia(
        monkeypatch,
        "Файл",
        "Сохранить как",
    )
    monkeypatch.setattr(
        automation,
        "focus_window",
        lambda _hwnd: None,
    )
    monkeypatch.setattr(
        automation,
        "wait_for_save_as_dialog",
        lambda _hwnd, timeout: (
            700
            if timeout <= 5.0
            else pytest.fail(
                "Диалог нельзя ждать дольше 5 секунд"
            )
        ),
    )
    monkeypatch.setattr(
        automation,
        "invoke_uia_file_menu_item",
        lambda *_: pytest.fail(
            "Slow fallback не нужен на fast path"
        ),
    )
    timings: dict[str, float] = {}

    assert automation.open_save_as_dialog(
        123,
        timings=timings,
    ) == 700
    expected_keys = {
        "open_save_as_cached_win32_command",
        "open_save_as_scan_win32_menu",
        "open_save_as_send_wm_command",
        "open_save_as_wait_dialog_win32",
        "open_save_as_uia_fast_path",
        "open_save_as_legacy_fallback",
        "open_save_as_fresh_main_wrapper",
        "open_save_as_find_file_menu",
        "open_save_as_invoke_file_menu",
        "open_save_as_find_popup_menu",
        "open_save_as_find_save_as_item",
        "open_save_as_get_item_rect",
        "open_save_as_raw_mouse_click",
        "open_save_as_wait_dialog",
        "open_save_as_total",
        "open_save_as_dialog",
    }
    assert expected_keys <= timings.keys()
    assert all(
        timings[key] >= 0.0
        for key in expected_keys
    )


class FakeValuePattern:
    def __init__(
        self,
        edit,
        events: list[str],
    ) -> None:
        self.edit = edit
        self.events = events

    @property
    def CurrentValue(self) -> str:
        return self.edit.value

    def SetValue(self, value: str) -> None:
        self.events.append("value_pattern")
        self.edit.value = value


class FakeSaveAsEdit:
    def __init__(
        self,
        events: list[str],
        *,
        set_edit_error: bool = False,
    ) -> None:
        self.events = events
        self.value = ""
        self.handle = 202
        self.element_info = type(
            "ElementInfo",
            (),
            {
                "handle": 202,
            },
        )()
        self.iface_value = FakeValuePattern(
            self,
            events,
        )
        self.set_edit_error = set_edit_error

    def set_focus(self) -> None:
        self.events.append("focus")

    def set_edit_text(self, value: str) -> None:
        self.events.append("set_edit_text")

        if self.set_edit_error:
            raise RuntimeError(
                "set_edit_text unavailable"
            )

        self.value = value

    def set_value(self, value: str) -> None:
        self.events.append("set_value")
        self.value = value

    def get_value(self) -> str:
        return self.value

    def window_text(self) -> str:
        return self.value


def test_set_save_as_path_uses_uia_value_pattern(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "variant.EMB"
    events: list[str] = []
    edit = FakeSaveAsEdit(
        events,
        set_edit_error=True,
    )
    monkeypatch.setattr(
        automation,
        "find_uia_save_as_edit",
        lambda *_: edit,
    )
    monkeypatch.setattr(
        automation,
        "find_win32_save_as_edit",
        lambda *_: (
            None,
            202,
        ),
    )
    monkeypatch.setattr(
        automation,
        "read_save_as_field_values",
        lambda uia_edit, _hwnd: {
            "UIA value": uia_edit.value,
            "raw GetWindowText": "",
        },
    )

    result = automation.set_save_as_path(
        500,
        output_path,
    )

    assert result == 202
    assert "value_pattern" in events
    assert edit.value == str(
        output_path.resolve()
    )


def test_raw_empty_is_allowed_when_uia_value_is_correct(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "variant.EMB"
    readings = {
        "UIA value": str(output_path.resolve()),
        "raw GetWindowText": "",
    }

    assert automation.accepted_save_as_value(
        readings,
        output_path,
    ) == str(output_path.resolve())


def test_save_as_value_accepts_full_path_and_name(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "variant.EMB"

    assert automation.save_as_value_matches(
        str(output_path.resolve()),
        output_path,
    )
    assert automation.save_as_value_matches(
        output_path.name,
        output_path,
    )


def test_save_as_value_rejects_old_working_name(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "variant.EMB"

    assert not automation.save_as_value_matches(
        "Ghost_debug__groupwork_123.EMB",
        output_path,
    )


def test_set_save_as_path_falls_back_to_win32_wrapper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "variant.EMB"
    state = {
        "value": "",
    }

    class FakeWin32Edit:
        def set_edit_text(
            self,
            value: str,
        ) -> None:
            state["value"] = value

    monkeypatch.setattr(
        automation,
        "find_uia_save_as_edit",
        lambda *_: None,
    )
    monkeypatch.setattr(
        automation,
        "find_win32_save_as_edit",
        lambda *_: (
            FakeWin32Edit(),
            202,
        ),
    )
    monkeypatch.setattr(
        automation,
        "read_save_as_field_values",
        lambda *_: {
            "Win32 wrapper text": state["value"],
            "raw GetWindowText": "",
        },
    )
    monkeypatch.setattr(
        automation.win32gui,
        "SendMessageTimeout",
        lambda *_: pytest.fail(
            "WM_SETTEXT не должен понадобиться"
        ),
    )

    assert automation.set_save_as_path(
        500,
        output_path,
    ) == 202


def test_set_save_as_path_falls_back_to_wm_settext(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "variant.EMB"
    state = {
        "value": "",
    }
    messages: list[tuple[object, ...]] = []

    class FailingWin32Edit:
        def set_edit_text(
            self,
            _value: str,
        ) -> None:
            raise RuntimeError("win32 unavailable")

    def send_message(*args: object) -> None:
        messages.append(args)
        state["value"] = str(args[3])

    monkeypatch.setattr(
        automation,
        "find_uia_save_as_edit",
        lambda *_: None,
    )
    monkeypatch.setattr(
        automation,
        "find_win32_save_as_edit",
        lambda *_: (
            FailingWin32Edit(),
            202,
        ),
    )
    monkeypatch.setattr(
        automation,
        "read_save_as_field_values",
        lambda *_: {
            "raw GetWindowText": state["value"],
        },
    )
    monkeypatch.setattr(
        automation.win32gui,
        "SendMessageTimeout",
        send_message,
    )

    assert automation.set_save_as_path(
        500,
        output_path,
    ) == 202
    assert messages[0][0:4] == (
        202,
        automation.win32con.WM_SETTEXT,
        0,
        str(output_path.resolve()),
    )


def test_find_uia_edit_uses_file_name_control_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []
    edit = object()

    class EditSpecification:
        def exists(
            self,
            timeout: float,
            retry_interval: float,
        ) -> bool:
            events.append(
                (
                    "exists",
                    timeout,
                    retry_interval,
                )
            )
            return True

        def wrapper_object(self):
            return edit

    class HostSpecification:
        def child_window(self, **kwargs):
            events.append(
                (
                    "edit",
                    kwargs,
                )
            )
            return EditSpecification()

    class DialogSpecification:
        def child_window(self, **kwargs):
            events.append(
                (
                    "host",
                    kwargs,
                )
            )
            return HostSpecification()

    class FakeDesktop:
        def window(self, handle: int):
            assert handle == 500
            return DialogSpecification()

    monkeypatch.setattr(
        automation,
        "Desktop",
        lambda backend: (
            FakeDesktop()
            if backend == "uia"
            else pytest.fail("Ожидался UIA")
        ),
    )

    assert automation.find_uia_save_as_edit(
        500,
        timeout=3.0,
    ) is edit
    assert events[0] == (
        "host",
        {
            "auto_id": "FileNameControlHost",
            "control_type": "ComboBox",
        },
    )
    assert events[1] == (
        "edit",
        {
            "auto_id": "1001",
            "control_type": "Edit",
        },
    )


def test_save_document_as_cancels_dialog_and_keeps_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "variant.EMB"
    original_error = RuntimeError(
        "field failed"
    )
    events: list[object] = []
    monkeypatch.setattr(
        automation,
        "open_save_as_dialog",
        lambda hwnd, timeout: (
            events.append(
                (
                    "open",
                    hwnd,
                    timeout,
                )
            )
            or 500
        ),
    )
    monkeypatch.setattr(
        automation,
        "set_save_as_path",
        lambda hwnd, path, timeout: (
            events.append(
                (
                    "set",
                    hwnd,
                    path,
                    timeout,
                )
            )
            or (_ for _ in ()).throw(
                original_error
            )
        ),
    )
    monkeypatch.setattr(
        automation,
        "confirm_save_as",
        lambda *_args, **_kwargs: pytest.fail(
            "confirm не должен вызываться"
        ),
    )
    monkeypatch.setattr(
        automation,
        "cancel_save_as_best_effort",
        lambda hwnd, timeout: events.append(
            (
                "cancel",
                hwnd,
                timeout,
            )
        ),
    )

    with pytest.raises(RuntimeError) as captured:
        automation.save_document_as(
            123,
            output_path,
        )

    assert captured.value is original_error
    assert events == [
        (
            "open",
            123,
            5.0,
        ),
        (
            "set",
            500,
            output_path.resolve(),
            3.0,
        ),
        (
            "cancel",
            500,
            3.0,
        ),
    ]


def test_cancel_save_as_clicks_control_id_2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exists = {
        "value": True,
    }
    messages: list[tuple[int, int]] = []
    monkeypatch.setattr(
        automation.win32gui,
        "IsWindow",
        lambda _: exists["value"],
    )
    monkeypatch.setattr(
        automation,
        "cancel_owned_confirmation_best_effort",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        automation,
        "find_visible_child_by_control_id",
        lambda parent, control_id, class_name: (
            [502]
            if (
                parent == 500
                and control_id
                == automation.win32con.IDCANCEL
                and class_name == "Button"
            )
            else []
        ),
    )

    def post_message(
        hwnd: int,
        message: int,
        *_: object,
    ) -> None:
        messages.append(
            (
                hwnd,
                message,
            )
        )
        exists["value"] = False

    monkeypatch.setattr(
        automation.win32gui,
        "PostMessage",
        post_message,
    )

    automation.cancel_save_as_best_effort(
        500,
        timeout=3.0,
    )

    assert messages == [
        (
            502,
            automation.win32con.BM_CLICK,
        )
    ]


def test_hidden_save_as_hwnd_is_not_considered_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        automation.win32gui,
        "IsWindow",
        lambda _: True,
    )
    monkeypatch.setattr(
        automation.win32gui,
        "IsWindowVisible",
        lambda _: False,
    )

    assert not automation.window_is_closed(
        500
    )


def test_cancel_save_as_falls_back_to_escape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exists = {
        "value": True,
    }
    messages: list[tuple[int, int, int]] = []
    monkeypatch.setattr(
        automation.win32gui,
        "IsWindow",
        lambda _: exists["value"],
    )
    monkeypatch.setattr(
        automation,
        "cancel_owned_confirmation_best_effort",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        automation,
        "find_visible_child_by_control_id",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        automation.win32gui,
        "SetForegroundWindow",
        lambda _: None,
    )

    def post_message(
        hwnd: int,
        message: int,
        key: int,
        _lparam: int,
    ) -> None:
        messages.append(
            (
                hwnd,
                message,
                key,
            )
        )

        if message == automation.win32con.WM_KEYUP:
            exists["value"] = False

    monkeypatch.setattr(
        automation.win32gui,
        "PostMessage",
        post_message,
    )

    automation.cancel_save_as_best_effort(
        500,
        timeout=3.0,
    )

    assert messages == [
        (
            500,
            automation.win32con.WM_KEYDOWN,
            automation.win32con.VK_ESCAPE,
        ),
        (
            500,
            automation.win32con.WM_KEYUP,
            automation.win32con.VK_ESCAPE,
        ),
    ]


def test_confirm_does_not_click_save_for_old_file_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "variant.EMB"
    monkeypatch.setattr(
        automation,
        "verify_save_as_path",
        lambda *_args, **_kwargs: (
            (_ for _ in ()).throw(
                RuntimeError(
                    "Ghost_debug__groupwork.EMB"
                )
            )
        ),
    )
    monkeypatch.setattr(
        automation.win32gui,
        "PostMessage",
        lambda *_: pytest.fail(
            "Save нельзя нажимать со старым именем"
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="groupwork",
    ):
        automation.confirm_save_as(
            500,
            output_path,
            123,
            timeout=1.0,
        )


class FakeSaveAsClock:
    def __init__(self) -> None:
        self.value = 0.0

    def time(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


def configure_confirm_save_as(
    monkeypatch: pytest.MonkeyPatch,
    title: str,
) -> tuple[list[int], FakeSaveAsClock]:
    posted: list[int] = []
    clock = FakeSaveAsClock()
    monkeypatch.setattr(
        automation,
        "verify_save_as_path",
        lambda _dialog, output, timeout: (
            output.name
        ),
    )
    monkeypatch.setattr(
        automation,
        "find_visible_child_by_control_id",
        lambda parent, control_id, class_name: (
            [201]
            if (
                parent == 500
                and control_id == 1
                and class_name == "Button"
            )
            else []
        ),
    )
    monkeypatch.setattr(
        automation.win32gui,
        "PostMessage",
        lambda hwnd, *_: posted.append(hwnd),
    )
    monkeypatch.setattr(
        automation,
        "find_overwrite_confirmation",
        lambda *_: None,
    )
    monkeypatch.setattr(
        automation,
        "window_is_closed",
        lambda _: True,
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetWindowText",
        lambda _: title,
    )
    monkeypatch.setattr(
        automation.time,
        "time",
        clock.time,
    )
    monkeypatch.setattr(
        automation.time,
        "sleep",
        clock.sleep,
    )

    return posted, clock


def test_confirm_save_as_accepts_stable_nonzero_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "variant.EMB"
    output_path.write_bytes(b"saved")
    posted, _ = configure_confirm_save_as(
        monkeypatch,
        "Wilcom - [variant]",
    )

    automation.confirm_save_as(
        500,
        output_path,
        123,
        timeout=1.0,
    )

    assert posted == [201]


def test_confirm_save_as_records_wait_timings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "variant.EMB"
    output_path.write_bytes(b"saved")
    configure_confirm_save_as(
        monkeypatch,
        "Wilcom - [variant]",
    )
    perf_values = iter(
        [
            10.0,
            10.01,
            10.02,
            10.03,
            10.23,
        ]
    )
    monkeypatch.setattr(
        automation.time,
        "perf_counter",
        lambda: next(perf_values),
    )
    timings: dict[str, float] = {}

    automation.confirm_save_as(
        500,
        output_path,
        123,
        timeout=1.0,
        timings=timings,
    )

    assert set(timings) == {
        "click_save",
        "wait_save_dialog_closed",
        "wait_new_title",
        "wait_output_file",
        "wait_stable_size",
    }
    assert timings["click_save"] == pytest.approx(
        0.01
    )
    assert timings["wait_stable_size"] == pytest.approx(
        0.2
    )


def test_save_document_as_records_open_and_path_timings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "variant.EMB"
    perf_values = iter(
        [
            1.0,
            1.1,
            2.0,
            2.2,
        ]
    )
    monkeypatch.setattr(
        automation.time,
        "perf_counter",
        lambda: next(perf_values),
    )
    monkeypatch.setattr(
        automation,
        "open_save_as_dialog",
        lambda _hwnd, timeout, timings: 500,
    )
    monkeypatch.setattr(
        automation,
        "set_save_as_path",
        lambda *_args, **_kwargs: None,
    )
    forwarded_timings: list[
        dict[str, float]
    ] = []
    monkeypatch.setattr(
        automation,
        "confirm_save_as",
        lambda *_args, **kwargs: (
            forwarded_timings.append(
                kwargs["timings"]
            )
        ),
    )
    timings: dict[str, float] = {}

    automation.save_document_as(
        123,
        output_path,
        timings=timings,
    )

    assert timings["open_save_as_dialog"] == pytest.approx(
        0.1
    )
    assert timings["set_save_as_path"] == pytest.approx(
        0.2
    )
    assert forwarded_timings == [timings]


def test_save_document_as_without_timings_uses_legacy_confirm_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "variant.EMB"
    monkeypatch.setattr(
        automation.time,
        "perf_counter",
        lambda: pytest.fail(
            "Без timings perf_counter не нужен"
        ),
    )
    monkeypatch.setattr(
        automation,
        "open_save_as_dialog",
        lambda _hwnd, timeout: 500,
    )
    monkeypatch.setattr(
        automation,
        "set_save_as_path",
        lambda *_args, **_kwargs: None,
    )
    confirm_calls: list[
        tuple[int, Path, int, float]
    ] = []

    def legacy_confirm(
        dialog_hwnd: int,
        path: Path,
        main_hwnd: int,
        timeout: float,
    ) -> None:
        confirm_calls.append(
            (
                dialog_hwnd,
                path,
                main_hwnd,
                timeout,
            )
        )

    monkeypatch.setattr(
        automation,
        "confirm_save_as",
        legacy_confirm,
    )

    automation.save_document_as(
        123,
        output_path,
    )

    assert confirm_calls == [
        (
            500,
            output_path.resolve(),
            123,
            10.0,
        )
    ]


def test_confirm_save_as_checks_new_stem_in_title(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "variant.EMB"
    output_path.write_bytes(b"saved")
    configure_confirm_save_as(
        monkeypatch,
        "Wilcom - [old_name]",
    )

    with pytest.raises(
        TimeoutError,
        match="Фактический заголовок",
    ):
        automation.confirm_save_as(
            500,
            output_path,
            123,
            timeout=0.5,
        )


def test_confirm_save_as_requires_existing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "missing.EMB"
    configure_confirm_save_as(
        monkeypatch,
        "Wilcom - [missing]",
    )

    with pytest.raises(
        TimeoutError,
        match="файл не появился",
    ):
        automation.confirm_save_as(
            500,
            output_path,
            123,
            timeout=0.5,
        )


def test_confirm_save_as_rejects_zero_size(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "empty.EMB"
    output_path.touch()
    configure_confirm_save_as(
        monkeypatch,
        "Wilcom - [empty]",
    )

    with pytest.raises(
        TimeoutError,
        match="размер файла равен нулю",
    ):
        automation.confirm_save_as(
            500,
            output_path,
            123,
            timeout=0.5,
        )


def test_confirm_save_as_clicks_overwrite_idyes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "variant.EMB"
    output_path.write_bytes(b"saved")
    posted, _ = configure_confirm_save_as(
        monkeypatch,
        "Wilcom - [variant]",
    )
    monkeypatch.setattr(
        automation,
        "find_overwrite_confirmation",
        lambda *_: (
            600,
            601,
        ),
    )

    automation.confirm_save_as(
        500,
        output_path,
        123,
        timeout=1.0,
    )

    assert posted == [
        201,
        601,
    ]


def test_find_overwrite_confirmation_uses_idyes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_ids: list[int] = []
    monkeypatch.setattr(
        automation.win32gui,
        "EnumWindows",
        lambda callback, data: callback(
            600,
            data,
        ),
    )
    monkeypatch.setattr(
        automation.win32gui,
        "IsWindowVisible",
        lambda _: True,
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetClassName",
        lambda _: "#32770",
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetWindow",
        lambda *_: 500,
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetParent",
        lambda _: 0,
    )

    def get_item(
        _dialog: int,
        control_id: int,
    ) -> int:
        requested_ids.append(control_id)
        return 601

    monkeypatch.setattr(
        automation.win32gui,
        "GetDlgItem",
        get_item,
    )
    monkeypatch.setattr(
        automation.win32gui,
        "GetWindowText",
        lambda _: "Yes",
    )

    assert automation.find_overwrite_confirmation(
        500,
        123,
    ) == (
        600,
        601,
    )
    assert requested_ids == [
        automation.win32con.IDYES
    ]
