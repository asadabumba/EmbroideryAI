from __future__ import annotations

import argparse
import ctypes
import os
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import win32con
import win32gui
import win32process
from pywinauto import Desktop


TESTS_DIR = Path(__file__).resolve().parent

if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from automate_wilcom_file import (
    close_document_and_wait,
    close_document_best_effort,
    find_es_exe,
    focus_window,
    is_es_process_window,
    raise_for_known_open_error_dialog,
    wait_for_document_open,
    wait_for_es_main_window,
)


CANCEL_BUTTON_TEXTS = {
    "отмена",
    "cancel",
    "abbrechen",
}
SAVE_BUTTON_TEXTS = {
    "сохранить",
    "save",
    "speichern",
}
FILE_NAME_TEXTS = {
    "имя файла",
    "file name",
    "dateiname",
}
FILE_TYPE_TEXTS = {
    "тип файла",
    "file type",
    "dateityp",
}
PATH_TEXTS = {
    "путь",
    "адрес",
    "path",
    "address",
    "speicherort",
    "adresse",
}
SAVE_AS_MENU_TEXTS = {
    "сохранить как",
    "save as",
    "speichern unter",
}
FILE_MENU_TEXTS = {
    "файл",
    "file",
    "datei",
}
SAVE_DESIGN_TEXTS = {
    "сохранить дизайн",
    "save design",
    "speichern",
}
SAVE_WORDS = {
    "сохран",
    "save",
    "speicher",
}


@dataclass(frozen=True)
class EsWindowSnapshot:
    hwnd: int
    pid: int
    title: str
    class_name: str
    rectangle: tuple[int, int, int, int]
    parent_hwnd: int
    owner_hwnd: int


@dataclass(frozen=True)
class MenuItemSnapshot:
    depth: int
    text: str
    command_id: int
    submenu_handle: int


@dataclass
class SaveAsDiagnostics:
    menu_items: list[MenuItemSnapshot] = field(
        default_factory=list
    )
    uia_menu_bar_found: bool = False
    uia_save_elements: list[str] = field(
        default_factory=list
    )
    toolbar_save_elements: list[str] = field(
        default_factory=list
    )
    attempts: list[str] = field(default_factory=list)
    new_windows: list[EsWindowSnapshot] = field(
        default_factory=list
    )


@dataclass(frozen=True)
class Win32ControlSnapshot:
    hwnd: int
    depth: int
    class_name: str
    window_text: str
    control_id: int
    automation_id: str
    control_type: str
    enabled: bool
    visible: bool
    rectangle: tuple[int, int, int, int]
    possible_roles: tuple[str, ...]


def normalize_menu_text(text: str) -> str:
    """Нормализует локализованный текст пункта меню."""

    without_shortcut = text.split("\t", 1)[0]

    return (
        without_shortcut.replace("&", "")
        .replace("...", "")
        .replace("…", "")
        .strip()
        .casefold()
    )


def get_menu_string(
    menu_handle: int,
    position: int,
) -> str:
    """Читает текст меню через pywin32 либо GetMenuStringW."""

    pywin32_getter = getattr(
        win32gui,
        "GetMenuString",
        None,
    )

    if pywin32_getter is not None:
        return pywin32_getter(
            menu_handle,
            position,
            win32con.MF_BYPOSITION,
        )

    buffer = ctypes.create_unicode_buffer(2048)
    length = ctypes.windll.user32.GetMenuStringW(
        menu_handle,
        position,
        buffer,
        len(buffer),
        win32con.MF_BYPOSITION,
    )

    if length <= 0:
        return ""

    return buffer.value[:length]


def enumerate_menu_items(
    menu_handle: int,
    depth: int = 0,
) -> list[MenuItemSnapshot]:
    """Рекурсивно перечисляет пункты стандартного Win32-меню."""

    if not menu_handle:
        return []

    items: list[MenuItemSnapshot] = []
    count = win32gui.GetMenuItemCount(menu_handle)

    for position in range(max(0, count)):
        text = get_menu_string(
            menu_handle,
            position,
        )
        submenu_handle = (
            win32gui.GetSubMenu(
                menu_handle,
                position,
            )
            or 0
        )
        command_id = win32gui.GetMenuItemID(
            menu_handle,
            position,
        )
        item = MenuItemSnapshot(
            depth=depth,
            text=text,
            command_id=command_id,
            submenu_handle=submenu_handle,
        )
        items.append(item)

        if submenu_handle:
            items.extend(
                enumerate_menu_items(
                    submenu_handle,
                    depth=depth + 1,
                )
            )

    return items


def print_menu_structure(
    menu_items: list[MenuItemSnapshot],
) -> None:
    print()
    print("=== Win32 menu ===")

    if not menu_items:
        print("<стандартное Win32-меню не найдено>")
        return

    for item in menu_items:
        indent = "  " * item.depth
        print(
            f"{indent}DEPTH={item.depth} "
            f"TEXT={item.text!r} "
            f"COMMAND_ID={item.command_id} "
            f"SUBMENU={item.submenu_handle}"
        )


