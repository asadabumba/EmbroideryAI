import argparse
import os
import time
from pathlib import Path

import psutil
import win32con
import win32gui
import win32process
from pywinauto import Desktop, mouse


X_AUTOMATION_ID = "6586"
Y_AUTOMATION_ID = "6587"
OPEN_DESIGN_ERROR_TITLE = "Невозможно открыть дизайн"
PREFERRED_WINDOW_TITLE = "Ultimate Special Edition"

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


def find_document_canvas(
    main_hwnd: int,
) -> tuple[int, int] | None:
    """
    Ищет большое рабочее поле документа Wilcom.

    У обнаруженной версии класс рабочего поля:
    AfxFrameOrView140u.
    """

    candidates: list[
        tuple[int, int, int]
    ] = []

    def callback(hwnd: int, _) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return

        try:
            class_name = win32gui.GetClassName(hwnd)
        except Exception:
            return

        if class_name != "AfxFrameOrView140u":
            return

        left, top, right, bottom = (
            win32gui.GetWindowRect(hwnd)
        )

        width = right - left
        height = bottom - top

        if width < 200 or height < 150:
            return

        center_x = left + width // 2
        center_y = top + height // 2

        candidates.append(
            (
                width * height,
                center_x,
                center_y,
            )
        )

    win32gui.EnumChildWindows(
        main_hwnd,
        callback,
        None,
    )

    if not candidates:
        return None

    candidates.sort(reverse=True)

    _, x, y = candidates[0]

    return x, y


def click_document_canvas(
    main_hwnd: int,
) -> None:
    """Кликает по рабочему полю, чтобы Ctrl+A выбрал дизайн."""

    point = find_document_canvas(
        main_hwnd
    )

    if point is None:
        left, top, right, bottom = (
            win32gui.GetWindowRect(main_hwnd)
        )

        width = right - left
        height = bottom - top

        # Запасная точка в правой центральной части окна.
        point = (
            left + int(width * 0.68),
            top + int(height * 0.60),
        )

    mouse.click(
        button="left",
        coords=point,
    )


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

    while time.time() < deadline:
        raise_for_known_open_error_dialog()

        try:
            focus_window(main_hwnd)
            window.set_focus()

            click_document_canvas(
                main_hwnd
            )

            time.sleep(0.3)

            window.type_keys(
                "^a",
                set_foreground=True,
            )

            time.sleep(0.8)

            controls = get_position_controls(
                window,
                require_enabled=True,
            )

            return controls

        except Exception as error:
            last_error = error
            raise_for_known_open_error_dialog()
            time.sleep(0.7)

    raise RuntimeError(
        "Документ не загрузился или дизайн "
        "не удалось выделить за 60 секунд."
    ) from last_error


def wait_for_enabled_controls(
    window,
    timeout: float = 8.0,
):
    deadline = time.time() + timeout
    last_error: Exception | None = None

    while time.time() < deadline:
        try:
            return get_position_controls(
                window,
                require_enabled=True,
            )
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
    time.sleep(0.2)

    # Wilcom отображает значение, хотя GetWindowText
    # для этого внутреннего Edit возвращает пустоту.
    win32gui.SendMessage(
        hwnd,
        win32con.WM_SETTEXT,
        0,
        value,
    )

    time.sleep(0.3)

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

    time.sleep(1.0)


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

    print()
    print("Открываю файл через Windows:")
    print(file_path)

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

    time.sleep(3.0)

    raise_for_known_open_error_dialog()

    print()
    print("Использую окно Wilcom:")
    print("HWND:", hwnd)
    print(
        "TITLE:",
        repr(win32gui.GetWindowText(hwnd)),
    )

    # После загрузки создаём свежую обёртку окна.
    window = Desktop(
        backend="uia"
    ).window(
        handle=hwnd
    )

    focus_window(hwnd)
    raise_for_known_open_error_dialog()

    try:
        window.set_focus()
    except Exception:
        raise_for_known_open_error_dialog()
        raise

    print()
    print("Жду загрузки и выделяю дизайн...")

    x_pane, x_edit, y_pane, y_edit = (
        wait_for_selected_design(
            window,
            hwnd,
            timeout=60.0,
        )
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
    ) = wait_for_enabled_controls(window)

    set_value(
        y_edit,
        y,
    )

    (
        x_pane,
        x_edit,
        y_pane,
        y_edit,
    ) = wait_for_enabled_controls(window)

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

    print()
    print("Сохраняю...")

    focus_window(hwnd)
    window.set_focus()

    window.type_keys(
        "^s",
        set_foreground=True,
    )

    time.sleep(4.0)

    print("Файл сохранён.")

    if close:
        focus_window(hwnd)
        window.set_focus()

        window.type_keys(
            "^{F4}",
            set_foreground=True,
        )

        time.sleep(2.0)

        print("Документ закрыт.")

    return {
        "file": str(file_path),
        "old_x": old_x,
        "old_y": old_y,
        "new_x": new_x,
        "new_y": new_y,
        "status": "success",
    }


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
