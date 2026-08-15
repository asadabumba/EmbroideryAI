import argparse
import ctypes
import os
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

import psutil
import win32api
import win32con
import win32gui
import win32process
from pywinauto import Desktop, keyboard, mouse
from pywinauto.timings import Timings


X_AUTOMATION_ID = "6586"
Y_AUTOMATION_ID = "6587"
OPEN_DESIGN_ERROR_TITLE = "Невозможно открыть дизайн"
SAVE_CHANGES_MARKERS = (
    "сохранить изменения в",
    "save changes to",
    "save changes in",
    "änderungen an",
)
SAVE_BUTTON_TEXTS = {
    True: {"да", "yes", "ja"},
    False: {"нет", "no", "nein"},
}
PREFERRED_WINDOW_TITLE = "Ultimate Special Edition"
DOCUMENT_CANVAS_CLASS = "AfxFrameOrView140u"
FILE_MENU_TEXTS = {
    "файл",
    "file",
    "datei",
}
SAVE_AS_MENU_TEXTS = {
    "сохранить как",
    "save as",
    "speichern unter",
}
SAVE_AS_MENU_CACHE: dict[str, str] = {}
SAVE_AS_MOUSE_CACHE: dict[str, object] = {}
POSITION_CONTROLS_CACHE: dict[
    int,
    tuple[object, object, object, object],
] = {}
_SAVE_AS_WIN32_COMMAND_ID: int | None = None
_SAVE_AS_WIN32_COMMAND_HWND: int | None = None
_SAVE_AS_WIN32_DISABLED_HWNDS: set[int] = set()
FAST_UIA_LOOKUP_TIMEOUT = 1.0
FAST_UIA_POLL_INTERVAL = 0.05
SAVE_AS_DIALOG_TIMEOUT = 5.0
WIN32_CACHED_DIALOG_TIMEOUT = 1.0
WIN32_DIALOG_TIMEOUT = 3.0
WIN32_MENU_MAX_DEPTH = 3
SAVE_AS_DIALOG_TITLES = SAVE_AS_MENU_TEXTS
SAVE_AS_FILE_NAME_CONTROL_ID = 1001
SAVE_AS_BUTTON_CONTROL_ID = 1
OVERWRITE_BUTTON_TEXTS = {
    "да",
    "yes",
    "ja",
}

_LOGGED_CANVAS_HANDLES: set[int] = set()
_LOGGED_SELECTION_METHODS: set[str] = set()
_LOGGED_WIN32_FILE_MENUS: set[int] = set()

_USER32 = ctypes.windll.user32
_USER32.GetMenu.argtypes = [wintypes.HWND]
_USER32.GetMenu.restype = wintypes.HMENU
_USER32.GetMenuItemCount.argtypes = [wintypes.HMENU]
_USER32.GetMenuItemCount.restype = ctypes.c_int
_USER32.GetMenuStringW.argtypes = [
    wintypes.HMENU,
    wintypes.UINT,
    wintypes.LPWSTR,
    ctypes.c_int,
    wintypes.UINT,
]
_USER32.GetMenuStringW.restype = ctypes.c_int
_USER32.GetSubMenu.argtypes = [
    wintypes.HMENU,
    ctypes.c_int,
]
_USER32.GetSubMenu.restype = wintypes.HMENU
_USER32.GetMenuItemID.argtypes = [
    wintypes.HMENU,
    ctypes.c_int,
]
_USER32.GetMenuItemID.restype = wintypes.UINT
_USER32.PostMessageW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
_USER32.PostMessageW.restype = wintypes.BOOL

DEFAULT_ES_EXE = Path(
    r"D:\AAAAAAAAAAA\EmbroideryStudio_e4.2\BIN\ES.EXE"
)


def find_es_exe(explicit_path: Path | None) -> Path:
    """Находит ES.EXE независимо от того, запущен Wilcom или нет."""

    if explicit_path is not None:
        result = explicit_path.resolve()

        if not result.exists():
            raise FileNotFoundError(
                f"ES.EXE не найден: {result}"
            )

        return result

    for process in psutil.process_iter(
        ["name", "exe"]
    ):
        try:
            name = process.info.get("name") or ""
            exe = process.info.get("exe")

            if name.lower() == "es.exe" and exe:
                result = Path(exe)

                if result.exists():
                    return result
        except (
            psutil.NoSuchProcess,
            psutil.AccessDenied,
        ):
            continue

    if DEFAULT_ES_EXE.exists():
        return DEFAULT_ES_EXE

    raise FileNotFoundError(
        "ES.EXE не найден. Передай путь через --es."
    )


def is_es_main_window_candidate(
    title: str,
    class_name: str,
    width: int,
    height: int,
    visible: bool = True,
) -> bool:
    """Фильтрует технические и модальные окна ES.EXE."""

    title = title.strip()

    if not visible:
        return False

    if width < 300 or height < 300:
        return False

    if not title:
        return False

    if title == "XTPFrameShadow":
        return False

    if class_name in {
        "XTPFrameShadow",
        "#32770",
    }:
        return False

    return True


def es_main_window_sort_key(
    title: str,
    area: int,
) -> tuple[int, int]:
    """Отдаёт приоритет известному заголовку главного окна."""

    preferred = (
        PREFERRED_WINDOW_TITLE.casefold()
        in title.casefold()
    )

    return int(preferred), area


def list_es_main_windows() -> list[
    tuple[int, int, int, int, str, str]
]:
    """
    Возвращает все крупные видимые окна ES.EXE:

    preferred, area, hwnd, pid, title, class_name
    """

    results: list[
        tuple[int, int, int, int, str, str]
    ] = []

    def callback(hwnd: int, _) -> None:
        visible = win32gui.IsWindowVisible(hwnd)

        try:
            title = win32gui.GetWindowText(hwnd)
            class_name = win32gui.GetClassName(hwnd)
        except Exception:
            return

        _, pid = win32process.GetWindowThreadProcessId(
            hwnd
        )

        try:
            process_name = (
                psutil.Process(pid)
                .name()
                .lower()
            )
        except (
            psutil.NoSuchProcess,
            psutil.AccessDenied,
        ):
            return

        if process_name != "es.exe":
            return

        left, top, right, bottom = (
            win32gui.GetWindowRect(hwnd)
        )

        width = right - left
        height = bottom - top

        if not is_es_main_window_candidate(
            title=title,
            class_name=class_name,
            width=width,
            height=height,
            visible=visible,
        ):
            return

        area = width * height
        preferred, _ = es_main_window_sort_key(
            title,
            area,
        )

        results.append(
            (
                preferred,
                area,
                hwnd,
                pid,
                title,
                class_name,
            )
        )

    win32gui.EnumWindows(
        callback,
        None,
    )

    results.sort(reverse=True)

    return results


def get_window_texts(hwnd: int) -> list[str]:
    """Собирает заголовок и доступные тексты дочерних окон."""

    texts: list[str] = []

    def add_text(window_hwnd: int) -> None:
        try:
            text = win32gui.GetWindowText(
                window_hwnd
            ).strip()
        except Exception:
            return

        if text and text not in texts:
            texts.append(text)

    add_text(hwnd)

    def callback(child_hwnd: int, _) -> None:
        add_text(child_hwnd)

    try:
        win32gui.EnumChildWindows(
            hwnd,
            callback,
            None,
        )
    except Exception:
        pass

    return texts


def is_es_process_window(hwnd: int) -> bool:
    """Проверяет принадлежность верхнеуровневого окна ES.EXE."""

    try:
        _, pid = win32process.GetWindowThreadProcessId(
            hwnd
        )
        process_name = psutil.Process(pid).name()
    except Exception:
        return False

    return process_name.casefold() == "es.exe"


def is_save_changes_dialog_text(
    texts: list[str],
) -> bool:
    combined = " ".join(texts).casefold()

    return any(
        marker in combined
        for marker in SAVE_CHANGES_MARKERS
    )


def find_save_changes_dialog(
    document_stem: str | None = None,
) -> tuple[int, list[str]] | None:
    """Находит видимый диалог сохранения процесса ES.EXE."""

    matches: list[
        tuple[int, int, int, list[str]]
    ] = []
    expected_stem = (
        document_stem.casefold()
        if document_stem
        else ""
    )

    def callback(hwnd: int, _) -> None:
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return

            if not is_es_process_window(hwnd):
                return

            class_name = win32gui.GetClassName(
                hwnd
            )
            texts = get_window_texts(hwnd)
        except Exception:
            return

        if not is_save_changes_dialog_text(texts):
            return

        combined = " ".join(texts).casefold()
        stem_matches = int(
            bool(expected_stem)
            and expected_stem in combined
        )
        dialog_class = int(
            class_name == "#32770"
        )
        matches.append(
            (
                stem_matches,
                dialog_class,
                hwnd,
                texts,
            )
        )

    win32gui.EnumWindows(
        callback,
        None,
    )

    if not matches:
        return None

    matches.sort(
        key=lambda match: (
            match[0],
            match[1],
        ),
        reverse=True,
    )
    _, _, hwnd, texts = matches[0]

    return hwnd, texts


def find_dialog_button_by_text(
    dialog_hwnd: int,
    allowed_texts: set[str],
) -> int:
    buttons: list[int] = []

    def callback(child_hwnd: int, _) -> None:
        try:
            class_name = win32gui.GetClassName(
                child_hwnd
            )
            text = (
                win32gui.GetWindowText(child_hwnd)
                .replace("&", "")
                .strip()
                .casefold()
            )
        except Exception:
            return

        if (
            class_name == "Button"
            and text in allowed_texts
        ):
            buttons.append(child_hwnd)

    try:
        win32gui.EnumChildWindows(
            dialog_hwnd,
            callback,
            None,
        )
    except Exception:
        return 0

    return buttons[0] if buttons else 0


def dismiss_save_changes_dialog(
    document_stem: str | None,
    save: bool,
    timeout: float = 5.0,
) -> bool:
    """Нажимает только «Да» либо «Нет» и ждёт закрытия диалога."""

    match = find_save_changes_dialog(
        document_stem
    )

    if match is None:
        return False

    dialog_hwnd, _ = match
    button_id = (
        win32con.IDYES
        if save
        else win32con.IDNO
    )
    button_hwnd = 0

    try:
        button_hwnd = win32gui.GetDlgItem(
            dialog_hwnd,
            button_id,
        )
    except Exception:
        pass

    if not button_hwnd:
        button_hwnd = find_dialog_button_by_text(
            dialog_hwnd,
            SAVE_BUTTON_TEXTS[save],
        )

    if not button_hwnd:
        return False

    try:
        win32gui.PostMessage(
            button_hwnd,
            win32con.BM_CLICK,
            0,
            0,
        )
    except Exception:
        return False

    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            closed = (
                not win32gui.IsWindow(dialog_hwnd)
                or not win32gui.IsWindowVisible(
                    dialog_hwnd
                )
            )
        except Exception:
            closed = True

        if closed:
            return True

        time.sleep(0.05)

    return False


def find_known_open_error_dialog(
) -> tuple[int, list[str]] | None:
    """Находит известный диалог ошибки открытия Wilcom."""

    matches: list[tuple[int, list[str]]] = []

    def callback(hwnd: int, _) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return

        try:
            title = win32gui.GetWindowText(
                hwnd
            ).strip()
        except Exception:
            return

        if title != OPEN_DESIGN_ERROR_TITLE:
            return

        matches.append(
            (
                hwnd,
                get_window_texts(hwnd),
            )
        )

    win32gui.EnumWindows(
        callback,
        None,
    )

    if not matches:
        return None

    return matches[0]


def describe_open_design_error(
    texts: list[str],
) -> str:
    """Формирует короткое понятное описание ошибки Wilcom."""

    combined = " ".join(texts).casefold()

    if (
        "был создан в более поздней версии программы"
        in combined
        or "данная версия не может открыть этот дизайн"
        in combined
    ):
        return (
            "Wilcom не смог открыть файл: дизайн создан "
            "в более поздней версии программы."
        )

    details = [
        text.strip()
        for text in texts
        if (
            text.strip()
            and text.strip() != OPEN_DESIGN_ERROR_TITLE
            and text.strip().casefold() not in {"ok", "ок"}
        )
    ]

    if details:
        detail = " ".join(details).rstrip(" .")
        return f"Wilcom не смог открыть файл: {detail}."

    return (
        "Wilcom не смог открыть файл: "
        "Невозможно открыть дизайн."
    )


