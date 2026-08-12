from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "inspect_wilcom_save_as.py"
)
SPEC = importlib.util.spec_from_file_location(
    "inspect_wilcom_save_as_tests",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
inspection = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = inspection
SPEC.loader.exec_module(inspection)


class FakeElementInfo:
    def __init__(
        self,
        name: str,
        control_type: str,
    ) -> None:
        self.name = name
        self.control_type = control_type
        self.automation_id = ""
        self.class_name = ""
        self.handle = 0


class FakeUiaControl:
    def __init__(
        self,
        name: str,
        control_type: str,
    ) -> None:
        self.element_info = FakeElementInfo(
            name,
            control_type,
        )
        self.invocations = 0
        self.clicks: list[dict[str, str]] = []

    def window_text(self) -> str:
        return self.element_info.name

    def get_properties(self) -> dict[str, str]:
        return {}

    def legacy_properties(self) -> dict[str, str]:
        return {}

    def invoke(self) -> None:
        self.invocations += 1

    def click_input(self, **kwargs: str) -> None:
        self.clicks.append(kwargs)


def make_window(
    hwnd: int,
    *,
    pid: int = 10,
    title: str = "",
    class_name: str = "#32770",
    parent_hwnd: int = 0,
    owner_hwnd: int = 0,
) -> inspection.EsWindowSnapshot:
    return inspection.EsWindowSnapshot(
        hwnd=hwnd,
        pid=pid,
        title=title,
        class_name=class_name,
        rectangle=(0, 0, 800, 600),
        parent_hwnd=parent_hwnd,
        owner_hwnd=owner_hwnd,
    )


def test_normalize_menu_text_removes_ampersand() -> None:
    assert (
        inspection.normalize_menu_text(
            "&Save &As"
        )
        == "save as"
    )


def test_normalize_menu_text_removes_ellipsis() -> None:
    assert (
        inspection.normalize_menu_text(
            "Сохранить как..."
        )
        == "сохранить как"
    )


def test_normalize_menu_text_removes_shortcut() -> None:
    assert (
        inspection.normalize_menu_text(
            "Save As...\tCtrl+Shift+S"
        )
        == "save as"
    )


@pytest.mark.parametrize(
    "text",
    [
        "Сохранить как...",
        "&Save As...",
        "Speichern &unter…",
    ],
)
def test_find_localized_save_as_menu_item(
    text: str,
) -> None:
    expected = inspection.MenuItemSnapshot(
        depth=1,
        text=text,
        command_id=321,
        submenu_handle=0,
    )

    assert inspection.find_save_as_menu_item(
        [expected]
    ) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Сохранить",
        "Save",
        "Speichern",
    ],
)
def test_plain_save_is_not_save_as(
    text: str,
) -> None:
    item = inspection.MenuItemSnapshot(
        depth=1,
        text=text,
        command_id=321,
        submenu_handle=0,
    )

    assert inspection.find_save_as_menu_item(
        [item]
    ) is None


def test_invoke_menu_command_posts_wm_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages: list[tuple[int, int, int, int]] = []
    monkeypatch.setattr(
        inspection.win32gui,
        "PostMessage",
        lambda *args: messages.append(args),
    )

    inspection.invoke_menu_command(100, 321)

    assert messages == [
        (
            100,
            inspection.win32con.WM_COMMAND,
            321,
            0,
        )
    ]


def test_enumerate_menu_items_recurses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entries = {
        10: [
            ("&File", -1, 20),
        ],
        20: [
            ("Save", 100, 0),
            ("Save &As...", 101, 0),
        ],
    }
    monkeypatch.setattr(
        inspection.win32gui,
        "GetMenuItemCount",
        lambda menu: len(entries[menu]),
    )
    monkeypatch.setattr(
        inspection.win32gui,
        "GetMenuString",
        lambda menu, position, _flags: (
            entries[menu][position][0]
        ),
        raising=False,
    )
    monkeypatch.setattr(
        inspection.win32gui,
        "GetMenuItemID",
        lambda menu, position: (
            entries[menu][position][1]
        ),
    )
    monkeypatch.setattr(
        inspection.win32gui,
        "GetSubMenu",
        lambda menu, position: (
            entries[menu][position][2]
        ),
    )

    items = inspection.enumerate_menu_items(10)

    assert [
        (
            item.depth,
            item.text,
            item.command_id,
            item.submenu_handle,
        )
        for item in items
    ] == [
        (
            0,
            "&File",
            -1,
            20,
        ),
        (
            1,
            "Save",
            100,
            0,
        ),
        (
            1,
            "Save &As...",
            101,
            0,
        ),
    ]