def find_save_as_menu_item(
    menu_items: list[MenuItemSnapshot],
) -> MenuItemSnapshot | None:
    for item in menu_items:
        if (
            normalize_menu_text(item.text)
            in SAVE_AS_MENU_TEXTS
            and item.command_id not in (-1, 0xFFFFFFFF)
        ):
            return item

    return None


def invoke_menu_command(
    main_hwnd: int,
    command_id: int,
) -> None:
    win32gui.PostMessage(
        main_hwnd,
        win32con.WM_COMMAND,
        command_id,
        0,
    )


def snapshot_top_level_windows(
) -> dict[int, EsWindowSnapshot]:
    """Снимает все видимые top-level окна независимо от PID."""

    snapshots: dict[int, EsWindowSnapshot] = {}

    def callback(hwnd: int, _) -> None:
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return

            _, pid = (
                win32process.GetWindowThreadProcessId(
                    hwnd
                )
            )
            title = win32gui.GetWindowText(hwnd)
            class_name = win32gui.GetClassName(hwnd)
            rectangle = win32gui.GetWindowRect(hwnd)
            parent_hwnd = win32gui.GetParent(hwnd) or 0
            owner_hwnd = (
                win32gui.GetWindow(
                    hwnd,
                    win32con.GW_OWNER,
                )
                or 0
            )
        except Exception:
            return

        snapshots[hwnd] = EsWindowSnapshot(
            hwnd=hwnd,
            pid=pid,
            title=title,
            class_name=class_name,
            rectangle=rectangle,
            parent_hwnd=parent_hwnd,
            owner_hwnd=owner_hwnd,
        )

    win32gui.EnumWindows(
        callback,
        None,
    )

    return snapshots


def snapshot_es_windows(
) -> dict[int, EsWindowSnapshot]:
    """Совместимый snapshot только окон ES.EXE."""

    return {
        hwnd: snapshot
        for hwnd, snapshot
        in snapshot_top_level_windows().items()
        if safe_call(
            lambda hwnd=hwnd: is_es_process_window(
                hwnd
            ),
            False,
        )
    }


def is_dialog_candidate(
    window: EsWindowSnapshot,
    main_hwnd: int,
) -> bool:
    if window.hwnd == main_hwnd:
        return False

    if (
        window.title.strip() == "XTPFrameShadow"
        or window.class_name == "XTPFrameShadow"
    ):
        return False

    if window.class_name == "#32768":
        # Выпадающее системное меню, а не Save As.
        return False

    # Save As обычно имеет #32770 или owner=main_hwnd, но
    # системный диалог может иметь другой PID и класс.
    return True


def collect_window_texts(
    window: EsWindowSnapshot,
) -> list[str]:
    texts = [window.title]

    def callback(child_hwnd: int, _) -> None:
        text = safe_call(
            lambda: win32gui.GetWindowText(
                child_hwnd
            ),
            "",
        )

        if text:
            texts.append(text)

    safe_call(
        lambda: win32gui.EnumChildWindows(
            window.hwnd,
            callback,
            None,
        ),
        None,
    )

    return texts


def save_as_evidence_score(
    window: EsWindowSnapshot,
) -> int:
    normalized_texts = {
        normalize_menu_text(text)
        for text in collect_window_texts(window)
        if text.strip()
    }
    score = 0

    if normalized_texts & SAVE_AS_MENU_TEXTS:
        score += 8

    if any(
        label in text
        for text in normalized_texts
        for label in FILE_NAME_TEXTS
    ):
        score += 4

    if any(
        text_matches_any(
            text,
            SAVE_BUTTON_TEXTS,
        )
        for text in normalized_texts
    ):
        score += 2

    if any(
        text_matches_any(
            text,
            CANCEL_BUTTON_TEXTS,
        )
        for text in normalized_texts
    ):
        score += 2

    return score