def dismiss_known_open_error_dialog(
    timeout: float = 3.0,
) -> str | None:
    """
    Закрывает известный диалог через OK или Enter.

    Возвращает описание найденной ошибки.
    """

    match = find_known_open_error_dialog()

    if match is None:
        return None

    hwnd, texts = match
    description = describe_open_design_error(
        texts
    )
    button_hwnd = 0

    try:
        button_hwnd = win32gui.GetDlgItem(
            hwnd,
            win32con.IDOK,
        )
    except Exception:
        pass

    if not button_hwnd:
        buttons: list[int] = []

        def callback(child_hwnd: int, _) -> None:
            try:
                class_name = win32gui.GetClassName(
                    child_hwnd
                )
                text = (
                    win32gui.GetWindowText(child_hwnd)
                    .replace("&", "")
                    .strip()
                    .casefold()
                )
            except Exception:
                return

            if (
                class_name == "Button"
                and text in {"ok", "ок"}
            ):
                buttons.append(child_hwnd)

        try:
            win32gui.EnumChildWindows(
                hwnd,
                callback,
                None,
            )
        except Exception:
            pass

        if buttons:
            button_hwnd = buttons[0]

    if button_hwnd:
        try:
            win32gui.PostMessage(
                button_hwnd,
                win32con.BM_CLICK,
                0,
                0,
            )
        except Exception:
            pass
    else:
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass

        try:
            win32gui.PostMessage(
                hwnd,
                win32con.WM_KEYDOWN,
                win32con.VK_RETURN,
                0,
            )
            win32gui.PostMessage(
                hwnd,
                win32con.WM_KEYUP,
                win32con.VK_RETURN,
                0,
            )
        except Exception:
            pass

    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            closed = (
                not win32gui.IsWindow(hwnd)
                or not win32gui.IsWindowVisible(hwnd)
            )
        except Exception:
            closed = True

        if closed:
            break

        time.sleep(0.05)

    return description


def raise_for_known_open_error_dialog() -> None:
    """Немедленно превращает известный диалог в RuntimeError."""

    description = dismiss_known_open_error_dialog()

    if description is not None:
        raise RuntimeError(description)


def wait_for_es_main_window(
    timeout: float = 60.0,
) -> int:
    """
    Ищет любое настоящее главное окно ES.EXE.

    Не привязывается к PID процесса запуска, потому
    что Wilcom может передать файл уже запущенному
    экземпляру и завершить новый процесс.
    """

    deadline = time.time() + timeout

    while time.time() < deadline:
        raise_for_known_open_error_dialog()

        windows = list_es_main_windows()

        if windows:
            (
                _,
                _,
                hwnd,
                pid,
                title,
                class_name,
            ) = windows[0]

            print()
            print("Найдено окно Wilcom:")
            print("HWND:", hwnd)
            print("PID:", pid)
            print("TITLE:", repr(title))
            print("CLASS:", repr(class_name))

            return hwnd

        time.sleep(0.25)

    raise TimeoutError(
        "Главное окно ES.EXE не появилось."
    )


def wait_for_document_open(
    main_hwnd: int,
    file_path: Path,
    timeout: float = 60.0,
) -> str:
    """Ждёт появления имени нужного документа в заголовке."""

    expected_stem = file_path.stem
    expected_casefold = expected_stem.casefold()
    last_title = ""
    deadline = time.time() + timeout

    while time.time() < deadline:
        raise_for_known_open_error_dialog()

        save_dialog = find_save_changes_dialog()

        if save_dialog is not None:
            _, dialog_texts = save_dialog
            dismissed = dismiss_save_changes_dialog(
                document_stem=None,
                save=False,
                timeout=3.0,
            )
            details = " | ".join(dialog_texts)
            cleanup_status = (
                "Диалог закрыт без сохранения."
                if dismissed
                else "Диалог не удалось закрыть."
            )
            raise RuntimeError(
                "Открытие нового файла заблокировано "
                "диалогом сохранения предыдущего документа. "
                f"{cleanup_status}\n"
                f"Тексты диалога: "
                f"{details or '<нет доступного текста>'}"
            )

        try:
            last_title = win32gui.GetWindowText(
                main_hwnd
            )
        except Exception:
            last_title = ""

        if expected_casefold in last_title.casefold():
            return last_title

        time.sleep(0.25)

    raise TimeoutError(
        "Wilcom не активировал нужный документ "
        f"за {timeout:g} секунд.\n"
        f"Ожидался: {expected_stem}\n"
        "Фактический заголовок: "
        f"{last_title or '<пустой заголовок>'}"
    )


def wait_for_document_closed(
    main_hwnd: int,
    document_stem: str,
    timeout: float = 20.0,
) -> str:
    """Ждёт исчезновения документа из главного окна Wilcom."""

    expected_casefold = document_stem.casefold()
    last_title = ""
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            if not win32gui.IsWindow(main_hwnd):
                return last_title
        except Exception:
            return last_title

        try:
            last_title = win32gui.GetWindowText(
                main_hwnd
            )
        except Exception:
            last_title = ""

        if not title_contains_document(
            last_title,
            expected_casefold,
        ):
            return last_title

        time.sleep(0.25)

    raise TimeoutError(
        "Wilcom не закрыл документ "
        f"за {timeout:g} секунд.\n"
        f"Документ: {document_stem}\n"
        "Фактический заголовок: "
        f"{last_title or '<пустой заголовок>'}"
    )


def title_contains_document(
    title: str,
    document_stem: str,
) -> bool:
    """Отличает имя документа от стандартного состояния No Design."""

    normalized_title = title.casefold()

    if "no design" in normalized_title:
        return False

    return document_stem.casefold() in normalized_title


def focus_window(hwnd: int) -> None:
    """Восстанавливает и активирует окно Wilcom."""

    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(
            hwnd,
            9,  # SW_RESTORE
        )

        time.sleep(0.5)

    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass


def close_document_and_wait(
    window,
    main_hwnd: int,
    document_stem: str,
    timeout: float = 20.0,
    save: bool = True,
) -> str:
    """Закрывает документ, отвечая на возможный запрос сохранения."""

    focus_window(main_hwnd)

    if window is not None:
        try:
            window.set_focus()
        except Exception:
            # Уже открытый модальный диалог может блокировать UIA-фокус.
            pass

    send_ctrl_virtual_key(
        win32con.VK_F4
    )
    expected_casefold = document_stem.casefold()
    last_title = ""
    save_dialog_seen = False
    last_dialog_texts: list[str] = []
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            if not win32gui.IsWindow(main_hwnd):
                return last_title
        except Exception:
            return last_title

        try:
            last_title = win32gui.GetWindowText(
                main_hwnd
            )
        except Exception:
            last_title = ""

        save_dialog = find_save_changes_dialog(
            document_stem
        )

        if save_dialog is not None:
            save_dialog_seen = True
            _, last_dialog_texts = save_dialog
            remaining = max(
                0.0,
                deadline - time.time(),
            )
            dismiss_save_changes_dialog(
                document_stem,
                save=save,
                timeout=min(5.0, remaining),
            )
        elif not title_contains_document(
            last_title,
            expected_casefold,
        ):
            return last_title

        time.sleep(0.15)

    dialog_details = (
        " | ".join(last_dialog_texts)
        if last_dialog_texts
        else "<нет доступного текста>"
    )
    raise TimeoutError(
        "Wilcom не закрыл документ "
        f"за {timeout:g} секунд.\n"
        f"Документ: {document_stem}\n"
        "Фактический заголовок: "
        f"{last_title or '<пустой заголовок>'}\n"
        "Диалог сохранения найден: "
        f"{'да' if save_dialog_seen else 'нет'}\n"
        f"Тексты диалога: {dialog_details}"
    )


def close_document_best_effort(
    main_hwnd: int,
    document_stem: str,
    window=None,
    timeout: float = 20.0,
) -> None:
    """Пытается закрыть только указанный документ, не скрывая ошибку."""

    try:
        if not win32gui.IsWindow(main_hwnd):
            return

        title = win32gui.GetWindowText(
            main_hwnd
        )
        save_dialog = find_save_changes_dialog(
            document_stem
        )

        if (
            not title_contains_document(
                title,
                document_stem,
            )
            and save_dialog is None
        ):
            return

        if window is None:
            try:
                window = Desktop(
                    backend="uia"
                ).window(
                    handle=main_hwnd
                )
            except Exception:
                window = None

        close_document_and_wait(
            window,
            main_hwnd,
            document_stem,
            timeout=timeout,
            save=False,
        )
    except Exception:
        pass


def build_document_canvas_candidate(
    hwnd: int,
    class_name: str,
    visible: bool,
    rectangle: tuple[int, int, int, int],
) -> tuple[int, int, int, int] | None:
    """Создаёт кандидата рабочего поля из данных Win32."""

    if not visible:
        return None

    if class_name != DOCUMENT_CANVAS_CLASS:
        return None

    left, top, right, bottom = rectangle
    width = right - left
    height = bottom - top

    if width < 200 or height < 150:
        return None

    center_x = left + width // 2
    center_y = top + height // 2

    return (
        width * height,
        hwnd,
        center_x,
        center_y,
    )


def choose_document_canvas_candidate(
    candidates: list[tuple[int, int, int, int]],
) -> tuple[int, int, int] | None:
    """Выбирает самое большое подходящее рабочее поле."""

    if not candidates:
        return None

    (
        _,
        hwnd,
        center_x,
        center_y,
    ) = max(
        candidates,
        key=lambda candidate: candidate[0],
    )

    return hwnd, center_x, center_y


def find_document_canvas(
    main_hwnd: int,
) -> tuple[int, int, int] | None:
    """
    Ищет большое рабочее поле документа Wilcom.

    У обнаруженной версии класс рабочего поля:
    AfxFrameOrView140u.
    """

    candidates: list[
        tuple[int, int, int, int]
    ] = []

    def callback(hwnd: int, _) -> None:
        try:
            class_name = win32gui.GetClassName(hwnd)
            visible = win32gui.IsWindowVisible(hwnd)
            rectangle = win32gui.GetWindowRect(hwnd)
        except Exception:
            return

        candidate = build_document_canvas_candidate(
            hwnd=hwnd,
            class_name=class_name,
            visible=visible,
            rectangle=rectangle,
        )

        if candidate is not None:
            candidates.append(candidate)

    win32gui.EnumChildWindows(
        main_hwnd,
        callback,
        None,
    )

    return choose_document_canvas_candidate(
        candidates
    )


def log_document_canvas_once(
    canvas_hwnd: int,
) -> None:
    """Печатает сведения о рабочем поле один раз для каждого HWND."""

    if canvas_hwnd in _LOGGED_CANVAS_HANDLES:
        return

    try:
        class_name = win32gui.GetClassName(
            canvas_hwnd
        )
        rectangle = win32gui.GetWindowRect(
            canvas_hwnd
        )
    except Exception:
        class_name = "<unknown>"
        rectangle = None

    print()
    print("Рабочее поле:")
    print("HWND:", canvas_hwnd)
    print("CLASS:", repr(class_name))
    print("RECT:", rectangle)

    _LOGGED_CANVAS_HANDLES.add(canvas_hwnd)


def send_ctrl_virtual_key(
    vk_code: int,
) -> None:
    """Отправляет Ctrl+VK и гарантированно освобождает обе клавиши."""

    try:
        win32api.keybd_event(
            win32con.VK_CONTROL,
            0,
            0,
            0,
        )
        time.sleep(0.05)

        win32api.keybd_event(
            vk_code,
            0,
            0,
            0,
        )
        time.sleep(0.05)
    finally:
        try:
            win32api.keybd_event(
                vk_code,
                0,
                win32con.KEYEVENTF_KEYUP,
                0,
            )
            time.sleep(0.05)
        finally:
            win32api.keybd_event(
                win32con.VK_CONTROL,
                0,
                win32con.KEYEVENTF_KEYUP,
                0,
            )


def send_ctrl_a_win32() -> None:
    """Отправляет раскладко-независимый Ctrl+A."""

    send_ctrl_virtual_key(
        ord("A")
    )


def select_all_design_objects(
    main_hwnd: int,
    method: str = "win32",
) -> None:
    """Фокусирует рабочее поле и глобально отправляет Ctrl+A."""

    if method not in {
        "win32",
        "pywinauto",
    }:
        raise ValueError(
            f"Неизвестный метод выделения: {method}"
        )

    focus_window(main_hwnd)

    canvas = find_document_canvas(
        main_hwnd
    )

    if canvas is None:
        left, top, right, bottom = (
            win32gui.GetWindowRect(main_hwnd)
        )

        width = right - left
        height = bottom - top

        # Запасная точка в правой центральной части окна.
        mouse.click(
            button="left",
            coords=(
                left + int(width * 0.68),
                top + int(height * 0.60),
            ),
        )
    else:
        (
            canvas_hwnd,
            center_x,
            center_y,
        ) = canvas

        log_document_canvas_once(
            canvas_hwnd
        )

        try:
            canvas_wrapper = Desktop(
                backend="win32"
            ).window(
                handle=canvas_hwnd
            ).wrapper_object()

            canvas_wrapper.click_input()
        except Exception:
            mouse.click(
                button="left",
                coords=(
                    center_x,
                    center_y,
                ),
            )

    time.sleep(0.3)

    focus_window(main_hwnd)

    if method == "win32":
        if method not in _LOGGED_SELECTION_METHODS:
            print()
            print(
                "Метод выделения: "
                "win32 VK_CONTROL + VK_A"
            )
            _LOGGED_SELECTION_METHODS.add(method)

        send_ctrl_a_win32()
    else:
        keyboard.send_keys(
            "^a",
            pause=0.05,
            vk_packet=False,
        )

    time.sleep(0.8)