def test_find_new_dialog_compares_with_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main_window = make_window(
        100,
        class_name="AfxFrameOrView140u",
        title="Wilcom",
    )
    old_dialog = make_window(
        200,
        title="Old dialog",
        owner_hwnd=100,
    )
    new_dialog = make_window(
        300,
        title="Save As",
        owner_hwnd=100,
    )
    before = {
        100: main_window,
        200: old_dialog,
    }

    monkeypatch.setattr(
        inspection,
        "snapshot_top_level_windows",
        lambda: {
            **before,
            300: new_dialog,
        },
    )

    assert inspection.find_new_es_dialog(
        before,
        main_hwnd=100,
        timeout=1.0,
    ) == new_dialog


def test_main_wilcom_window_is_not_a_dialog() -> None:
    main_window = make_window(
        100,
        title="Wilcom EmbroideryStudio",
        class_name="#32770",
    )

    assert inspection.choose_new_es_dialog(
        before=set(),
        current={100: main_window},
        main_hwnd=100,
    ) is None


def test_xtp_frame_shadow_is_not_a_dialog() -> None:
    shadow = make_window(
        200,
        pid=10,
        title="XTPFrameShadow",
        class_name="XTPFrameShadow",
        owner_hwnd=100,
    )

    assert inspection.choose_new_es_dialog(
        before=set(),
        current={200: shadow},
        main_hwnd=100,
    ) is None


def test_dialog_may_belong_to_different_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog = make_window(
        300,
        pid=999,
        title="Save As",
        owner_hwnd=100,
    )
    monkeypatch.setattr(
        inspection,
        "collect_window_texts",
        lambda window: [window.title],
    )

    assert inspection.choose_new_es_dialog(
        before=set(),
        current={300: dialog},
        main_hwnd=100,
    ) == dialog