def choose_new_es_dialog(
    before: Mapping[int, EsWindowSnapshot] | set[int],
    current: Mapping[int, EsWindowSnapshot],
    main_hwnd: int,
) -> EsWindowSnapshot | None:
    """Выбирает новый диалог, отсутствовавший до команды Save As."""

    if isinstance(before, Mapping):
        previous_windows = {
            (
                hwnd,
                snapshot.pid,
            )
            for hwnd, snapshot in before.items()
        }
    else:
        previous_windows = {
            (
                hwnd,
                None,
            )
            for hwnd in before
        }

    candidates: list[
        tuple[
            int,
            int,
            int,
            int,
            EsWindowSnapshot,
        ]
    ] = []

    for hwnd, snapshot in current.items():
        known = (
            (hwnd, snapshot.pid) in previous_windows
            or (hwnd, None) in previous_windows
        )

        if known or not is_dialog_candidate(
            snapshot,
            main_hwnd,
        ):
            continue

        class_priority = int(
            snapshot.class_name == "#32770"
        )
        owner_priority = int(
            snapshot.owner_hwnd == main_hwnd
            or snapshot.parent_hwnd == main_hwnd
        )
        left, top, right, bottom = snapshot.rectangle
        area = max(0, right - left) * max(
            0,
            bottom - top,
        )
        evidence_priority = save_as_evidence_score(
            snapshot
        )

        if not (
            evidence_priority
            or class_priority
            or owner_priority
        ):
            continue

        candidates.append(
            (
                evidence_priority,
                owner_priority,
                class_priority,
                area,
                snapshot,
            )
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda candidate: candidate[:4],
        reverse=True,
    )

    return candidates[0][4]


def list_new_windows(
    before: Mapping[int, EsWindowSnapshot] | set[int],
    current: Mapping[int, EsWindowSnapshot],
) -> list[EsWindowSnapshot]:
    if isinstance(before, Mapping):
        known = {
            (hwnd, snapshot.pid)
            for hwnd, snapshot in before.items()
        }
    else:
        known = {
            (hwnd, None)
            for hwnd in before
        }

    return [
        snapshot
        for hwnd, snapshot in current.items()
        if (
            (hwnd, snapshot.pid) not in known
            and (hwnd, None) not in known
        )
    ]


def find_new_es_dialog(
    before: Mapping[int, EsWindowSnapshot] | set[int],
    main_hwnd: int,
    timeout: float = 15.0,
) -> EsWindowSnapshot:
    """Ждёт новый видимый Save As независимо от PID."""

    deadline = time.time() + timeout
    last_snapshot: dict[int, EsWindowSnapshot] = {}

    while time.time() < deadline:
        last_snapshot = snapshot_top_level_windows()
        dialog = choose_new_es_dialog(
            before,
            last_snapshot,
            main_hwnd,
        )

        if dialog is not None:
            return dialog

        time.sleep(0.15)

    new_windows = list_new_windows(
        before,
        last_snapshot,
    )
    visible = ", ".join(
        f"{hwnd}:{window.title!r}/{window.class_name!r}"
        for hwnd, window in (
            (window.hwnd, window)
            for window in new_windows
        )
    )
    raise TimeoutError(
        "Новый диалог «Сохранить как» не появился "
        f"за {timeout:g} секунд.\n"
        "Новые видимые top-level окна: "
        f"{visible or '<нет>'}"
    )


def safe_call(
    callback,
    default,
):
    try:
        return callback()
    except Exception:
        return default


def wrapper_text_values(control) -> list[str]:
    values: list[str] = []
    element_info = safe_call(
        lambda: control.element_info,
        None,
    )

    for callback in (
        lambda: control.window_text(),
        lambda: element_info.name,
        lambda: element_info.automation_id,
        lambda: element_info.class_name,
        lambda: element_info.control_type,
    ):
        value = safe_call(callback, "")

        if value:
            values.append(str(value))

    for callback in (
        lambda: control.get_properties(),
        lambda: control.legacy_properties(),
    ):
        properties = safe_call(callback, {})

        if not isinstance(properties, Mapping):
            continue

        for value in properties.values():
            if isinstance(value, str) and value:
                values.append(value)

    return list(dict.fromkeys(values))


def wrapper_control_type(control) -> str:
    return str(
        safe_call(
            lambda: control.element_info.control_type,
            "",
        )
        or ""
    ).casefold()


def describe_uia_control(control) -> str:
    values = wrapper_text_values(control)
    handle = safe_call(
        lambda: int(
            control.element_info.handle or 0
        ),
        0,
    )

    return (
        f"HWND={handle} "
        f"CONTROL_TYPE={wrapper_control_type(control)!r} "
        f"TEXTS={values!r}"
    )


def collect_uia_controls(
    main_hwnd: int,
) -> list[object]:
    """Собирает UIA-контролы главного окна и его popup-окон."""

    desktop = Desktop(backend="uia")
    root_specification = desktop.window(
        handle=main_hwnd
    )
    root = safe_call(
        lambda: root_specification.wrapper_object(),
        root_specification,
    )
    controls: list[object] = [root]
    controls.extend(
        safe_call(
            lambda: root.descendants(),
            [],
        )
    )
    main_pid = safe_call(
        lambda: win32process.GetWindowThreadProcessId(
            main_hwnd
        )[1],
        0,
    )

    for top_window in safe_call(
        lambda: desktop.windows(),
        [],
    ):
        handle = safe_call(
            lambda: int(
                top_window.element_info.handle or 0
            ),
            0,
        )
        process_id = safe_call(
            lambda: int(
                top_window.element_info.process_id or 0
            ),
            0,
        )

        if (
            handle == main_hwnd
            or not main_pid
            or process_id != main_pid
        ):
            continue

        controls.append(top_window)
        controls.extend(
            safe_call(
                lambda: top_window.descendants(),
                [],
            )
        )

    unique: list[object] = []
    seen: set[int] = set()

    for control in controls:
        identity = id(control)

        if identity in seen:
            continue

        seen.add(identity)
        unique.append(control)

    return unique