def is_control_visible(control) -> bool:
    try:
        return control.is_visible()
    except Exception:
        return False


def get_child_edit(pane):
    """
    Находит настоящий Win32 Edit,
    физически вложенный в панель X или Y.
    """

    candidates: list[tuple[int, int]] = []

    def callback(hwnd: int, _) -> None:
        try:
            if win32gui.GetClassName(hwnd) != "Edit":
                return

            if not win32gui.IsWindowVisible(hwnd):
                return

            left, top, right, bottom = (
                win32gui.GetWindowRect(hwnd)
            )

            area = (
                (right - left)
                * (bottom - top)
            )

            candidates.append(
                (area, hwnd)
            )

        except Exception:
            return

    win32gui.EnumChildWindows(
        pane.handle,
        callback,
        None,
    )

    if not candidates:
        return None

    candidates.sort(reverse=True)

    edit_hwnd = candidates[0][1]

    return Desktop(
        backend="win32"
    ).window(
        handle=edit_hwnd
    ).wrapper_object()


def control_center_y(control) -> int:
    rectangle = control.rectangle()

    return (
        rectangle.top
        + rectangle.bottom
    ) // 2


def find_pane_near_label(
    window,
    label,
    automation_id: str,
    require_enabled: bool,
):
    label_rectangle = label.rectangle()
    label_center_y = control_center_y(label)

    candidates = []

    for pane in window.descendants(
        control_type="Pane"
    ):
        pane_automation_id = str(
            pane.element_info.automation_id or ""
        )

        if pane_automation_id != automation_id:
            continue

        if not is_control_visible(pane):
            continue

        edit = get_child_edit(pane)

        if edit is None:
            continue

        if require_enabled and not edit.is_enabled():
            continue

        pane_rectangle = pane.rectangle()
        pane_center_y = control_center_y(pane)

        vertical_difference = abs(
            pane_center_y
            - label_center_y
        )

        horizontal_gap = (
            pane_rectangle.left
            - label_rectangle.right
        )

        # Поле должно находиться справа от своей подписи.
        if horizontal_gap < -10:
            continue

        if horizontal_gap > 250:
            continue

        # Вертикально подпись и поле должны быть
        # практически на одной линии.
        if vertical_difference > 15:
            continue

        score = (
            vertical_difference * 100
            + abs(horizontal_gap)
        )

        candidates.append(
            (
                score,
                pane,
                edit,
            )
        )

    if not candidates:
        raise RuntimeError(
            f"Поле с automation_id="
            f"{automation_id} рядом с подписью "
            f"{label.window_text()!r} не найдено."
        )

    candidates.sort(
        key=lambda item: item[0]
    )

    _, pane, edit = candidates[0]

    return pane, edit


def get_position_controls(
    window,
    require_enabled: bool,
):
    x_labels = []
    y_labels = []

    for control in window.descendants(
        control_type="Text"
    ):
        if not is_control_visible(control):
            continue

        text = control.window_text().strip()

        if text == "Позиция X:":
            x_labels.append(control)

        elif text == "Позиция Y:":
            y_labels.append(control)

    pairs = []

    for x_label in x_labels:
        for y_label in y_labels:
            x_rectangle = x_label.rectangle()
            y_rectangle = y_label.rectangle()

            horizontal_difference = abs(
                x_rectangle.left
                - y_rectangle.left
            )

            vertical_difference = (
                control_center_y(y_label)
                - control_center_y(x_label)
            )

            # Подписи X и Y должны находиться
            # одна под другой.
            if horizontal_difference > 20:
                continue

            if not 10 <= vertical_difference <= 40:
                continue

            try:
                x_pane, x_edit = find_pane_near_label(
                    window,
                    x_label,
                    X_AUTOMATION_ID,
                    require_enabled,
                )

                y_pane, y_edit = find_pane_near_label(
                    window,
                    y_label,
                    Y_AUTOMATION_ID,
                    require_enabled,
                )
            except RuntimeError:
                continue

            score = (
                horizontal_difference
                + abs(vertical_difference - 20)
            )

            pairs.append(
                (
                    score,
                    x_pane,
                    x_edit,
                    y_pane,
                    y_edit,
                )
            )

    if not pairs:
        raise RuntimeError(
            "Настоящие поля «Позиция X» "
            "и «Позиция Y» не найдены."
        )

    pairs.sort(
        key=lambda item: item[0]
    )

    (
        _,
        x_pane,
        x_edit,
        y_pane,
        y_edit,
    ) = pairs[0]

    print()
    print("Выбраны поля координат:")
    print(
        "X:",
        x_pane.window_text(),
        x_pane.rectangle(),
    )
    print(
        "Y:",
        y_pane.window_text(),
        y_pane.rectangle(),
    )

    return (
        x_pane,
        x_edit,
        y_pane,
        y_edit,
    )


def get_cached_position_controls(
    main_hwnd: int,
):
    controls = POSITION_CONTROLS_CACHE.get(
        main_hwnd
    )

    if controls is None:
        return None

    (
        x_pane,
        x_edit,
        y_pane,
        y_edit,
    ) = controls

    try:
        for edit in (x_edit, y_edit):
            edit_hwnd = int(edit.handle)

            if (
                not edit_hwnd
                or not win32gui.IsWindow(edit_hwnd)
                or not edit.is_enabled()
            ):
                raise RuntimeError(
                    "cached Edit is no longer available"
                )
    except Exception:
        POSITION_CONTROLS_CACHE.pop(
            main_hwnd,
            None,
        )
        return None

    return controls


def wait_for_selected_design(
    window,
    main_hwnd: int,
    timeout: float = 60.0,
):
    """
    Ждёт загрузки документа и повторяет выделение,
    пока поля координат не станут активными.
    """

    deadline = time.time() + timeout
    last_error: Exception | None = None
    selection_attempt = 0

    while time.time() < deadline:
        raise_for_known_open_error_dialog()

        try:
            focus_window(main_hwnd)
            window.set_focus()

            method = (
                "win32"
                if selection_attempt % 2 == 0
                else "pywinauto"
            )
            selection_attempt += 1

            select_all_design_objects(
                main_hwnd,
                method=method,
            )

            controls = get_position_controls(
                window,
                require_enabled=True,
            )

            return controls

        except Exception as error:
            last_error = error
            raise_for_known_open_error_dialog()
            time.sleep(0.7)

    reason = (
        str(last_error)
        if last_error is not None
        else "причина не определена"
    )

    raise RuntimeError(
        "Документ открыт, но дизайн не удалось выделить:\n"
        f"{reason}"
    ) from last_error


def wait_for_enabled_controls(
    window,
    timeout: float = 8.0,
    main_hwnd: int | None = None,
):
    deadline = time.time() + timeout
    last_error: Exception | None = None

    while time.time() < deadline:
        if main_hwnd is not None:
            cached = get_cached_position_controls(
                main_hwnd
            )

            if cached is not None:
                return cached

        try:
            controls = get_position_controls(
                window,
                require_enabled=True,
            )

            if main_hwnd is not None:
                POSITION_CONTROLS_CACHE[
                    main_hwnd
                ] = controls

            return controls
        except Exception as error:
            last_error = error
            time.sleep(0.25)

    raise RuntimeError(
        "Поля позиции перестали быть доступными."
    ) from last_error


def read_value(pane, edit) -> str:
    # Сначала читаем непосредственно Win32 Edit.
    value = win32gui.GetWindowText(
        edit.handle
    ).strip()

    if value:
        return value

    return pane.window_text().strip()


def set_value(
    edit,
    value: str,
) -> None:
    if not edit.is_enabled():
        raise RuntimeError(
            "Поле координаты недоступно."
        )

    hwnd = edit.handle

    edit.click_input()
    time.sleep(0.05)

    # Wilcom отображает значение, хотя GetWindowText
    # для этого внутреннего Edit возвращает пустоту.
    win32gui.SendMessage(
        hwnd,
        win32con.WM_SETTEXT,
        0,
        value,
    )

    time.sleep(0.10)

    print(
        "Передаю значение:",
        value,
        "HWND:",
        hwnd,
    )

    # Подтверждаем ввод, чтобы Wilcom применил координату.
    edit.type_keys(
        "{ENTER}",
        set_foreground=False,
    )

    time.sleep(0.40)


def parse_number(value: str) -> float:
    return float(
        value
        .strip()
        .replace(",", ".")
    )


def verify_value(
    name: str,
    actual: str,
    expected: str,
) -> None:
    difference = abs(
        parse_number(actual)
        - parse_number(expected)
    )

    if difference > 0.011:
        raise RuntimeError(
            f"{name} установился неправильно: "
            f"ожидалось {expected}, "
            f"получено {actual}"
        )


def send_save_command(
    window,
    main_hwnd: int,
) -> None:
    """Отправляет раскладко-независимый Ctrl+S."""

    focus_window(main_hwnd)
    window.set_focus()
    send_ctrl_virtual_key(
        ord("S")
    )
    time.sleep(0.75)

    print("Команда сохранения отправлена.")


def normalize_menu_text(text: str) -> str:
    """Нормализует локализованный текст UIA-меню."""

    normalized = (
        str(text)
        .replace("\xa0", " ")
        .split("\t", 1)[0]
        .replace("&", "")
        .replace("...", "")
        .replace("…", "")
    )

    return " ".join(
        normalized.split()
    ).casefold()


def menu_text_matches(
    text: str,
    allowed_texts: set[str],
) -> bool:
    normalized = normalize_menu_text(text)
    return any(
        normalized == allowed
        or normalized.startswith(allowed)
        for allowed in allowed_texts
    )


@dataclass(frozen=True)
class Win32MenuItem:
    depth: int
    text: str
    command_id: int
    submenu_handle: int
    path: tuple[str, ...]


@dataclass
class UiaPopupMenuInspection:
    popup: object
    hwnd: int
    class_name: str
    rectangle: tuple[int, int, int, int] | None
    title: str
    items: list[object]


def _handle_as_int(value) -> int:
    if value is None:
        return 0

    raw_value = getattr(value, "value", value)
    return int(raw_value or 0)


def get_win32_menu_text(
    menu_handle: int,
    position: int,
) -> str:
    buffer = ctypes.create_unicode_buffer(1024)
    length = int(
        _USER32.GetMenuStringW(
            menu_handle,
            position,
            buffer,
            len(buffer),
            win32con.MF_BYPOSITION,
        )
    )

    if length <= 0:
        return ""

    return buffer.value[:length]


def enumerate_win32_menu_items(
    menu_handle: int,
    depth: int = 0,
    path: tuple[str, ...] = (),
    max_depth: int = WIN32_MENU_MAX_DEPTH,
) -> list[Win32MenuItem]:
    """Перечисляет не больше трёх уровней стандартного меню."""

    if not menu_handle or depth >= max_depth:
        return []

    count = int(
        _USER32.GetMenuItemCount(menu_handle)
    )

    if count <= 0:
        return []

    items: list[Win32MenuItem] = []

    for position in range(count):
        text = get_win32_menu_text(
            menu_handle,
            position,
        )
        submenu_handle = _handle_as_int(
            _USER32.GetSubMenu(
                menu_handle,
                position,
            )
        )
        command_id = int(
            _USER32.GetMenuItemID(
                menu_handle,
                position,
            )
        )
        item_path = (*path, text)
        item = Win32MenuItem(
            depth=depth,
            text=text,
            command_id=command_id,
            submenu_handle=submenu_handle,
            path=item_path,
        )
        items.append(item)

        if submenu_handle:
            items.extend(
                enumerate_win32_menu_items(
                    submenu_handle,
                    depth=depth + 1,
                    path=item_path,
                    max_depth=max_depth,
                )
            )

    return items


def is_valid_menu_command_id(
    command_id: int,
) -> bool:
    return command_id not in {
        0,
        -1,
        0xFFFFFFFF,
    }


def find_save_as_win32_menu_item(
    menu_items: list[Win32MenuItem],
) -> Win32MenuItem | None:
    for item in menu_items:
        if (
            menu_text_matches(
                item.text,
                SAVE_AS_MENU_TEXTS,
            )
            and is_valid_menu_command_id(
                item.command_id
            )
        ):
            return item

    return None


def print_win32_file_menu(
    main_hwnd: int,
    menu_handle: int,
    menu_items: list[Win32MenuItem],
) -> None:
    if main_hwnd in _LOGGED_WIN32_FILE_MENUS:
        return

    _LOGGED_WIN32_FILE_MENUS.add(main_hwnd)
    print("Win32 File menu:")

    if not menu_handle:
        print("GetMenu(main_hwnd) == NULL")
        return

    file_items = [
        item
        for item in menu_items
        if (
            item.path
            and menu_text_matches(
                item.path[0],
                FILE_MENU_TEXTS,
            )
            and item.depth > 0
        )
    ]

    if not file_items:
        print("<пункты File не найдены>")
        return

    for item in file_items:
        command_id = (
            item.command_id
            if is_valid_menu_command_id(
                item.command_id
            )
            else "-"
        )
        print(
            f"[id={command_id}] {item.text}"
        )


