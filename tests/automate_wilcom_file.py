import argparse
import subprocess
import time
import os
import win32con
from pathlib import Path

import psutil
import win32gui
import win32process
from pywinauto import Desktop, mouse


X_AUTOMATION_ID = "6586"
Y_AUTOMATION_ID = "6587"

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


def list_es_main_windows() -> list[
    tuple[int, int, int, str]
]:
    """
    Возвращает все крупные видимые окна ES.EXE:

    area, hwnd, pid, title
    """

    results: list[
        tuple[int, int, int, str]
    ] = []

    def callback(hwnd: int, _) -> None:
        if not win32gui.IsWindowVisible(hwnd):
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

        if width < 300 or height < 300:
            return

        results.append(
            (
                width * height,
                hwnd,
                pid,
                win32gui.GetWindowText(hwnd),
            )
        )

    win32gui.EnumWindows(
        callback,
        None,
    )

    results.sort(reverse=True)

    return results


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
        windows = list_es_main_windows()

        if windows:
            _, hwnd, pid, title = windows[0]

            print()
            print("Найдено окно Wilcom:")
            print("HWND:", hwnd)
            print("PID:", pid)
            print("TITLE:", repr(title))

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



def wait_for_open_dialog(
    main_hwnd: int,
    timeout: float = 15.0,
) -> int:
    deadline = time.time() + timeout

    _, main_pid = (
        win32process.GetWindowThreadProcessId(
            main_hwnd
        )
    )

    while time.time() < deadline:
        matches: list[tuple[int, int]] = []

        def callback(hwnd: int, _) -> None:
            if not win32gui.IsWindowVisible(hwnd):
                return

            try:
                class_name = win32gui.GetClassName(hwnd)
            except Exception:
                return

            if class_name != "#32770":
                return

            _, pid = (
                win32process.GetWindowThreadProcessId(
                    hwnd
                )
            )

            owner = win32gui.GetWindow(
                hwnd,
                win32gui.GW_OWNER,
            )

            if pid != main_pid and owner != main_hwnd:
                return

            left, top, right, bottom = (
                win32gui.GetWindowRect(hwnd)
            )

            width = right - left
            height = bottom - top

            if width < 300 or height < 200:
                return

            matches.append(
                (
                    width * height,
                    hwnd,
                )
            )

        win32gui.EnumWindows(
            callback,
            None,
        )

        if matches:
            matches.sort(reverse=True)
            return matches[0][1]

        time.sleep(0.2)

    raise TimeoutError(
        "Диалог открытия файла не появился."
    )


def open_file_via_dialog(
    main_hwnd: int,
    file_path: Path,
) -> None:
    print()
    print("Открываю файл через Ctrl+O...")

    focus_window(main_hwnd)

    main_window = Desktop(
        backend="uia"
    ).window(
        handle=main_hwnd
    )

    main_window.set_focus()

    main_window.type_keys(
        "^o",
        set_foreground=True,
    )

    dialog_hwnd = wait_for_open_dialog(
        main_hwnd,
        timeout=15.0,
    )

    dialog = Desktop(
        backend="win32"
    ).window(
        handle=dialog_hwnd
    )

    dialog.set_focus()

    time.sleep(0.5)

    edits = []

    for control in dialog.descendants(
        class_name="Edit"
    ):
        try:
            if (
                control.is_visible()
                and control.is_enabled()
            ):
                rectangle = control.rectangle()

                edits.append(
                    (
                        rectangle.top,
                        rectangle.width(),
                        control,
                    )
                )
        except Exception:
            continue

    if not edits:
        raise RuntimeError(
            "В диалоге открытия не найдено "
            "поле имени файла."
        )

    # Поле имени файла обычно находится ниже
    # остальных полей диалога.
    edits.sort(
        key=lambda item: (
            item[0],
            item[1],
        ),
        reverse=True,
    )

    file_edit = edits[0][2]

    file_edit.set_edit_text(
        str(file_path)
    )

    time.sleep(0.4)

    open_button = None

    for button in dialog.descendants(
        class_name="Button"
    ):
        try:
            text = (
                button.window_text()
                .replace("&", "")
                .strip()
                .lower()
            )
        except Exception:
            continue

        if (
            text == "open"
            or text.startswith("открыть")
        ):
            open_button = button
            break

    if open_button is not None:
        open_button.click()
    else:
        file_edit.type_keys(
            "{ENTER}",
            set_foreground=False,
        )

    deadline = time.time() + 20.0

    while time.time() < deadline:
        if (
            not win32gui.IsWindow(dialog_hwnd)
            or not win32gui.IsWindowVisible(
                dialog_hwnd
            )
        ):
            print("Диалог закрыт, файл загружается.")
            return

        time.sleep(0.25)

    raise TimeoutError(
        "Диалог открытия не закрылся."
    )


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

    file_path = args.file.resolve()

    if not file_path.exists():
        raise FileNotFoundError(
            f"Файл не найден: {file_path}"
        )

    es_exe = find_es_exe(
        args.es
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

    # Wilcom может открыть файл в уже запущенном
    # процессе или запустить новый процесс.
    hwnd = wait_for_es_main_window(
        timeout=60.0,
    )

    time.sleep(3.0)

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
    window.set_focus()

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
        args.x,
    )

    (
        x_pane,
        x_edit,
        y_pane,
        y_edit,
    ) = wait_for_enabled_controls(window)

    set_value(
        y_edit,
        args.y,
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
        args.x,
    )

    verify_value(
        "Y",
        new_y,
        args.y,
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

    if args.close:
        focus_window(hwnd)
        window.set_focus()

        window.type_keys(
            "^{F4}",
            set_foreground=True,
        )

        time.sleep(2.0)

        print("Документ закрыт.")


if __name__ == "__main__":
    main()