def control_has_exact_text(
    control,
    expected: set[str],
) -> bool:
    return any(
        normalize_menu_text(value) in expected
        for value in wrapper_text_values(control)
    )


def control_mentions_save(control) -> bool:
    return any(
        any(
            word in normalize_menu_text(value)
            for word in SAVE_WORDS
        )
        for value in wrapper_text_values(control)
    )


def invoke_uia_control(control) -> None:
    try:
        control.invoke()
    except Exception:
        control.click_input()


def invoke_save_as_via_uia(
    main_hwnd: int,
    diagnostics: SaveAsDiagnostics,
) -> bool:
    """Открывает File и вызывает точный Save As через UIA."""

    controls = collect_uia_controls(main_hwnd)
    diagnostics.uia_menu_bar_found = any(
        wrapper_control_type(control) == "menubar"
        for control in controls
    )
    diagnostics.uia_save_elements = [
        describe_uia_control(control)
        for control in controls
        if control_mentions_save(control)
    ]

    save_as_item = next(
        (
            control
            for control in controls
            if (
                wrapper_control_type(control)
                == "menuitem"
                and control_has_exact_text(
                    control,
                    SAVE_AS_MENU_TEXTS,
                )
            )
        ),
        None,
    )

    if save_as_item is not None:
        invoke_uia_control(save_as_item)
        return True

    file_item = next(
        (
            control
            for control in controls
            if (
                wrapper_control_type(control)
                == "menuitem"
                and control_has_exact_text(
                    control,
                    FILE_MENU_TEXTS,
                )
            )
        ),
        None,
    )

    if file_item is None:
        return False

    invoke_uia_control(file_item)
    time.sleep(0.3)
    controls = collect_uia_controls(main_hwnd)
    diagnostics.uia_menu_bar_found = (
        diagnostics.uia_menu_bar_found
        or any(
            wrapper_control_type(control)
            == "menubar"
            for control in controls
        )
    )
    diagnostics.uia_save_elements = list(
        dict.fromkeys(
            [
                *diagnostics.uia_save_elements,
                *(
                    describe_uia_control(control)
                    for control in controls
                    if control_mentions_save(control)
                ),
            ]
        )
    )
    save_as_item = next(
        (
            control
            for control in controls
            if (
                wrapper_control_type(control)
                == "menuitem"
                and control_has_exact_text(
                    control,
                    SAVE_AS_MENU_TEXTS,
                )
            )
        ),
        None,
    )

    if save_as_item is None:
        return False

    invoke_uia_control(save_as_item)
    return True


def invoke_save_design_toolbar(
    main_hwnd: int,
    diagnostics: SaveAsDiagnostics,
) -> bool:
    """Правой кнопкой вызывает Save As с кнопки Save Design."""

    controls = collect_uia_controls(main_hwnd)
    candidates: list[object] = []

    for control in controls:
        if not control_mentions_save(control):
            continue

        description = describe_uia_control(control)
        diagnostics.toolbar_save_elements.append(
            description
        )
        control_type = wrapper_control_type(control)

        if control_type in {
            "menu",
            "menubar",
            "menuitem",
        }:
            continue

        normalized_values = {
            normalize_menu_text(value)
            for value in wrapper_text_values(control)
        }

        if (
            normalized_values & SAVE_DESIGN_TEXTS
            or any(
                "save design" in value
                or "сохранить дизайн" in value
                for value in normalized_values
            )
        ):
            candidates.append(control)

    diagnostics.toolbar_save_elements = list(
        dict.fromkeys(
            diagnostics.toolbar_save_elements
        )
    )

    if not candidates:
        return False

    candidates[0].click_input(
        button="right"
    )
    return True


def format_menu_items(
    menu_items: list[MenuItemSnapshot],
) -> str:
    if not menu_items:
        return "<стандартное Win32-меню не найдено>"

    return "\n".join(
        (
            f"{'  ' * item.depth}"
            f"depth={item.depth} "
            f"text={item.text!r} "
            f"command_id={item.command_id} "
            f"submenu={item.submenu_handle}"
        )
        for item in menu_items
    )


def format_window_list(
    windows: list[EsWindowSnapshot],
) -> str:
    if not windows:
        return "<нет>"

    return "\n".join(
        (
            f"HWND={window.hwnd} PID={window.pid} "
            f"TITLE={window.title!r} "
            f"CLASS={window.class_name!r} "
            f"OWNER={window.owner_hwnd} "
            f"PARENT={window.parent_hwnd}"
        )
        for window in windows
    )