def scan_save_as_win32_menu(
    main_hwnd: int,
    debug: bool = False,
) -> Win32MenuItem | None:
    menu_handle = _handle_as_int(
        _USER32.GetMenu(main_hwnd)
    )

    if not menu_handle:
        _SAVE_AS_WIN32_DISABLED_HWNDS.add(
            main_hwnd
        )

        if debug:
            print_win32_file_menu(
                main_hwnd,
                0,
                [],
            )

        return None

    menu_items = enumerate_win32_menu_items(
        menu_handle
    )

    if debug:
        print_win32_file_menu(
            main_hwnd,
            menu_handle,
            menu_items,
        )

    return find_save_as_win32_menu_item(
        menu_items
    )


def post_win32_menu_command(
    main_hwnd: int,
    command_id: int,
) -> None:
    if not is_valid_menu_command_id(command_id):
        raise ValueError(
            f"Некорректный Win32 command ID: {command_id}"
        )

    if not _USER32.PostMessageW(
        main_hwnd,
        win32con.WM_COMMAND,
        command_id,
        0,
    ):
        raise OSError(
            ctypes.get_last_error(),
            "Не удалось отправить WM_COMMAND для Save As.",
        )


def safe_uia_call(
    callback,
    default,
):
    try:
        return callback()
    except Exception:
        return default


def get_uia_control_texts(control) -> list[str]:
    element_info = safe_uia_call(
        lambda: control.element_info,
        None,
    )
    values: list[str] = []

    for callback in (
        lambda: control.window_text(),
        lambda: element_info.name,
        lambda: element_info.automation_id,
    ):
        value = safe_uia_call(callback, "")

        if value:
            values.append(str(value))

    return list(dict.fromkeys(values))


def get_uia_control_type(control) -> str:
    return str(
        safe_uia_call(
            lambda: control.element_info.control_type,
            "",
        )
        or ""
    ).casefold()