def test_open_save_as_falls_back_to_uia(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog = make_window(
        300,
        title="Save As",
        owner_hwnd=100,
    )
    calls: list[str] = []
    monkeypatch.setattr(
        inspection,
        "snapshot_top_level_windows",
        lambda: {},
    )
    monkeypatch.setattr(
        inspection.win32gui,
        "GetMenu",
        lambda _: 0,
    )
    monkeypatch.setattr(
        inspection,
        "invoke_save_as_via_uia",
        lambda *_: calls.append("uia") or True,
    )
    monkeypatch.setattr(
        inspection,
        "invoke_save_design_toolbar",
        lambda *_: pytest.fail(
            "Toolbar не должен вызываться"
        ),
    )
    monkeypatch.setattr(
        inspection,
        "find_new_es_dialog",
        lambda *_args, **_kwargs: dialog,
    )

    assert inspection.open_save_as_dialog(
        100,
        timeout=1.0,
    ) == dialog
    assert calls == ["uia"]


def test_open_save_as_falls_back_to_toolbar_right_click(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialog = make_window(
        300,
        title="Save As",
        owner_hwnd=100,
    )
    calls: list[str] = []
    monkeypatch.setattr(
        inspection,
        "snapshot_top_level_windows",
        lambda: {},
    )
    monkeypatch.setattr(
        inspection.win32gui,
        "GetMenu",
        lambda _: 0,
    )
    monkeypatch.setattr(
        inspection,
        "invoke_save_as_via_uia",
        lambda *_: False,
    )
    monkeypatch.setattr(
        inspection,
        "invoke_save_design_toolbar",
        lambda *_: calls.append("right") or True,
    )
    monkeypatch.setattr(
        inspection,
        "find_new_es_dialog",
        lambda *_args, **_kwargs: dialog,
    )

    assert inspection.open_save_as_dialog(
        100,
        timeout=1.0,
    ) == dialog
    assert calls == ["right"]


def test_uia_fallback_opens_file_then_save_as(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    menu_bar = FakeUiaControl(
        "Application",
        "MenuBar",
    )
    file_item = FakeUiaControl(
        "File",
        "MenuItem",
    )
    save_as_item = FakeUiaControl(
        "Save As...",
        "MenuItem",
    )
    snapshots = iter(
        (
            [menu_bar, file_item],
            [
                menu_bar,
                file_item,
                save_as_item,
            ],
        )
    )
    monkeypatch.setattr(
        inspection,
        "collect_uia_controls",
        lambda _: next(snapshots),
    )
    monkeypatch.setattr(
        inspection.time,
        "sleep",
        lambda _: None,
    )
    diagnostics = inspection.SaveAsDiagnostics()

    assert inspection.invoke_save_as_via_uia(
        100,
        diagnostics,
    )
    assert diagnostics.uia_menu_bar_found
    assert file_item.invocations == 1
    assert save_as_item.invocations == 1


def test_toolbar_fallback_uses_right_click(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    save_design = FakeUiaControl(
        "Save Design",
        "Button",
    )
    monkeypatch.setattr(
        inspection,
        "collect_uia_controls",
        lambda _: [save_design],
    )
    diagnostics = inspection.SaveAsDiagnostics()

    assert inspection.invoke_save_design_toolbar(
        100,
        diagnostics,
    )
    assert save_design.clicks == [
        {
            "button": "right",
        }
    ]


def test_ctrl_shift_s_is_not_available_as_primary_method() -> None:
    assert not hasattr(
        inspection,
        "send_ctrl_shift_virtual_key",
    )


@pytest.mark.parametrize(
    "button_text",
    [
        "Отмена",
        "Cancel",
        "Abbrechen",
    ],
)
def test_find_localized_cancel_button(
    button_text: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    texts = {
        201: "Save",
        202: button_text,
    }

    def enum_children(
        _dialog_hwnd: int,
        callback,
        data,
    ) -> None:
        for hwnd in texts:
            callback(hwnd, data)

    monkeypatch.setattr(
        inspection.win32gui,
        "EnumChildWindows",
        enum_children,
    )
    monkeypatch.setattr(
        inspection.win32gui,
        "GetClassName",
        lambda _: "Button",
    )
    monkeypatch.setattr(
        inspection.win32gui,
        "GetWindowText",
        lambda hwnd: texts[hwnd],
    )

    assert inspection.find_dialog_button(
        500
    ) == 202


def test_cancel_dialog_falls_back_to_escape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages: list[tuple[int, int, int]] = []

    monkeypatch.setattr(
        inspection,
        "find_dialog_button",
        lambda *_: None,
    )
    monkeypatch.setattr(
        inspection.win32gui,
        "SetForegroundWindow",
        lambda _: None,
    )
    monkeypatch.setattr(
        inspection.win32gui,
        "PostMessage",
        lambda hwnd, message, wparam, _lparam: (
            messages.append(
                (
                    hwnd,
                    message,
                    wparam,
                )
            )
        ),
    )
    monkeypatch.setattr(
        inspection,
        "dialog_is_closed",
        lambda _: True,
    )

    assert inspection.cancel_dialog(500)
    assert messages == [
        (
            500,
            inspection.win32con.WM_KEYDOWN,
            inspection.win32con.VK_ESCAPE,
        ),
        (
            500,
            inspection.win32con.WM_KEYUP,
            inspection.win32con.VK_ESCAPE,
        ),
    ]


def test_cancel_dialog_never_clicks_save(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    texts = {
        201: "Save",
        202: "Cancel",
    }
    clicked: list[int] = []

    def enum_children(
        _dialog_hwnd: int,
        callback,
        data,
    ) -> None:
        for hwnd in texts:
            callback(hwnd, data)

    monkeypatch.setattr(
        inspection.win32gui,
        "EnumChildWindows",
        enum_children,
    )
    monkeypatch.setattr(
        inspection.win32gui,
        "GetClassName",
        lambda _: "Button",
    )
    monkeypatch.setattr(
        inspection.win32gui,
        "GetWindowText",
        lambda hwnd: texts[hwnd],
    )
    monkeypatch.setattr(
        inspection.win32gui,
        "PostMessage",
        lambda hwnd, message, *_: (
            clicked.append(hwnd)
            if message == inspection.win32con.BM_CLICK
            else None
        ),
    )
    monkeypatch.setattr(
        inspection,
        "dialog_is_closed",
        lambda _: True,
    )

    assert inspection.cancel_dialog(500)
    assert clicked == [202]
    assert 201 not in clicked


def test_diagnostic_closes_source_without_saving(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_path = tmp_path / "Ghost_debug.EMB"
    file_path.write_bytes(b"EMB")
    events: list[object] = []
    dialog = make_window(
        500,
        title="Save As",
        owner_hwnd=100,
    )

    class FakeWindow:
        def set_focus(self) -> None:
            events.append("set_focus")

    class FakeDesktop:
        def window(self, handle: int) -> FakeWindow:
            assert handle == 100
            return FakeWindow()

    monkeypatch.setattr(
        inspection,
        "find_es_exe",
        lambda _: Path("ES.EXE"),
    )
    monkeypatch.setattr(
        inspection.os,
        "startfile",
        lambda path: events.append(
            (
                "open",
                path,
            )
        ),
    )
    monkeypatch.setattr(
        inspection,
        "raise_for_known_open_error_dialog",
        lambda: None,
    )
    monkeypatch.setattr(
        inspection,
        "wait_for_es_main_window",
        lambda timeout: 100,
    )
    monkeypatch.setattr(
        inspection,
        "wait_for_document_open",
        lambda *_, **__: "Wilcom - [Ghost_debug]",
    )
    monkeypatch.setattr(
        inspection,
        "Desktop",
        lambda backend: (
            FakeDesktop()
            if backend == "uia"
            else pytest.fail("Неожиданный backend")
        ),
    )
    monkeypatch.setattr(
        inspection,
        "focus_window",
        lambda hwnd: events.append(
            (
                "focus",
                hwnd,
            )
        ),
    )
    monkeypatch.setattr(
        inspection,
        "open_save_as_dialog",
        lambda hwnd, timeout: (
            events.append(
                (
                    "open_save_as",
                    hwnd,
                    timeout,
                )
            )
            or dialog
        ),
    )
    monkeypatch.setattr(
        inspection,
        "print_dialog_header",
        lambda _: None,
    )
    monkeypatch.setattr(
        inspection,
        "describe_win32_children",
        lambda _: [],
    )
    monkeypatch.setattr(
        inspection,
        "describe_pywinauto_backend",
        lambda *_: None,
    )
    monkeypatch.setattr(
        inspection,
        "cancel_dialog",
        lambda hwnd, timeout: (
            events.append(
                (
                    "cancel",
                    hwnd,
                )
            )
            or True
        ),
    )
    monkeypatch.setattr(
        inspection,
        "close_document_and_wait",
        lambda _window, hwnd, stem, timeout, save: (
            events.append(
                (
                    "close",
                    hwnd,
                    stem,
                    timeout,
                    save,
                )
            )
            or "Wilcom - No Design"
        ),
    )
    monkeypatch.setattr(
        inspection,
        "close_document_best_effort",
        lambda *_args, **_kwargs: pytest.fail(
            "Успешный путь не должен требовать cleanup"
        ),
    )
    monkeypatch.setattr(
        inspection.time,
        "sleep",
        lambda _: None,
    )

    result = inspection.inspect_save_as(
        file_path,
    )

    assert result == dialog
    assert (
        "close",
        100,
        "Ghost_debug",
        20.0,
        False,
    ) in events
    assert (
        "open_save_as",
        100,
        15.0,
    ) in events
    assert not any(
        isinstance(event, tuple)
        and event[0] == "save"
        for event in events
    )