def format_save_as_failure(
    diagnostics: SaveAsDiagnostics,
    timeout: float,
) -> str:
    uia_elements = (
        "\n".join(diagnostics.uia_save_elements)
        or "<нет>"
    )
    toolbar_elements = (
        "\n".join(
            diagnostics.toolbar_save_elements
        )
        or "<нет>"
    )
    attempts = (
        "\n".join(diagnostics.attempts)
        or "<нет доступных способов>"
    )

    return (
        "Диалог «Сохранить как» не появился "
        f"после доступных способов вызова "
        f"(ожидание каждого: {timeout:g} с).\n"
        "\nПолная структура Win32-меню:\n"
        f"{format_menu_items(diagnostics.menu_items)}\n"
        "\nMenuBar через UIA найден: "
        f"{'да' if diagnostics.uia_menu_bar_found else 'нет'}\n"
        "Элементы UIA с Save/Сохранить/Speichern:\n"
        f"{uia_elements}\n"
        "Элементы toolbar с Save/Сохранить/Speichern:\n"
        f"{toolbar_elements}\n"
        "Попытки:\n"
        f"{attempts}\n"
        "Все новые top-level окна независимо от PID:\n"
        f"{format_window_list(diagnostics.new_windows)}"
    )


def open_save_as_dialog(
    main_hwnd: int,
    timeout: float = 15.0,
) -> EsWindowSnapshot:
    """Открывает Save As через Win32 menu, UIA или toolbar."""

    diagnostics = SaveAsDiagnostics()
    initial_windows = snapshot_top_level_windows()
    menu_handle = safe_call(
        lambda: win32gui.GetMenu(main_hwnd),
        0,
    )

    if menu_handle:
        try:
            diagnostics.menu_items = (
                enumerate_menu_items(menu_handle)
            )
        except Exception as error:
            diagnostics.attempts.append(
                "Ошибка чтения Win32-меню: "
                f"{error}"
            )

    print_menu_structure(
        diagnostics.menu_items
    )

    def invoke_and_wait(
        method_description: str,
        callback,
    ) -> EsWindowSnapshot | None:
        before = snapshot_top_level_windows()
        print(
            "Способ открытия Save As:",
            method_description,
        )

        try:
            invoked = callback()
        except Exception as error:
            diagnostics.attempts.append(
                f"{method_description}: ERROR: {error}"
            )
            return None

        if invoked is False:
            diagnostics.attempts.append(
                f"{method_description}: не найден"
            )
            return None

        try:
            return find_new_es_dialog(
                before,
                main_hwnd,
                timeout=timeout,
            )
        except TimeoutError as error:
            diagnostics.attempts.append(
                f"{method_description}: {error}"
            )
            observed = list_new_windows(
                before,
                snapshot_top_level_windows(),
            )
            known_windows = {
                (window.hwnd, window.pid)
                for window in diagnostics.new_windows
            }

            diagnostics.new_windows.extend(
                window
                for window in observed
                if (
                    window.hwnd,
                    window.pid,
                )
                not in known_windows
            )
            return None

    menu_item = find_save_as_menu_item(
        diagnostics.menu_items
    )

    if menu_item is not None:
        dialog = invoke_and_wait(
            "Win32 menu command ID: "
            f"{menu_item.command_id}",
            lambda: invoke_menu_command(
                main_hwnd,
                menu_item.command_id,
            ),
        )

        if dialog is not None:
            return dialog

    dialog = invoke_and_wait(
        "UIA menu item",
        lambda: invoke_save_as_via_uia(
            main_hwnd,
            diagnostics,
        ),
    )

    if dialog is not None:
        return dialog

    dialog = invoke_and_wait(
        "right click Save Design toolbar",
        lambda: invoke_save_design_toolbar(
            main_hwnd,
            diagnostics,
        ),
    )

    if dialog is not None:
        return dialog

    current_windows = snapshot_top_level_windows()
    final_new_windows = list_new_windows(
        initial_windows,
        current_windows,
    )
    known_windows = {
        (window.hwnd, window.pid)
        for window in diagnostics.new_windows
    }
    diagnostics.new_windows.extend(
        window
        for window in final_new_windows
        if (
            window.hwnd,
            window.pid,
        )
        not in known_windows
    )
    raise RuntimeError(
        format_save_as_failure(
            diagnostics,
            timeout,
        )
    )


def calculate_win32_depth(
    hwnd: int,
    root_hwnd: int,
) -> int:
    depth = 1
    current = hwnd
    visited = {hwnd}

    while depth < 100:
        parent = safe_call(
            lambda: win32gui.GetParent(current) or 0,
            0,
        )

        if not parent or parent == root_hwnd:
            return depth

        if parent in visited:
            return depth

        visited.add(parent)
        current = parent
        depth += 1

    return depth