def collect_uia_menu_controls(
    main_hwnd: int,
) -> list[object]:
    """Собирает UIA-контролы окна и popup-меню его процесса."""

    desktop = Desktop(backend="uia")
    specification = desktop.window(
        handle=main_hwnd
    )
    root = safe_uia_call(
        lambda: specification.wrapper_object(),
        specification,
    )
    controls: list[object] = [root]
    controls.extend(
        safe_uia_call(
            lambda: root.descendants(),
            [],
        )
    )
    main_pid = safe_uia_call(
        lambda: win32process.GetWindowThreadProcessId(
            main_hwnd
        )[1],
        0,
    )

    for popup in safe_uia_call(
        lambda: desktop.windows(),
        [],
    ):
        popup_handle = safe_uia_call(
            lambda: int(
                popup.element_info.handle or 0
            ),
            0,
        )
        popup_pid = safe_uia_call(
            lambda: int(
                popup.element_info.process_id or 0
            ),
            0,
        )

        if (
            popup_handle == main_hwnd
            or not main_pid
            or popup_pid != main_pid
        ):
            continue

        controls.append(popup)
        controls.extend(
            safe_uia_call(
                lambda: popup.descendants(),
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


def uia_control_matches(
    control,
    allowed_texts: set[str],
) -> bool:
    return any(
        menu_text_matches(text, allowed_texts)
        for text in get_uia_control_texts(control)
    )


def invoke_uia_control(control) -> None:
    try:
        control.invoke()
    except Exception:
        control.click_input()


def matching_uia_menu_title(
    control,
    allowed_texts: set[str],
) -> str:
    for text in get_uia_control_texts(control):
        if menu_text_matches(
            text,
            allowed_texts,
        ):
            return text

    return ""


def resolve_uia_specification(
    specification,
    timeout: float,
) -> object | None:
    """Разрешает один точный UIA locator с коротким timeout."""

    old_timeout = Timings.window_find_timeout
    old_retry = Timings.window_find_retry

    try:
        Timings.window_find_timeout = max(
            0.01,
            timeout,
        )
        Timings.window_find_retry = min(
            FAST_UIA_POLL_INTERVAL,
            Timings.window_find_timeout,
        )
        return safe_uia_call(
            specification.wrapper_object,
            None,
        )
    finally:
        Timings.window_find_timeout = old_timeout
        Timings.window_find_retry = old_retry


def find_uia_menu_bar(
    window,
    timeout: float = FAST_UIA_LOOKUP_TIMEOUT,
) -> object | None:
    specification = safe_uia_call(
        lambda: window.child_window(
            control_type="MenuBar",
            depth=3,
        ),
        None,
    )

    if specification is None:
        return None

    return resolve_uia_specification(
        specification,
        timeout=timeout,
    )


def wait_for_shallow_uia_menu_item(
    container,
    allowed_texts: set[str],
    cached_title: str = "",
    timeout: float = FAST_UIA_LOOKUP_TIMEOUT,
    allow_popup_descendants: bool = False,
    debug: bool = False,
) -> tuple[object, str] | None:
    """Ищет MenuItem с единым deadline и без обхода main window."""

    deadline = time.monotonic() + timeout
    descendants_checked = False
    debug_printed = False

    def find_match(
        items: list[object],
    ) -> tuple[object, str] | None:
        if cached_title:
            for item in items:
                texts = get_uia_control_texts(
                    item
                )

                if cached_title not in texts:
                    continue

                actual_title = matching_uia_menu_title(
                    item,
                    allowed_texts,
                )

                if actual_title:
                    return item, actual_title

        for item in items:
            actual_title = matching_uia_menu_title(
                item,
                allowed_texts,
            )

            if actual_title:
                return item, actual_title

        return None

    while True:
        items = list(
            safe_uia_call(
                lambda: container.children(
                    control_type="MenuItem"
                ),
                [],
            )
        )
        match = find_match(items)

        if (
            match is None
            and allow_popup_descendants
            and not descendants_checked
        ):
            descendants_checked = True
            descendants = list(
                safe_uia_call(
                    lambda: container.descendants(
                        control_type="MenuItem"
                    ),
                    [],
                )
            )
            known = {id(item) for item in items}
            items.extend(
                item
                for item in descendants
                if id(item) not in known
            )
            match = find_match(items)

        if debug and not debug_printed:
            debug_printed = True
            print("UIA popup MenuItem:")

            if not items:
                print("<пункты не найдены>")

            for item in items:
                texts = get_uia_control_texts(
                    item
                )
                print(
                    texts[0]
                    if texts
                    else "<без названия>"
                )

        if match is not None:
            return match

        remaining = deadline - time.monotonic()

        if remaining <= 0:
            return None

        time.sleep(
            min(
                FAST_UIA_POLL_INTERVAL,
                remaining,
            )
        )


def get_uia_control_handle(control) -> int:
    return int(
        safe_uia_call(
            lambda: control.element_info.handle or 0,
            0,
        )
        or 0
    )


def get_visible_uia_popup_menus(
    desktop,
    main_hwnd: int,
) -> list[object]:
    """Перечисляет только видимые top-level UIA Menu."""

    criteria: dict[str, object] = {
        "control_type": "Menu",
        "visible_only": True,
        "top_level_only": True,
    }

    return list(
        safe_uia_call(
            lambda: desktop.windows(**criteria),
            [],
        )
    )


def popup_menu_relation_score(
    main_hwnd: int,
    popup,
) -> int:
    """Предпочитает Menu того же процесса/owner рядом с Wilcom."""

    popup_hwnd = get_uia_control_handle(
        popup
    )
    main_pid = safe_uia_call(
        lambda: win32process.GetWindowThreadProcessId(
            main_hwnd
        )[1],
        0,
    )
    popup_pid = int(
        safe_uia_call(
            lambda: popup.element_info.process_id or 0,
            0,
        )
        or 0
    )
    owner_hwnd = (
        safe_uia_call(
            lambda: win32gui.GetWindow(
                popup_hwnd,
                win32con.GW_OWNER,
            ),
            0,
        )
        if popup_hwnd
        else 0
    )
    parent_hwnd = (
        safe_uia_call(
            lambda: win32gui.GetParent(
                popup_hwnd
            ),
            0,
        )
        if popup_hwnd
        else 0
    )
    score = 0

    if main_hwnd in {
        owner_hwnd,
        parent_hwnd,
    }:
        score += 100

    if main_pid and popup_pid == main_pid:
        score += 50

    main_rectangle = safe_uia_call(
        lambda: win32gui.GetWindowRect(
            main_hwnd
        ),
        None,
    )
    popup_rectangle = safe_uia_call(
        lambda: popup.rectangle(),
        None,
    )

    if (
        main_rectangle is not None
        and popup_rectangle is not None
    ):
        main_left, main_top, main_right, main_bottom = (
            main_rectangle
        )
        popup_left = safe_uia_call(
            lambda: popup_rectangle.left,
            0,
        )
        popup_right = safe_uia_call(
            lambda: popup_rectangle.right,
            0,
        )
        popup_top = safe_uia_call(
            lambda: popup_rectangle.top,
            0,
        )
        horizontally_near = (
            popup_right >= main_left - 50
            and popup_left <= main_right + 50
        )
        vertically_near = (
            main_top - 50
            <= popup_top
            <= main_bottom + 50
        )

        if horizontally_near and vertically_near:
            score += 20

    return score


def get_uia_control_title(control) -> str:
    for callback in (
        lambda: control.window_text(),
        lambda: control.element_info.name,
    ):
        value = safe_uia_call(callback, "")

        if value:
            return str(value)

    return ""


def get_uia_popup_class_name(
    popup,
) -> str:
    popup_hwnd = get_uia_control_handle(popup)

    if popup_hwnd:
        class_name = safe_uia_call(
            lambda: win32gui.GetClassName(
                popup_hwnd
            ),
            "",
        )

        if class_name:
            return str(class_name)

    return str(
        safe_uia_call(
            lambda: popup.element_info.class_name,
            "",
        )
        or ""
    )


def get_uia_popup_rectangle(
    popup,
) -> tuple[int, int, int, int] | None:
    rectangle = safe_uia_call(
        popup.rectangle,
        None,
    )

    if rectangle is None:
        return None

    try:
        return (
            int(rectangle.left),
            int(rectangle.top),
            int(rectangle.right),
            int(rectangle.bottom),
        )
    except Exception:
        return None


def collect_uia_popup_menu_items(
    popup,
) -> list[object]:
    """Обходит только маленький popup Menu, никогда main window."""

    direct_items = list(
        safe_uia_call(
            lambda: popup.children(
                control_type="MenuItem"
            ),
            [],
        )
    )
    descendant_items = list(
        safe_uia_call(
            lambda: popup.descendants(
                control_type="MenuItem"
            ),
            [],
        )
    )
    items: list[object] = []
    seen: set[tuple[int, str]] = set()

    for item in [
        *direct_items,
        *descendant_items,
    ]:
        identity = (
            get_uia_control_handle(item),
            get_uia_control_title(item),
        )

        if identity in seen:
            continue

        seen.add(identity)
        items.append(item)

    return items


def inspect_uia_popup_menu(
    popup,
) -> UiaPopupMenuInspection:
    return UiaPopupMenuInspection(
        popup=popup,
        hwnd=get_uia_control_handle(popup),
        class_name=get_uia_popup_class_name(
            popup
        ),
        rectangle=get_uia_popup_rectangle(
            popup
        ),
        title=get_uia_control_title(popup),
        items=collect_uia_popup_menu_items(
            popup
        ),
    )


def print_uia_popup_inspection(
    inspection: UiaPopupMenuInspection,
) -> None:
    print("Popup Menu:")
    print(f"- HWND: {inspection.hwnd}")
    print(f"- CLASS: {inspection.class_name!r}")
    print(f"- RECT: {inspection.rectangle!r}")
    print(f"- TITLE: {inspection.title!r}")
    print("- ITEMS:")

    if not inspection.items:
        print("  <пункты не найдены>")
        return

    for item in inspection.items:
        print(
            f"  {get_uia_control_title(item)!r}"
        )


def popup_is_relevant_after_file(
    main_hwnd: int,
    popup,
    before_handles: set[int],
) -> bool:
    popup_hwnd = get_uia_control_handle(popup)
    class_name = get_uia_popup_class_name(
        popup
    )
    is_new = bool(
        popup_hwnd
        and popup_hwnd not in before_handles
    )
    is_standard_menu = class_name == "#32768"
    is_related = (
        popup_menu_relation_score(
            main_hwnd,
            popup,
        )
        >= 20
    )
    return (
        is_new
        or is_related
        or (
            is_standard_menu
            and not before_handles
        )
    )


def find_save_as_item_in_inspections(
    inspections: list[UiaPopupMenuInspection],
) -> tuple[object, str] | None:
    for inspection in inspections:
        for item in inspection.items:
            title = get_uia_control_title(item)

            if menu_text_matches(
                title,
                SAVE_AS_MENU_TEXTS,
            ):
                return item, title

    return None


def find_save_as_in_visible_popups(
    desktop,
    main_hwnd: int,
    before_handles: set[int],
    timeout: float = FAST_UIA_LOOKUP_TIMEOUT,
    debug: bool = False,
    timings: dict[str, float] | None = None,
) -> tuple[
    tuple[object, str] | None,
    list[UiaPopupMenuInspection],
]:
    """Проверяет все popup и выбирает содержащий реальный Save As."""

    deadline = time.monotonic() + max(
        0.0,
        timeout,
    )
    printed: set[
        tuple[int, tuple[str, ...]]
    ] = set()
    latest: list[UiaPopupMenuInspection] = []
    find_started = start_optional_timing(
        timings
    )

    try:
        while True:
            enumerate_started = start_optional_timing(
                timings
            )

            try:
                popups = get_visible_uia_popup_menus(
                    desktop,
                    main_hwnd,
                )
            finally:
                add_optional_timing(
                    timings,
                    "open_save_as_enumerate_popup_menus",
                    enumerate_started,
                )

            relevant = [
                popup
                for popup in popups
                if popup_is_relevant_after_file(
                    main_hwnd,
                    popup,
                    before_handles,
                )
            ]
            inspect_started = start_optional_timing(
                timings
            )

            try:
                latest = [
                    inspect_uia_popup_menu(popup)
                    for popup in relevant
                ]
            finally:
                add_optional_timing(
                    timings,
                    "open_save_as_inspect_popup_items",
                    inspect_started,
                )

            if debug:
                for inspection in latest:
                    signature = (
                        inspection.hwnd,
                        tuple(
                            get_uia_control_title(item)
                            for item in inspection.items
                        ),
                    )

                    if signature in printed:
                        continue

                    printed.add(signature)
                    print_uia_popup_inspection(
                        inspection
                    )

            match = find_save_as_item_in_inspections(
                latest
            )

            if match is not None:
                return match, latest

            remaining = deadline - time.monotonic()

            if remaining <= 0:
                return None, latest

            time.sleep(
                min(
                    FAST_UIA_POLL_INTERVAL,
                    remaining,
                )
            )
    finally:
        finish_optional_timing(
            timings,
            "open_save_as_find_save_as_item",
            find_started,
        )


def snapshot_visible_uia_popup_handles(
    desktop,
    main_hwnd: int,
) -> set[int]:
    return {
        get_uia_control_handle(popup)
        for popup in get_visible_uia_popup_menus(
            desktop,
            main_hwnd,
        )
        if get_uia_control_handle(popup)
    }


def start_optional_timing(
    timings: dict[str, float] | None,
) -> float | None:
    if timings is None:
        return None

    return time.perf_counter()


def finish_optional_timing(
    timings: dict[str, float] | None,
    key: str,
    started_at: float | None,
) -> None:
    if timings is None or started_at is None:
        return

    timings[key] = (
        time.perf_counter() - started_at
    )


def add_optional_timing(
    timings: dict[str, float] | None,
    key: str,
    started_at: float | None,
) -> None:
    if timings is None or started_at is None:
        return

    timings[key] = (
        timings.get(key, 0.0)
        + time.perf_counter()
        - started_at
    )


def uia_menu_item_is_expandable(item) -> bool:
    children = list(
        safe_uia_call(
            lambda: item.children(
                control_type="MenuItem"
            ),
            [],
        )
    )

    if children:
        return True

    interface = safe_uia_call(
        lambda: item.iface_expand_collapse,
        None,
    )

    if interface is None:
        return False

    state = safe_uia_call(
        lambda: interface.CurrentExpandCollapseState,
        None,
    )
    return state != 3


def expand_uia_menu_item(item) -> bool:
    interface = safe_uia_call(
        lambda: item.iface_expand_collapse,
        None,
    )
    methods = []

    if interface is not None:
        methods.append(
            safe_uia_call(
                lambda: interface.Expand,
                None,
            )
        )

    methods.extend(
        [
            safe_uia_call(
                lambda: item.expand,
                None,
            ),
            safe_uia_call(
                lambda: item.invoke,
                None,
            ),
            safe_uia_call(
                lambda: item.click_input,
                None,
            ),
        ]
    )

    for method in methods:
        if not callable(method):
            continue

        try:
            method()
            return True
        except Exception:
            continue

    return False


def find_save_as_through_submenu(
    desktop,
    main_hwnd: int,
    inspections: list[UiaPopupMenuInspection],
    timeout: float,
    debug: bool,
    timings: dict[str, float] | None,
) -> tuple[object, str] | None:
    deadline = time.monotonic() + max(
        0.0,
        timeout,
    )

    for inspection in inspections:
        for item in inspection.items:
            if not uia_menu_item_is_expandable(
                item
            ):
                continue

            before_handles = (
                snapshot_visible_uia_popup_handles(
                    desktop,
                    main_hwnd,
                )
            )

            if not expand_uia_menu_item(item):
                continue

            remaining = deadline - time.monotonic()

            if remaining <= 0:
                return None

            match, _ = find_save_as_in_visible_popups(
                desktop,
                main_hwnd,
                before_handles,
                timeout=min(1.0, remaining),
                debug=debug,
                timings=timings,
            )

            if match is not None:
                return match

    return None


def invoke_save_as_item_and_wait(
    item,
    main_hwnd: int,
    timeout: float = SAVE_AS_DIALOG_TIMEOUT,
    timings: dict[str, float] | None = None,
) -> int:
    deadline = time.monotonic() + max(
        0.0,
        timeout,
    )

    rect_started = start_optional_timing(
        timings
    )

    try:
        rectangle = get_uia_popup_rectangle(
            item
        )
    finally:
        finish_optional_timing(
            timings,
            "open_save_as_get_item_rect",
            rect_started,
        )

    if rectangle is None:
        return 0

    left, top, right, bottom = rectangle

    if right <= left or bottom <= top:
        return 0

    x = (left + right) // 2
    y = (top + bottom) // 2

    click_started = start_optional_timing(
        timings
    )

    try:
        mouse.click(
            button="left",
            coords=(x, y),
        )
    except Exception:
        add_optional_timing(
            timings,
            "open_save_as_raw_mouse_click",
            click_started,
        )
        return 0

    add_optional_timing(
        timings,
        "open_save_as_raw_mouse_click",
        click_started,
    )

    remaining = deadline - time.monotonic()

    if remaining <= 0:
        return 0

    wait_started = start_optional_timing(
        timings
    )

    try:
        return wait_for_save_as_dialog(
            main_hwnd,
            timeout=min(2.0, remaining),
        )
    finally:
        add_optional_timing(
            timings,
            "open_save_as_wait_dialog",
            wait_started,
        )



def invoke_fast_save_as_menu(
    main_hwnd: int,
    timings: dict[str, float] | None = None,
) -> int:
    """Ищет Save As по содержимому всех появившихся popup Menu."""

    file_title = ""
    save_as_title = ""

    try:
        wrapper_started = start_optional_timing(
            timings
        )

        try:
            desktop = Desktop(backend="uia")
            window = desktop.window(
                handle=main_hwnd
            )
            window.wrapper_object()
        finally:
            finish_optional_timing(
                timings,
                "open_save_as_fresh_main_wrapper",
                wrapper_started,
            )

        file_started = start_optional_timing(
            timings
        )

        try:
            menu_bar = find_uia_menu_bar(
                window,
                timeout=FAST_UIA_LOOKUP_TIMEOUT,
            )

            if menu_bar is None:
                file_match = None
            else:
                file_match = (
                    wait_for_shallow_uia_menu_item(
                        menu_bar,
                        FILE_MENU_TEXTS,
                        cached_title=(
                            SAVE_AS_MENU_CACHE.get(
                                "file_title",
                                "",
                            )
                        ),
                        timeout=FAST_UIA_LOOKUP_TIMEOUT,
                    )
                )
        finally:
            finish_optional_timing(
                timings,
                "open_save_as_find_file_menu",
                file_started,
            )

        if file_match is None:
            SAVE_AS_MENU_CACHE.clear()
            return 0

        file_menu, file_title = file_match

        file_rectangle = get_uia_popup_rectangle(
            file_menu
        )

        if file_rectangle is not None:
            left, top, right, bottom = file_rectangle

            if right > left and bottom > top:
                if (
                    SAVE_AS_MOUSE_CACHE.get("hwnd")
                    != main_hwnd
                ):
                    SAVE_AS_MOUSE_CACHE.clear()

                SAVE_AS_MOUSE_CACHE["hwnd"] = main_hwnd
                SAVE_AS_MOUSE_CACHE["file_point"] = (
                    (left + right) // 2,
                    (top + bottom) // 2,
                )

        snapshot_started = start_optional_timing(
            timings
        )

        try:
            before_handles = (
                snapshot_visible_uia_popup_handles(
                    desktop,
                    main_hwnd,
                )
            )
        finally:
            add_optional_timing(
                timings,
                "open_save_as_enumerate_popup_menus",
                snapshot_started,
            )

        invoke_file_started = start_optional_timing(
            timings
        )

        try:
            invoke_uia_control(file_menu)
        finally:
            finish_optional_timing(
                timings,
                "open_save_as_invoke_file_menu",
                invoke_file_started,
            )

        popup_started = start_optional_timing(
            timings
        )

        try:
            save_as_match, inspections = (
                find_save_as_in_visible_popups(
                    desktop,
                    main_hwnd,
                    before_handles,
                    timeout=FAST_UIA_LOOKUP_TIMEOUT,
                    debug=timings is not None,
                    timings=timings,
                )
            )
        finally:
            finish_optional_timing(
                timings,
                "open_save_as_find_popup_menu",
                popup_started,
            )

        if save_as_match is None:
            save_as_match = find_save_as_through_submenu(
                desktop,
                main_hwnd,
                inspections,
                timeout=FAST_UIA_LOOKUP_TIMEOUT,
                debug=timings is not None,
                timings=timings,
            )

        if save_as_match is None:
            SAVE_AS_MENU_CACHE.clear()
            return 0

        save_as_item, save_as_title = save_as_match
        dialog_hwnd = invoke_save_as_item_and_wait(
            save_as_item,
            main_hwnd,
            timeout=min(
                SAVE_AS_DIALOG_TIMEOUT,
                3.0,
            ),
            timings=timings,
        )

        if not dialog_hwnd:
            SAVE_AS_MENU_CACHE.clear()
            return 0

        SAVE_AS_MENU_CACHE.update(
            {
                "file_title": file_title,
                "save_as_title": save_as_title,
            }
        )
        return dialog_hwnd
    except Exception:
        SAVE_AS_MENU_CACHE.clear()
        return 0


def invoke_uia_file_menu_item(
    main_hwnd: int,
    item_texts: set[str],
    timings: dict[str, float] | None = None,
) -> bool:
    """Legacy fallback с полным UIA-обходом и диагностикой."""

    collect_started = start_optional_timing(
        timings
    )

    try:
        controls = collect_uia_menu_controls(
            main_hwnd
        )
    finally:
        finish_optional_timing(
            timings,
            "open_save_as_legacy_collect_initial",
            collect_started,
        )

    def find_item():
        return next(
            (
                control
                for control in controls
                if (
                    get_uia_control_type(control)
                    == "menuitem"
                    and uia_control_matches(
                        control,
                        item_texts,
                    )
                )
            ),
            None,
        )

    find_started = start_optional_timing(
        timings
    )

    try:
        target = find_item()
    finally:
        finish_optional_timing(
            timings,
            "open_save_as_legacy_find_initial",
            find_started,
        )

    if target is not None:
        invoke_started = start_optional_timing(
            timings
        )

        try:
            rectangle = get_uia_popup_rectangle(target)
            if rectangle is None:
                return False
            left, top, right, bottom = rectangle
            if right <= left or bottom <= top:
                return False

            point = (
                (left + right) // 2,
                (top + bottom) // 2,
            )

            if (
                SAVE_AS_MOUSE_CACHE.get("hwnd")
                != main_hwnd
            ):
                SAVE_AS_MOUSE_CACHE.clear()

            SAVE_AS_MOUSE_CACHE["hwnd"] = main_hwnd
            SAVE_AS_MOUSE_CACHE["save_as_point"] = point

            mouse.click(
                button="left",
                coords=point,
            )
        finally:
            add_optional_timing(
                timings,
                "open_save_as_legacy_invoke_target",
                invoke_started,
            )

        return True

    file_started = start_optional_timing(
        timings
    )

    try:
        file_item = next(
            (
                control
                for control in controls
                if (
                    get_uia_control_type(control)
                    == "menuitem"
                    and uia_control_matches(
                        control,
                        FILE_MENU_TEXTS,
                    )
                )
            ),
            None,
        )
    finally:
        finish_optional_timing(
            timings,
            "open_save_as_legacy_find_file",
            file_started,
        )

    if file_item is None:
        return False

    file_rectangle = get_uia_popup_rectangle(
        file_item
    )

    if file_rectangle is not None:
        left, top, right, bottom = file_rectangle

        if right > left and bottom > top:
            if (
                SAVE_AS_MOUSE_CACHE.get("hwnd")
                != main_hwnd
            ):
                SAVE_AS_MOUSE_CACHE.clear()

            SAVE_AS_MOUSE_CACHE["hwnd"] = main_hwnd
            SAVE_AS_MOUSE_CACHE["file_point"] = (
                (left + right) // 2,
                (top + bottom) // 2,
            )

    invoke_file_started = start_optional_timing(
        timings
    )

    try:
        invoke_uia_control(file_item)
        time.sleep(0.3)
    finally:
        finish_optional_timing(
            timings,
            "open_save_as_legacy_invoke_file",
            invoke_file_started,
        )

    collect_started = start_optional_timing(
        timings
    )

    try:
        controls = collect_uia_menu_controls(
            main_hwnd
        )
    finally:
        finish_optional_timing(
            timings,
            "open_save_as_legacy_collect_after_file",
            collect_started,
        )

    find_started = start_optional_timing(
        timings
    )

    try:
        target = find_item()
    finally:
        finish_optional_timing(
            timings,
            "open_save_as_legacy_find_after_file",
            find_started,
        )

    if target is None:
        return False

    invoke_started = start_optional_timing(
        timings
    )

    try:
        rectangle = get_uia_popup_rectangle(target)
        if rectangle is None:
            return False
        left, top, right, bottom = rectangle
        if right <= left or bottom <= top:
            return False

        point = (
            (left + right) // 2,
            (top + bottom) // 2,
        )

        if (
            SAVE_AS_MOUSE_CACHE.get("hwnd")
            != main_hwnd
        ):
            SAVE_AS_MOUSE_CACHE.clear()

        SAVE_AS_MOUSE_CACHE["hwnd"] = main_hwnd
        SAVE_AS_MOUSE_CACHE["save_as_point"] = point

        mouse.click(
            button="left",
            coords=point,
        )
    finally:
        add_optional_timing(
            timings,
            "open_save_as_legacy_invoke_target",
            invoke_started,
        )

    return True


def find_save_as_dialog(
    main_hwnd: int,
) -> int:
    """Находит принадлежащий Wilcom стандартный диалог Save As."""

    matches: list[int] = []

    def callback(hwnd: int, _) -> None:
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return

            class_name = win32gui.GetClassName(
                hwnd
            )
            title = normalize_menu_text(
                win32gui.GetWindowText(hwnd)
            )
            owner_hwnd = (
                win32gui.GetWindow(
                    hwnd,
                    win32con.GW_OWNER,
                )
                or 0
            )
            parent_hwnd = (
                win32gui.GetParent(hwnd)
                or 0
            )
        except Exception:
            return

        if (
            class_name == "#32770"
            and menu_text_matches(
                title,
                SAVE_AS_DIALOG_TITLES,
            )
            and main_hwnd in {
                owner_hwnd,
                parent_hwnd,
            }
        ):
            matches.append(hwnd)

    win32gui.EnumWindows(
        callback,
        None,
    )

    return matches[0] if matches else 0


def wait_for_save_as_dialog(
    main_hwnd: int,
    timeout: float = SAVE_AS_DIALOG_TIMEOUT,
) -> int:
    deadline = time.monotonic() + timeout

    while True:
        dialog_hwnd = find_save_as_dialog(
            main_hwnd
        )

        if dialog_hwnd:
            return dialog_hwnd

        remaining = deadline - time.monotonic()

        if remaining <= 0:
            return 0

        time.sleep(
            min(0.1, remaining)
        )


def open_save_as_dialog(
    main_hwnd: int,
    timeout: float = SAVE_AS_DIALOG_TIMEOUT,
    timings: dict[str, float] | None = None,
) -> int:
    """Открывает Save As через Win32 command, затем через UIA."""

    global _SAVE_AS_WIN32_COMMAND_ID
    global _SAVE_AS_WIN32_COMMAND_HWND

    if timings is not None:
        for key in (
            "open_save_as_cached_mouse",
            "open_save_as_cached_win32_command",
            "open_save_as_scan_win32_menu",
            "open_save_as_send_wm_command",
            "open_save_as_wait_dialog_win32",
            "open_save_as_uia_fast_path",
            "open_save_as_legacy_fallback",
            "open_save_as_legacy_collect_initial",
            "open_save_as_legacy_find_initial",
            "open_save_as_legacy_find_file",
            "open_save_as_legacy_invoke_file",
            "open_save_as_legacy_collect_after_file",
            "open_save_as_legacy_find_after_file",
            "open_save_as_legacy_invoke_target",
            "open_save_as_legacy_wait_dialog",
            "open_save_as_fresh_main_wrapper",
            "open_save_as_find_file_menu",
            "open_save_as_invoke_file_menu",
            "open_save_as_enumerate_popup_menus",
            "open_save_as_inspect_popup_items",
            "open_save_as_find_popup_menu",
            "open_save_as_find_save_as_item",
            "open_save_as_invoke_save_as",
            "open_save_as_wait_dialog",
            "open_save_as_total",
            "open_save_as_dialog",
        ):
            timings.pop(key, None)

    total_started = start_optional_timing(
        timings
    )
    dialog_timeout = min(
        SAVE_AS_DIALOG_TIMEOUT,
        max(0.0, timeout),
    )

    def wait_dialog_with_timing(
        stage_key: str,
        stage_timeout: float,
    ) -> int:
        wait_started = start_optional_timing(
            timings
        )

        try:
            return wait_for_save_as_dialog(
                main_hwnd,
                timeout=max(0.0, stage_timeout),
            )
        finally:
            add_optional_timing(
                timings,
                stage_key,
                wait_started,
            )

            if stage_key != "open_save_as_wait_dialog":
                add_optional_timing(
                    timings,
                    "open_save_as_wait_dialog",
                    wait_started,
                )

    def send_win32_command(
        command_id: int,
    ) -> None:
        send_started = start_optional_timing(
            timings
        )

        try:
            post_win32_menu_command(
                main_hwnd,
                command_id,
            )
        finally:
            add_optional_timing(
                timings,
                "open_save_as_send_wm_command",
                send_started,
            )

    try:
        focus_window(main_hwnd)

        mouse_started = start_optional_timing(
            timings
        )

        try:
            file_point = SAVE_AS_MOUSE_CACHE.get(
                "file_point"
            )
            save_as_point = SAVE_AS_MOUSE_CACHE.get(
                "save_as_point"
            )

            if (
                SAVE_AS_MOUSE_CACHE.get("hwnd")
                == main_hwnd
                and isinstance(file_point, tuple)
                and len(file_point) == 2
                and isinstance(save_as_point, tuple)
                and len(save_as_point) == 2
            ):
                try:
                    mouse.click(
                        button="left",
                        coords=file_point,
                    )
                    time.sleep(0.25)
                    mouse.click(
                        button="left",
                        coords=save_as_point,
                    )

                    dialog_hwnd = (
                        wait_dialog_with_timing(
                            "open_save_as_wait_dialog",
                            min(
                                1.0,
                                dialog_timeout,
                            ),
                        )
                    )
                except Exception:
                    dialog_hwnd = 0

                if dialog_hwnd:
                    return dialog_hwnd

                SAVE_AS_MOUSE_CACHE.clear()
        finally:
            finish_optional_timing(
                timings,
                "open_save_as_cached_mouse",
                mouse_started,
            )

        cached_started = start_optional_timing(
            timings
        )

        try:
            cached_command_id = (
                _SAVE_AS_WIN32_COMMAND_ID
            )

            if (
                main_hwnd
                not in _SAVE_AS_WIN32_DISABLED_HWNDS
                and cached_command_id is not None
                and _SAVE_AS_WIN32_COMMAND_HWND
                == main_hwnd
            ):
                try:
                    send_win32_command(
                        cached_command_id
                    )
                    dialog_hwnd = (
                        wait_dialog_with_timing(
                            "open_save_as_wait_dialog_win32",
                            min(
                                WIN32_CACHED_DIALOG_TIMEOUT,
                                dialog_timeout,
                            ),
                        )
                    )
                except Exception:
                    dialog_hwnd = 0

                if dialog_hwnd:
                    return dialog_hwnd

                _SAVE_AS_WIN32_COMMAND_ID = None
                _SAVE_AS_WIN32_COMMAND_HWND = None
        finally:
            finish_optional_timing(
                timings,
                "open_save_as_cached_win32_command",
                cached_started,
            )

        scan_started = start_optional_timing(
            timings
        )

        try:
            if (
                main_hwnd
                in _SAVE_AS_WIN32_DISABLED_HWNDS
            ):
                win32_item = None
            else:
                win32_item = scan_save_as_win32_menu(
                    main_hwnd,
                    debug=timings is not None,
                )
        except Exception:
            win32_item = None
        finally:
            finish_optional_timing(
                timings,
                "open_save_as_scan_win32_menu",
                scan_started,
            )

        if win32_item is not None:
            try:
                send_win32_command(
                    win32_item.command_id
                )
                dialog_hwnd = wait_dialog_with_timing(
                    "open_save_as_wait_dialog_win32",
                    min(
                        WIN32_DIALOG_TIMEOUT,
                        dialog_timeout,
                    ),
                )
            except Exception:
                dialog_hwnd = 0

            if dialog_hwnd:
                _SAVE_AS_WIN32_COMMAND_ID = (
                    win32_item.command_id
                )
                _SAVE_AS_WIN32_COMMAND_HWND = (
                    main_hwnd
                )
                return dialog_hwnd

        uia_started = start_optional_timing(
            timings
        )

        try:
            dialog_hwnd = invoke_fast_save_as_menu(
                main_hwnd,
                timings=timings,
            )

            if dialog_hwnd:
                return dialog_hwnd
        finally:
            finish_optional_timing(
                timings,
                "open_save_as_uia_fast_path",
                uia_started,
            )

        SAVE_AS_MENU_CACHE.clear()
        print(
            "Быстрые способы Save As не сработали, "
            "использую legacy fallback."
        )
        fallback_started = start_optional_timing(
            timings
        )

        try:
            legacy_invoked = (
                invoke_uia_file_menu_item(
                    main_hwnd,
                    SAVE_AS_MENU_TEXTS,
                    timings=timings,
                )
            )

            if legacy_invoked:
                dialog_hwnd = wait_dialog_with_timing(
                    "open_save_as_legacy_wait_dialog",
                    dialog_timeout,
                )
            else:
                dialog_hwnd = 0
        finally:
            finish_optional_timing(
                timings,
                "open_save_as_legacy_fallback",
                fallback_started,
            )

        if dialog_hwnd:
            return dialog_hwnd

        raise TimeoutError(
            "Диалог «Сохранить как» не появился "
            "после Win32 WM_COMMAND, быстрого UIA "
            "и legacy fallback."
        )
    finally:
        finish_optional_timing(
            timings,
            "open_save_as_total",
            total_started,
        )

        if (
            timings is not None
            and "open_save_as_total" in timings
        ):
            for key in (
                "open_save_as_cached_win32_command",
                "open_save_as_scan_win32_menu",
                "open_save_as_send_wm_command",
                "open_save_as_wait_dialog_win32",
                "open_save_as_uia_fast_path",
                "open_save_as_legacy_fallback",
            ):
                timings.setdefault(key, 0.0)

            timings["open_save_as_dialog"] = (
                timings["open_save_as_total"]
            )


def find_visible_child_by_control_id(
    parent_hwnd: int,
    control_id: int,
    class_name: str | None = None,
) -> list[int]:
    matches: list[int] = []

    def callback(child_hwnd: int, _) -> None:
        try:
            if not win32gui.IsWindowVisible(
                child_hwnd
            ):
                return

            if (
                win32gui.GetDlgCtrlID(child_hwnd)
                != control_id
            ):
                return

            if (
                class_name is not None
                and win32gui.GetClassName(
                    child_hwnd
                )
                != class_name
            ):
                return
        except Exception:
            return

        matches.append(child_hwnd)

    win32gui.EnumChildWindows(
        parent_hwnd,
        callback,
        None,
    )

    return matches


def get_control_hwnd(
    control,
) -> int:
    return int(
        safe_uia_call(
            lambda: (
                control.element_info.handle
                or control.handle
                or 0
            ),
            0,
        )
    )


def find_uia_save_as_edit(
    dialog_hwnd: int,
    timeout: float,
):
    """Находит Edit 1001 строго внутри FileNameControlHost."""

    deadline = time.time() + max(
        0.0,
        timeout,
    )
    dialog = Desktop(
        backend="uia"
    ).window(
        handle=dialog_hwnd
    )
    host = dialog.child_window(
        auto_id="FileNameControlHost",
        control_type="ComboBox",
    )
    edit_specification = host.child_window(
        auto_id="1001",
        control_type="Edit",
    )
    exists = getattr(
        edit_specification,
        "exists",
        None,
    )

    if callable(exists):
        remaining = max(
            0.05,
            deadline - time.time(),
        )

        if not exists(
            timeout=remaining,
            retry_interval=0.05,
        ):
            raise RuntimeError(
                "UIA Edit 1001 внутри "
                "FileNameControlHost не найден."
            )

    return edit_specification.wrapper_object()


def find_win32_save_as_edit(
    dialog_hwnd: int,
):
    edit_handles = find_visible_child_by_control_id(
        dialog_hwnd,
        SAVE_AS_FILE_NAME_CONTROL_ID,
        class_name="Edit",
    )

    if not edit_handles:
        return None, 0

    edit_hwnd = edit_handles[0]
    wrapper = safe_uia_call(
        lambda: (
            Desktop(
                backend="win32"
            ).window(
                handle=edit_hwnd
            ).wrapper_object()
        ),
        None,
    )

    return wrapper, edit_hwnd


def read_save_as_field_values(
    uia_edit,
    edit_hwnd: int,
) -> dict[str, str]:
    """Читает поле имени через все доступные API."""

    readings: dict[str, str] = {}

    def read(
        label: str,
        callback,
    ) -> None:
        value = safe_uia_call(
            callback,
            "",
        )

        if isinstance(value, (list, tuple)):
            items = [
                str(item or "")
                .strip()
                .strip('"')
                for item in value
            ]

            if not items:
                readings[label] = ""
                return

            for index, item in enumerate(
                items
            ):
                readings[
                    f"{label}[{index}]"
                ] = item

            return

        readings[label] = str(
            value or ""
        ).strip().strip('"')

    if uia_edit is not None:
        read(
            "UIA value",
            lambda: (
                uia_edit.iface_value.CurrentValue
            ),
        )
        read(
            "UIA get_value",
            lambda: uia_edit.get_value(),
        )
        read(
            "UIA window_text",
            lambda: uia_edit.window_text(),
        )

    win32_wrapper = None

    if edit_hwnd:
        win32_wrapper = safe_uia_call(
            lambda: (
                Desktop(
                    backend="win32"
                ).window(
                    handle=edit_hwnd
                ).wrapper_object()
            ),
            None,
        )

    if win32_wrapper is not None:
        read(
            "Win32 wrapper text",
            lambda: win32_wrapper.window_text(),
        )
        read(
            "Win32 wrapper texts",
            lambda: win32_wrapper.texts(),
        )

    if edit_hwnd:
        read(
            "raw GetWindowText",
            lambda: win32gui.GetWindowText(
                edit_hwnd
            ),
        )

    return readings


def save_as_value_matches(
    value: str,
    output_path: Path,
) -> bool:
    value = value.strip().strip('"')

    if not value:
        return False

    expected_path = os.path.normcase(
        os.path.normpath(
            str(output_path.resolve())
        )
    )
    actual_path = os.path.normcase(
        os.path.normpath(value)
    )

    if actual_path == expected_path:
        return True

    return (
        value.casefold()
        == output_path.name.casefold()
    )


def accepted_save_as_value(
    readings: dict[str, str],
    output_path: Path,
) -> str:
    for value in readings.values():
        if save_as_value_matches(
            value,
            output_path,
        ):
            return value

    return ""


def format_save_as_readings(
    readings: dict[str, str],
) -> str:
    if not readings:
        return "<нет доступных способов чтения>"

    return "\n".join(
        f"{label}: {value!r}"
        for label, value in readings.items()
    )


def wait_for_save_as_field_value(
    uia_edit,
    edit_hwnd: int,
    output_path: Path,
    deadline: float,
) -> tuple[str, dict[str, str]]:
    readings: dict[str, str] = {}

    while time.time() < deadline:
        readings = read_save_as_field_values(
            uia_edit,
            edit_hwnd,
        )
        accepted = accepted_save_as_value(
            readings,
            output_path,
        )

        if accepted:
            return accepted, readings

        time.sleep(0.05)

    readings = read_save_as_field_values(
        uia_edit,
        edit_hwnd,
    )

    return (
        accepted_save_as_value(
            readings,
            output_path,
        ),
        readings,
    )


def verify_save_as_path(
    dialog_hwnd: int,
    output_path: Path,
    timeout: float = 1.0,
) -> str:
    """Проверяет, что поле содержит новый output, а не старое имя."""

    deadline = time.time() + timeout
    uia_edit = safe_uia_call(
        lambda: find_uia_save_as_edit(
            dialog_hwnd,
            max(
                0.05,
                deadline - time.time(),
            ),
        ),
        None,
    )
    edit_hwnd = get_control_hwnd(
        uia_edit
    ) if uia_edit is not None else 0

    if not edit_hwnd:
        _, edit_hwnd = find_win32_save_as_edit(
            dialog_hwnd
        )

    accepted, readings = (
        wait_for_save_as_field_value(
            uia_edit,
            edit_hwnd,
            output_path,
            deadline,
        )
    )

    if accepted:
        return accepted

    raise RuntimeError(
        "Поле имени файла содержит старое "
        "или неправильное значение.\n"
        f"Ожидалось: {str(output_path.resolve())!r} "
        f"или {output_path.name!r}\n"
        f"{format_save_as_readings(readings)}"
    )


def set_save_as_path(
    dialog_hwnd: int,
    output_path: Path,
    timeout: float = 3.0,
) -> int:
    """UIA-first устанавливает и проверяет полный output path."""

    output_path = output_path.resolve()
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    expected = str(output_path)
    deadline = time.time() + timeout
    errors: list[str] = []
    last_readings: dict[str, str] = {}
    uia_edit = safe_uia_call(
        lambda: find_uia_save_as_edit(
            dialog_hwnd,
            max(
                0.05,
                deadline - time.time(),
            ),
        ),
        None,
    )
    win32_wrapper, win32_hwnd = (
        find_win32_save_as_edit(
            dialog_hwnd
        )
    )
    edit_hwnd = (
        get_control_hwnd(uia_edit)
        if uia_edit is not None
        else 0
    ) or win32_hwnd

    if uia_edit is not None:
        safe_uia_call(
            lambda: uia_edit.set_focus(),
            None,
        )
        uia_setters = (
            (
                "UIA set_edit_text",
                lambda: uia_edit.set_edit_text(
                    expected
                ),
            ),
            (
                "UIA ValuePattern",
                lambda: (
                    uia_edit.iface_value.SetValue(
                        expected
                    )
                ),
            ),
            (
                "UIA set_value",
                lambda: uia_edit.set_value(
                    expected
                ),
            ),
        )

        for label, setter in uia_setters:
            if time.time() >= deadline:
                break

            try:
                setter()
            except Exception as error:
                errors.append(
                    f"{label}: {error}"
                )
                continue

            accepted, last_readings = (
                wait_for_save_as_field_value(
                    uia_edit,
                    edit_hwnd,
                    output_path,
                    min(
                        deadline,
                        time.time() + 0.7,
                    ),
                )
            )

            if accepted:
                print(
                    "Поле имени файла установлено:",
                    accepted,
                )
                return edit_hwnd

    if (
        win32_wrapper is not None
        and time.time() < deadline
    ):
        try:
            win32_wrapper.set_edit_text(
                expected
            )
        except Exception as error:
            errors.append(
                "Win32 wrapper set_edit_text: "
                f"{error}"
            )
        else:
            accepted, last_readings = (
                wait_for_save_as_field_value(
                    uia_edit,
                    edit_hwnd,
                    output_path,
                    min(
                        deadline,
                        time.time() + 0.7,
                    ),
                )
            )

            if accepted:
                print(
                    "Поле имени файла установлено:",
                    accepted,
                )
                return edit_hwnd

    if edit_hwnd and time.time() < deadline:
        remaining_ms = max(
            1,
            int(
                (
                    deadline - time.time()
                )
                * 1000
            ),
        )

        try:
            win32gui.SendMessageTimeout(
                edit_hwnd,
                win32con.WM_SETTEXT,
                0,
                expected,
                win32con.SMTO_ABORTIFHUNG,
                remaining_ms,
            )
        except Exception as error:
            errors.append(
                f"WM_SETTEXT: {error}"
            )
        else:
            accepted, last_readings = (
                wait_for_save_as_field_value(
                    uia_edit,
                    edit_hwnd,
                    output_path,
                    deadline,
                )
            )

            if accepted:
                print(
                    "Поле имени файла установлено:",
                    accepted,
                )
                return edit_hwnd

    if not edit_hwnd:
        errors.append(
            "Edit с automation/control id 1001 "
            "не найден."
        )

    details = format_save_as_readings(
        last_readings
    )
    error_details = "\n".join(
        errors
    )
    raise RuntimeError(
        "Полный путь не установился в поле "
        "имени файла Save As.\n"
        f"Ожидалось: {expected!r} "
        f"или {output_path.name!r}\n"
        f"{details}"
        + (
            f"\nОшибки способов записи:\n"
            f"{error_details}"
            if error_details
            else ""
        )
    )


def find_overwrite_confirmation(
    save_as_hwnd: int,
    main_hwnd: int,
) -> tuple[int, int] | None:
    matches: list[tuple[int, int]] = []

    def callback(hwnd: int, _) -> None:
        if hwnd == save_as_hwnd:
            return

        try:
            if not win32gui.IsWindowVisible(hwnd):
                return

            if win32gui.GetClassName(hwnd) != "#32770":
                return

            owner_hwnd = (
                win32gui.GetWindow(
                    hwnd,
                    win32con.GW_OWNER,
                )
                or 0
            )
            parent_hwnd = (
                win32gui.GetParent(hwnd)
                or 0
            )

            if not {
                owner_hwnd,
                parent_hwnd,
            }.intersection(
                {
                    save_as_hwnd,
                    main_hwnd,
                }
            ):
                return

            button_hwnd = win32gui.GetDlgItem(
                hwnd,
                win32con.IDYES,
            )

            if not button_hwnd:
                return

            button_text = (
                win32gui.GetWindowText(button_hwnd)
                .replace("&", "")
                .strip()
                .casefold()
            )
        except Exception:
            return

        if (
            not button_text
            or button_text
            in OVERWRITE_BUTTON_TEXTS
        ):
            matches.append(
                (
                    hwnd,
                    button_hwnd,
                )
            )

    win32gui.EnumWindows(
        callback,
        None,
    )

    return matches[0] if matches else None


def window_is_closed(hwnd: int) -> bool:
    try:
        return not win32gui.IsWindow(hwnd)
    except Exception:
        return True


def cancel_owned_confirmation_best_effort(
    dialog_hwnd: int,
    timeout: float,
) -> None:
    """Закрывает overwrite-confirmation через No/Cancel/Escape."""

    owned_dialogs: list[int] = []
    deadline = time.time() + timeout

    def callback(hwnd: int, _) -> None:
        if hwnd == dialog_hwnd:
            return

        try:
            if (
                not win32gui.IsWindowVisible(hwnd)
                or win32gui.GetClassName(hwnd)
                != "#32770"
            ):
                return

            owner = (
                win32gui.GetWindow(
                    hwnd,
                    win32con.GW_OWNER,
                )
                or 0
            )
            parent = (
                win32gui.GetParent(hwnd)
                or 0
            )
        except Exception:
            return

        if dialog_hwnd in {
            owner,
            parent,
        }:
            owned_dialogs.append(hwnd)

    safe_uia_call(
        lambda: win32gui.EnumWindows(
            callback,
            None,
        ),
        None,
    )

    for owned_hwnd in owned_dialogs:
        button_hwnd = 0

        for control_id in (
            win32con.IDNO,
            win32con.IDCANCEL,
        ):
            button_hwnd = safe_uia_call(
                lambda control_id=control_id: (
                    win32gui.GetDlgItem(
                        owned_hwnd,
                        control_id,
                    )
                ),
                0,
            )

            if button_hwnd:
                break

        if button_hwnd:
            safe_uia_call(
                lambda: win32gui.PostMessage(
                    button_hwnd,
                    win32con.BM_CLICK,
                    0,
                    0,
                ),
                None,
            )
        else:
            safe_uia_call(
                lambda: win32gui.PostMessage(
                    owned_hwnd,
                    win32con.WM_KEYDOWN,
                    win32con.VK_ESCAPE,
                    0,
                ),
                None,
            )
            safe_uia_call(
                lambda: win32gui.PostMessage(
                    owned_hwnd,
                    win32con.WM_KEYUP,
                    win32con.VK_ESCAPE,
                    0,
                ),
                None,
            )

        while time.time() < deadline:
            if window_is_closed(owned_hwnd):
                break

            time.sleep(0.05)


def cancel_save_as_best_effort(
    dialog_hwnd: int | None,
    timeout: float = 3.0,
) -> None:
    """Отменяет Save As, никогда не скрывая исходную ошибку."""

    if not dialog_hwnd:
        return

    try:
        if not win32gui.IsWindow(dialog_hwnd):
            return

        deadline = time.time() + timeout
        cancel_owned_confirmation_best_effort(
            dialog_hwnd,
            timeout=min(
                1.0,
                max(
                    0.05,
                    deadline - time.time(),
                ),
            ),
        )
        cancel_buttons = (
            find_visible_child_by_control_id(
                dialog_hwnd,
                win32con.IDCANCEL,
                class_name="Button",
            )
        )

        if cancel_buttons:
            win32gui.PostMessage(
                cancel_buttons[0],
                win32con.BM_CLICK,
                0,
                0,
            )
        else:
            safe_uia_call(
                lambda: win32gui.SetForegroundWindow(
                    dialog_hwnd
                ),
                None,
            )
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

        while time.time() < deadline:
            if window_is_closed(dialog_hwnd):
                print(
                    "Диалог Save As отменён "
                    "после ошибки."
                )
                return

            time.sleep(0.05)
    except Exception:
        pass


def confirm_save_as(
    dialog_hwnd: int,
    output_path: Path,
    main_hwnd: int,
    timeout: float = 30.0,
    timings: dict[str, float] | None = None,
) -> None:
    """Подтверждает Save As и проверяет устойчивый файл на диске."""

    if timings is not None:
        for key in (
            "click_save",
            "wait_save_dialog_closed",
            "wait_new_title",
            "wait_output_file",
            "wait_stable_size",
        ):
            timings.pop(key, None)

    output_path = output_path.resolve()
    verify_save_as_path(
        dialog_hwnd,
        output_path,
        timeout=1.0,
    )
    save_buttons = find_visible_child_by_control_id(
        dialog_hwnd,
        SAVE_AS_BUTTON_CONTROL_ID,
        class_name="Button",
    )

    if not save_buttons:
        raise RuntimeError(
            "Кнопка Save As "
            "(Button, control id 1) не найдена."
        )

    click_started = (
        time.perf_counter()
        if timings is not None
        else None
    )

    try:
        win32gui.PostMessage(
            save_buttons[0],
            win32con.BM_CLICK,
            0,
            0,
        )
    finally:
        if timings is not None and click_started is not None:
            timings["click_save"] = (
                time.perf_counter()
                - click_started
            )

    print("Кнопка «Сохранить» нажата.")
    expected_stem = output_path.stem.casefold()
    deadline = time.time() + timeout
    last_title = ""
    last_size: int | None = None
    stable_size_readings = 0
    confirmed_overwrite_dialogs: set[int] = set()
    save_as_closed = False
    wait_started = (
        time.perf_counter()
        if timings is not None
        else None
    )
    output_seen_at: float | None = None

    while time.time() < deadline:
        overwrite = find_overwrite_confirmation(
            dialog_hwnd,
            main_hwnd,
        )

        if (
            overwrite is not None
            and overwrite[0]
            not in confirmed_overwrite_dialogs
        ):
            overwrite_hwnd, yes_button_hwnd = (
                overwrite
            )
            win32gui.PostMessage(
                yes_button_hwnd,
                win32con.BM_CLICK,
                0,
                0,
            )
            confirmed_overwrite_dialogs.add(
                overwrite_hwnd
            )

        save_as_closed = window_is_closed(
            dialog_hwnd
        )
        last_title = safe_uia_call(
            lambda: win32gui.GetWindowText(
                main_hwnd
            ),
            "",
        )
        title_matches = (
            expected_stem
            in last_title.casefold()
        )
        observed_at = (
            time.perf_counter()
            if timings is not None
            else None
        )

        if (
            timings is not None
            and wait_started is not None
            and observed_at is not None
        ):
            if (
                save_as_closed
                and "wait_save_dialog_closed"
                not in timings
            ):
                timings[
                    "wait_save_dialog_closed"
                ] = observed_at - wait_started

            if (
                title_matches
                and "wait_new_title" not in timings
            ):
                timings["wait_new_title"] = (
                    observed_at - wait_started
                )

        current_size: int | None = None

        try:
            if output_path.is_file():
                current_size = (
                    output_path.stat().st_size
                )
        except OSError:
            current_size = None

        if (
            current_size is not None
            and current_size > 0
        ):
            if (
                timings is not None
                and wait_started is not None
                and observed_at is not None
                and "wait_output_file"
                not in timings
            ):
                output_seen_at = observed_at
                timings["wait_output_file"] = (
                    observed_at - wait_started
                )

            if current_size == last_size:
                stable_size_readings += 1
            else:
                stable_size_readings = 1

            last_size = current_size
        else:
            last_size = current_size
            stable_size_readings = 0

        if (
            timings is not None
            and observed_at is not None
            and stable_size_readings >= 2
            and "wait_stable_size" not in timings
        ):
            stable_started = (
                output_seen_at
                if output_seen_at is not None
                else wait_started
            )

            if stable_started is not None:
                timings["wait_stable_size"] = (
                    observed_at - stable_started
                )

        if (
            save_as_closed
            and title_matches
            and stable_size_readings >= 2
        ):
            return

        time.sleep(0.2)

    if not output_path.exists():
        file_status = "файл не появился"
    elif output_path.stat().st_size == 0:
        file_status = "размер файла равен нулю"
    elif stable_size_readings < 2:
        file_status = "размер файла не стабилизировался"
    else:
        file_status = "файл записан"

    raise TimeoutError(
        "Save As не завершился корректно "
        f"за {timeout:g} секунд.\n"
        f"Диалог закрыт: {save_as_closed}\n"
        "Ожидаемый stem в заголовке: "
        f"{expected_stem!r}\n"
        f"Фактический заголовок: {last_title!r}\n"
        f"Состояние файла: {file_status}."
    )


def save_document_as(
    main_hwnd: int,
    output_path: Path,
    timings: dict[str, float] | None = None,
) -> None:
    """Сохраняет текущий документ под новым полным путём."""

    output_path = output_path.resolve()
    print()
    print("Сохраняю как:")
    print(output_path)
    dialog_hwnd: int | None = None

    try:
        open_started = (
            time.perf_counter()
            if timings is not None
            else None
        )

        try:
            if timings is None:
                dialog_hwnd = open_save_as_dialog(
                    main_hwnd,
                    timeout=SAVE_AS_DIALOG_TIMEOUT,
                )
            else:
                dialog_hwnd = open_save_as_dialog(
                    main_hwnd,
                    timeout=SAVE_AS_DIALOG_TIMEOUT,
                    timings=timings,
                )
        finally:
            if timings is not None and open_started is not None:
                timings["open_save_as_dialog"] = (
                    time.perf_counter()
                    - open_started
                )

        path_started = (
            time.perf_counter()
            if timings is not None
            else None
        )

        try:
            set_save_as_path(
                dialog_hwnd,
                output_path,
                timeout=3.0,
            )
        finally:
            if timings is not None and path_started is not None:
                timings["set_save_as_path"] = (
                    time.perf_counter()
                    - path_started
                )

        if timings is None:
            confirm_save_as(
                dialog_hwnd,
                output_path,
                main_hwnd,
                timeout=10.0,
            )
        else:
            confirm_save_as(
                dialog_hwnd,
                output_path,
                main_hwnd,
                timeout=10.0,
                timings=timings,
            )
        print("Save As завершён.")
    except BaseException:
        if dialog_hwnd is None:
            dialog_hwnd = safe_uia_call(
                lambda: find_save_as_dialog(
                    main_hwnd
                ),
                0,
            )

        cancel_save_as_best_effort(
            dialog_hwnd,
            timeout=3.0,
        )
        raise


def set_document_position(
    window,
    hwnd: int,
    x: str,
    y: str,
) -> dict[str, str]:
    """Устанавливает абсолютную позицию без сохранения документа."""

    focus_window(hwnd)
    raise_for_known_open_error_dialog()

    try:
        window.set_focus()
    except Exception:
        raise_for_known_open_error_dialog()
        raise

    print()
    print("Жду загрузки и выделяю дизайн...")

    cached_controls = get_cached_position_controls(
        hwnd
    )

    if cached_controls is None:
        (
            x_pane,
            x_edit,
            y_pane,
            y_edit,
        ) = wait_for_selected_design(
            window,
            hwnd,
            timeout=60.0,
        )

        POSITION_CONTROLS_CACHE[hwnd] = (
            x_pane,
            x_edit,
            y_pane,
            y_edit,
        )
    else:
        (
            x_pane,
            x_edit,
            y_pane,
            y_edit,
        ) = cached_controls

        print()
        print(
            "Using cached position controls."
        )

    old_x = read_value(
        x_pane,
        x_edit,
    )

    old_y = read_value(
        y_pane,
        y_edit,
    )

    print()
    print("До изменения:")
    print("X:", old_x)
    print("Y:", old_y)

    set_value(
        x_edit,
        x,
    )

    (
        x_pane,
        x_edit,
        y_pane,
        y_edit,
    ) = wait_for_enabled_controls(
        window,
        main_hwnd=hwnd,
    )

    set_value(
        y_edit,
        y,
    )

    (
        x_pane,
        x_edit,
        y_pane,
        y_edit,
    ) = wait_for_enabled_controls(
        window,
        main_hwnd=hwnd,
    )

    new_x = read_value(
        x_pane,
        x_edit,
    )

    new_y = read_value(
        y_pane,
        y_edit,
    )

    verify_value(
        "X",
        new_x,
        x,
    )

    verify_value(
        "Y",
        new_y,
        y,
    )

    print()
    print("После изменения:")
    print("X:", new_x)
    print("Y:", new_y)

    return {
        "old_x": old_x,
        "old_y": old_y,
        "new_x": new_x,
        "new_y": new_y,
    }


def process_open_document(
    window,
    hwnd: int,
    x: str,
    y: str,
) -> dict[str, str]:
    """Обрабатывает и сохраняет уже открытый документ."""

    values = set_document_position(
        window,
        hwnd,
        x,
        y,
    )

    print()
    print("Сохраняю...")

    send_save_command(
        window,
        hwnd,
    )

    return values


def process_emb_file(
    file_path: Path,
    x: str,
    y: str,
    es_path: Path | None = None,
    close: bool = True,
) -> dict[str, str]:
    """Обрабатывает один EMB-файл в Wilcom."""

    file_path = file_path.resolve()

    if not file_path.exists():
        raise FileNotFoundError(
            f"Файл не найден: {file_path}"
        )

    es_exe = find_es_exe(
        es_path
    )

    print("Wilcom:")
    print(es_exe)

    print()
    print("Открываю:")
    print(file_path)

    windows_before_open = list_es_main_windows()
    title_before_open = (
        windows_before_open[0][4]
        if windows_before_open
        else ""
    )

    if title_before_open:
        print(
            "TITLE до открытия:",
            repr(title_before_open),
        )

    print()
    print("Открываю файл через Windows:")
    print(file_path)

    document_stem = file_path.stem
    hwnd: int | None = None
    window = None
    document_opened = False
    processing_succeeded = False

    try:
        os.startfile(
            str(file_path)
        )

        raise_for_known_open_error_dialog()

        # Wilcom может открыть файл в уже запущенном
        # процессе или запустить новый процесс.
        hwnd = wait_for_es_main_window(
            timeout=60.0,
        )

        raise_for_known_open_error_dialog()

        active_title = wait_for_document_open(
            hwnd,
            file_path,
            timeout=60.0,
        )
        document_opened = True

        time.sleep(0.75)
        raise_for_known_open_error_dialog()

        print()
        print("Использую окно Wilcom:")
        print("HWND:", hwnd)
        print(
            "TITLE:",
            repr(active_title),
        )

        # UIA-обёртка создаётся только после подтверждения
        # нужного документа по заголовку.
        window = Desktop(
            backend="uia"
        ).window(
            handle=hwnd
        )

        values = process_open_document(
            window,
            hwnd,
            x,
            y,
        )

        if close:
            close_document_and_wait(
                window,
                hwnd,
                document_stem,
                timeout=20.0,
                save=True,
            )
            document_opened = False

            print("Файл сохранён.")
            print("Документ закрыт.")

        processing_succeeded = True

        return {
            "file": str(file_path),
            **values,
            "status": "success",
        }

    finally:
        if (
            document_opened
            and not processing_succeeded
            and hwnd is not None
        ):
            try:
                close_document_best_effort(
                    hwnd,
                    document_stem,
                    window=window,
                )
            except Exception:
                pass


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "file",
        type=Path,
        help="Путь к файлу Wilcom",
    )

    parser.add_argument(
        "--x",
        required=True,
        help="Позиция X",
    )

    parser.add_argument(
        "--y",
        required=True,
        help="Позиция Y",
    )

    parser.add_argument(
        "--es",
        type=Path,
        help="Необязательный путь к ES.EXE",
    )

    parser.add_argument(
        "--close",
        action="store_true",
        help="Закрыть документ после сохранения",
    )

    args = parser.parse_args()

    process_emb_file(
        file_path=args.file,
        x=args.x,
        y=args.y,
        es_path=args.es,
        close=args.close,
    )


if __name__ == "__main__":
    main()