def get_pywinauto_metadata(
    hwnd: int,
) -> tuple[str, str]:
    automation_id = ""
    control_type = ""

    for backend in (
        "win32",
        "uia",
    ):
        try:
            wrapper = Desktop(
                backend=backend
            ).window(
                handle=hwnd
            ).wrapper_object()
            element_info = wrapper.element_info
        except Exception:
            continue

        if not automation_id:
            automation_id = str(
                safe_call(
                    lambda: element_info.automation_id,
                    "",
                )
                or ""
            )

        if not control_type:
            control_type = str(
                safe_call(
                    lambda: element_info.control_type,
                    "",
                )
                or ""
            )

    return automation_id, control_type


def normalize_button_text(
    text: str,
) -> str:
    return (
        text.replace("&", "")
        .strip()
        .casefold()
    )


def text_matches_any(
    text: str,
    candidates: set[str],
) -> bool:
    normalized = normalize_button_text(text)

    return any(
        normalized == candidate
        or normalized.startswith(
            f"{candidate} ("
        )
        for candidate in candidates
    )


def identify_possible_roles(
    class_name: str,
    window_text: str,
    control_id: int,
    automation_id: str,
    control_type: str,
) -> tuple[str, ...]:
    combined = " ".join(
        (
            class_name,
            window_text,
            automation_id,
            control_type,
        )
    ).casefold()
    roles: list[str] = []

    if (
        any(text in combined for text in FILE_NAME_TEXTS)
        or control_id == 1152
    ):
        roles.append("поле имени файла")

    if (
        any(text in combined for text in PATH_TEXTS)
        or "breadcrumb" in combined
        or class_name in {
            "ToolbarWindow32",
            "ComboBoxEx32",
        }
    ):
        roles.append("поле пути / адресная строка")

    if (
        text_matches_any(
            window_text,
            SAVE_BUTTON_TEXTS,
        )
        or (
            control_id == win32con.IDOK
            and "button" in combined
        )
    ):
        roles.append("кнопка «Сохранить»")

    if (
        text_matches_any(
            window_text,
            CANCEL_BUTTON_TEXTS,
        )
        or (
            control_id == win32con.IDCANCEL
            and "button" in combined
        )
    ):
        roles.append("кнопка «Отмена»")

    if (
        any(text in combined for text in FILE_TYPE_TEXTS)
        or control_id == 1136
    ):
        roles.append("тип файла")

    if (
        class_name in {
            "SysListView32",
            "DirectUIHWND",
        }
        or control_type.casefold() in {
            "list",
            "datagrid",
            "tree",
        }
    ):
        roles.append("список файлов")

    return tuple(roles)


def describe_win32_children(
    dialog_hwnd: int,
) -> list[Win32ControlSnapshot]:
    """Печатает рекурсивный Win32 EnumChildWindows snapshot."""

    child_handles: list[int] = []

    def callback(child_hwnd: int, _) -> None:
        child_handles.append(child_hwnd)

    win32gui.EnumChildWindows(
        dialog_hwnd,
        callback,
        None,
    )
    controls: list[Win32ControlSnapshot] = []

    print()
    print("=== Win32 EnumChildWindows ===")

    for child_hwnd in child_handles:
        class_name = safe_call(
            lambda: win32gui.GetClassName(
                child_hwnd
            ),
            "",
        )
        window_text = safe_call(
            lambda: win32gui.GetWindowText(
                child_hwnd
            ),
            "",
        )
        control_id = safe_call(
            lambda: win32gui.GetDlgCtrlID(
                child_hwnd
            ),
            0,
        )
        enabled = bool(
            safe_call(
                lambda: win32gui.IsWindowEnabled(
                    child_hwnd
                ),
                False,
            )
        )
        visible = bool(
            safe_call(
                lambda: win32gui.IsWindowVisible(
                    child_hwnd
                ),
                False,
            )
        )
        rectangle = safe_call(
            lambda: win32gui.GetWindowRect(
                child_hwnd
            ),
            (0, 0, 0, 0),
        )
        automation_id, control_type = (
            get_pywinauto_metadata(
                child_hwnd
            )
        )
        roles = identify_possible_roles(
            class_name,
            window_text,
            control_id,
            automation_id,
            control_type,
        )
        control = Win32ControlSnapshot(
            hwnd=child_hwnd,
            depth=calculate_win32_depth(
                child_hwnd,
                dialog_hwnd,
            ),
            class_name=class_name,
            window_text=window_text,
            control_id=control_id,
            automation_id=automation_id,
            control_type=control_type,
            enabled=enabled,
            visible=visible,
            rectangle=rectangle,
            possible_roles=roles,
        )
        controls.append(control)

        indent = "  " * control.depth
        print(
            f"{indent}HWND={control.hwnd} "
            f"DEPTH={control.depth} "
            f"CLASS={control.class_name!r} "
            f"TEXT={control.window_text!r} "
            f"CONTROL_ID={control.control_id} "
            f"AUTOMATION_ID={control.automation_id!r} "
            f"CONTROL_TYPE={control.control_type!r} "
            f"ENABLED={control.enabled} "
            f"VISIBLE={control.visible} "
            f"RECT={control.rectangle}"
        )

        if roles:
            print(
                f"{indent}  >>> ВОЗМОЖНО: "
                f"{', '.join(roles)}"
            )

    return controls


def calculate_element_depth(
    element_info,
    root_element_info,
) -> int:
    depth = 0
    current = element_info
    visited: set[int] = set()

    while current is not None and depth < 100:
        identity = id(current)

        if identity in visited:
            break

        visited.add(identity)

        if current is root_element_info:
            break

        current = safe_call(
            lambda: current.parent,
            None,
        )
        depth += 1

    return depth


def describe_pywinauto_backend(
    dialog_hwnd: int,
    backend: str,
) -> None:
    """Печатает handle-less элементы выбранного backend."""

    print()
    print(
        f"=== pywinauto backend={backend!r} ==="
    )

    try:
        root = Desktop(
            backend=backend
        ).window(
            handle=dialog_hwnd
        ).wrapper_object()
        descendants = root.descendants()
    except Exception as error:
        print(
            f"Backend {backend!r} недоступен: {error}"
        )
        return

    root_info = root.element_info

    for control in descendants:
        element_info = safe_call(
            lambda: control.element_info,
            None,
        )

        if element_info is None:
            continue

        hwnd = safe_call(
            lambda: int(element_info.handle or 0),
            0,
        )
        class_name = str(
            safe_call(
                lambda: element_info.class_name,
                "",
            )
            or ""
        )
        text = str(
            safe_call(
                control.window_text,
                "",
            )
            or ""
        )
        control_id = int(
            safe_call(
                lambda: element_info.control_id or 0,
                0,
            )
        )
        automation_id = str(
            safe_call(
                lambda: element_info.automation_id,
                "",
            )
            or ""
        )
        control_type = str(
            safe_call(
                lambda: element_info.control_type,
                "",
            )
            or ""
        )
        enabled = bool(
            safe_call(
                control.is_enabled,
                False,
            )
        )
        visible = bool(
            safe_call(
                control.is_visible,
                False,
            )
        )
        rectangle = safe_call(
            lambda: tuple(control.rectangle()),
            (0, 0, 0, 0),
        )
        depth = calculate_element_depth(
            element_info,
            root_info,
        )
        roles = identify_possible_roles(
            class_name,
            text,
            control_id,
            automation_id,
            control_type,
        )
        indent = "  " * max(1, depth)

        print(
            f"{indent}HWND={hwnd} "
            f"DEPTH={depth} "
            f"CLASS={class_name!r} "
            f"TEXT={text!r} "
            f"CONTROL_ID={control_id} "
            f"AUTOMATION_ID={automation_id!r} "
            f"CONTROL_TYPE={control_type!r} "
            f"ENABLED={enabled} "
            f"VISIBLE={visible} "
            f"RECT={rectangle}"
        )

        if roles:
            print(
                f"{indent}  >>> ВОЗМОЖНО: "
                f"{', '.join(roles)}"
            )


def print_dialog_header(
    dialog: EsWindowSnapshot,
) -> None:
    print()
    print("=== Новый диалог Save As ===")
    print("HWND:", dialog.hwnd)
    print("PID:", dialog.pid)
    print("TITLE:", repr(dialog.title))
    print("CLASS:", repr(dialog.class_name))
    print("RECT:", dialog.rectangle)
    print("PARENT HWND:", dialog.parent_hwnd)
    print("OWNER HWND:", dialog.owner_hwnd)


def find_dialog_button(
    dialog_hwnd: int,
    allowed_texts: set[str] | None = None,
) -> int | None:
    """Находит только кнопку с явно разрешённым текстом."""

    allowed = allowed_texts or CANCEL_BUTTON_TEXTS
    matches: list[int] = []

    def callback(child_hwnd: int, _) -> None:
        try:
            class_name = win32gui.GetClassName(
                child_hwnd
            )
            text = win32gui.GetWindowText(
                child_hwnd
            )
        except Exception:
            return

        if (
            class_name == "Button"
            and text_matches_any(
                text,
                allowed,
            )
        ):
            matches.append(child_hwnd)

    win32gui.EnumChildWindows(
        dialog_hwnd,
        callback,
        None,
    )

    return matches[0] if matches else None


def dialog_is_closed(
    dialog_hwnd: int,
) -> bool:
    try:
        return (
            not win32gui.IsWindow(dialog_hwnd)
            or not win32gui.IsWindowVisible(
                dialog_hwnd
            )
        )
    except Exception:
        return True


def cancel_dialog(
    dialog_hwnd: int,
    timeout: float = 5.0,
) -> bool:
    """Нажимает Cancel/Отмена/Abbrechen либо отправляет Escape."""

    cancel_button = find_dialog_button(
        dialog_hwnd,
        CANCEL_BUTTON_TEXTS,
    )

    if cancel_button is not None:
        win32gui.PostMessage(
            cancel_button,
            win32con.BM_CLICK,
            0,
            0,
        )
        print(
            "Диалог отменён найденной кнопкой:",
            cancel_button,
        )
    else:
        try:
            win32gui.SetForegroundWindow(
                dialog_hwnd
            )
        except Exception:
            pass

        win32gui.PostMessage(
            dialog_hwnd,
            win32con.WM_KEYDOWN,
            win32con.VK_ESCAPE,
            0,
        )
        win32gui.PostMessage(
            dialog_hwnd,
            win32con.WM_KEYUP,
            win32con.VK_ESCAPE,
            0,
        )
        print(
            "Кнопка «Отмена» не найдена; отправлен Escape."
        )

    deadline = time.time() + timeout

    while time.time() < deadline:
        if dialog_is_closed(dialog_hwnd):
            return True

        time.sleep(0.05)

    return dialog_is_closed(dialog_hwnd)


def inspect_save_as(
    file_path: Path,
    es_path: Path | None = None,
    timeout: float = 15.0,
) -> EsWindowSnapshot:
    """Открывает исходный EMB и диагностирует Save As без сохранения."""

    file_path = file_path.resolve()

    if not file_path.is_file():
        raise FileNotFoundError(
            f"EMB-файл не найден: {file_path}"
        )

    if file_path.suffix.lower() != ".emb":
        raise ValueError(
            f"Ожидался файл .EMB: {file_path}"
        )

    es_exe = find_es_exe(es_path)
    print("Wilcom:", es_exe)
    print("Открываю:", file_path)

    main_hwnd: int | None = None
    window = None
    document_opened = False
    dialog_hwnd: int | None = None

    try:
        os.startfile(
            str(file_path)
        )
        raise_for_known_open_error_dialog()
        main_hwnd = wait_for_es_main_window(
            timeout=60.0,
        )
        raise_for_known_open_error_dialog()
        active_title = wait_for_document_open(
            main_hwnd,
            file_path,
            timeout=60.0,
        )
        document_opened = True
        time.sleep(0.75)
        raise_for_known_open_error_dialog()

        print("Документ открыт:", repr(active_title))

        window = Desktop(
            backend="uia"
        ).window(
            handle=main_hwnd
        )

        focus_window(main_hwnd)
        window.set_focus()
        dialog = open_save_as_dialog(
            main_hwnd,
            timeout=timeout,
        )
        dialog_hwnd = dialog.hwnd
        print_dialog_header(dialog)
        describe_win32_children(dialog.hwnd)
        describe_pywinauto_backend(
            dialog.hwnd,
            "win32",
        )
        describe_pywinauto_backend(
            dialog.hwnd,
            "uia",
        )

        if not cancel_dialog(
            dialog.hwnd,
            timeout=5.0,
        ):
            raise TimeoutError(
                "Диалог «Сохранить как» не исчез "
                "после команды отмены."
            )

        dialog_hwnd = None
        close_document_and_wait(
            window,
            main_hwnd,
            file_path.stem,
            timeout=20.0,
            save=False,
        )
        document_opened = False
        print(
            "Исходный документ закрыт без сохранения."
        )

        return dialog

    finally:
        if (
            dialog_hwnd is not None
            and not dialog_is_closed(dialog_hwnd)
        ):
            try:
                cancel_dialog(
                    dialog_hwnd,
                    timeout=2.0,
                )
            except Exception:
                pass

        if (
            document_opened
            and main_hwnd is not None
        ):
            close_document_best_effort(
                main_hwnd,
                file_path.stem,
                window=window,
            )


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "file",
        type=Path,
        help="Исходный EMB для диагностики Save As",
    )
    parser.add_argument(
        "--es",
        type=Path,
        help="Необязательный путь к ES.EXE",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="Ожидание нового диалога в секундах",
    )

    return parser


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    if args.timeout <= 0:
        parser.error("--timeout должен быть больше нуля.")

    try:
        inspect_save_as(
            args.file,
            es_path=args.es,
            timeout=args.timeout,
        )
    except KeyboardInterrupt:
        print(
            "Диагностика прервана пользователем.",
            file=sys.stderr,
        )
        raise SystemExit(130)
    except Exception as error:
        print(
            f"ERROR: {error}",
            file=sys.stderr,
        )
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
