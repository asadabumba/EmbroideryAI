from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
import uuid
from pathlib import Path

import win32con
import win32gui
from pywinauto import Desktop


TESTS_DIR = Path(__file__).resolve().parent

if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from automate_wilcom_batch import (
    CoordinateRow,
    PreparedTask,
    preflight_batch,
    read_coordinate_csv,
    resolve_source_path,
)
from automate_wilcom_file import (
    cancel_save_as_best_effort,
    close_document_best_effort,
    dismiss_save_changes_dialog,
    find_es_exe,
    find_document_canvas,
    find_save_as_dialog,
    find_save_changes_dialog,
    focus_window,
    invoke_uia_file_menu_item,
    raise_for_known_open_error_dialog,
    save_document_as,
    send_ctrl_virtual_key,
    set_document_position,
    wait_for_document_open,
    wait_for_es_main_window,
)


CLOSE_MENU_TEXTS = {
    "закрыть",
    "close",
    "schließen",
}

TIMING_LABELS = {
    "create_working_copy": "создание working copy",
    "open_emb": "открытие EMB",
    "wait_wilcom_window": "ожидание окна Wilcom",
    "total_opening": "всего открытие",
    "set_document_position": "set_document_position",
    "open_save_as_dialog": "open_save_as_dialog",
    "open_save_as_cached_win32_command": (
        "cached Win32 command"
    ),
    "open_save_as_scan_win32_menu": "scan Win32 menu",
    "open_save_as_send_wm_command": "send WM_COMMAND",
    "open_save_as_wait_dialog_win32": (
        "wait dialog Win32"
    ),
    "open_save_as_uia_fast_path": "UIA fast path",
    "open_save_as_legacy_fallback": "legacy fallback",
    "open_save_as_fresh_main_wrapper": "fresh main wrapper",
    "open_save_as_find_file_menu": "find File menu",
    "open_save_as_invoke_file_menu": "invoke File menu",
    "open_save_as_enumerate_popup_menus": (
        "enumerate popup menus"
    ),
    "open_save_as_inspect_popup_items": (
        "inspect popup items"
    ),
    "open_save_as_find_popup_menu": "find popup menu",
    "open_save_as_find_save_as_item": "find Save As item",
    "open_save_as_invoke_save_as": "invoke Save As",
    "open_save_as_wait_dialog": "wait dialog",
    "open_save_as_legacy_collect_initial": (
        "legacy: collect initial controls"
    ),
    "open_save_as_legacy_find_initial": (
        "legacy: find target initially"
    ),
    "open_save_as_legacy_find_file": (
        "legacy: find File"
    ),
    "open_save_as_legacy_invoke_file": (
        "legacy: invoke File"
    ),
    "open_save_as_legacy_collect_after_file": (
        "legacy: collect after File"
    ),
    "open_save_as_legacy_find_after_file": (
        "legacy: find target after File"
    ),
    "open_save_as_legacy_invoke_target": (
        "legacy: invoke Save As"
    ),
    "open_save_as_legacy_wait_dialog": (
        "legacy: wait dialog"
    ),
    "open_save_as_total": "total",
    "set_save_as_path": "set_save_as_path",
    "click_save": "click_save",
    "wait_save_dialog_closed": (
        "wait_save_dialog_closed (от click_save)"
    ),
    "wait_new_title": "wait_new_title (от click_save)",
    "wait_output_file": "wait_output_file (от click_save)",
    "wait_stable_size": (
        "wait_stable_size (после появления файла)"
    ),
    "total_variant": "всего вариант",
    "fresh_wrapper": "получение свежего wrapper",
    "active_stem": "определение active stem",
    "send_ctrl_f4": "фокус и отправка Ctrl+F4",
    "wait_document_closed": "ожидание закрытия документа",
    "save_changes_dialog": "обработка save-changes dialog",
    "uia_close_fallback": "UIA Close fallback",
    "remove_working_copy": "удаление working copy",
    "total_completion": "всего завершение",
}

OPEN_SAVE_AS_DETAIL_TIMINGS = (
    "open_save_as_cached_win32_command",
    "open_save_as_scan_win32_menu",
    "open_save_as_send_wm_command",
    "open_save_as_wait_dialog_win32",
    "open_save_as_uia_fast_path",
    "open_save_as_legacy_fallback",
    "open_save_as_fresh_main_wrapper",
    "open_save_as_find_file_menu",
    "open_save_as_invoke_file_menu",
    "open_save_as_enumerate_popup_menus",
    "open_save_as_inspect_popup_items",
    "open_save_as_find_popup_menu",
    "open_save_as_find_save_as_item",
    "open_save_as_invoke_save_as",
    "open_save_as_wait_dialog",
    "open_save_as_legacy_collect_initial",
    "open_save_as_legacy_find_initial",
    "open_save_as_legacy_find_file",
    "open_save_as_legacy_invoke_file",
    "open_save_as_legacy_collect_after_file",
    "open_save_as_legacy_find_after_file",
    "open_save_as_legacy_invoke_target",
    "open_save_as_legacy_wait_dialog",
    "open_save_as_total",
)


def start_timing(enabled: bool) -> float | None:
    if not enabled:
        return None

    return time.perf_counter()


def finish_timing(
    timings: dict[str, float],
    key: str,
    started_at: float | None,
) -> float:
    if started_at is None:
        return 0.0

    duration = time.perf_counter() - started_at
    timings[key] = duration
    return duration


def print_timing_line(
    key: str,
    duration: float,
) -> None:
    label = TIMING_LABELS[key]
    print(f"- {label}: {duration:.3f} сек")


def print_timing_section(
    title: str,
    timings: dict[str, float],
    keys: tuple[str, ...],
) -> None:
    print()
    print(f"{title}:")

    for key in keys:
        print_timing_line(
            key,
            timings.get(key, 0.0),
        )

        if key == "open_save_as_dialog":
            for detail_key in (
                OPEN_SAVE_AS_DETAIL_TIMINGS
            ):
                label = TIMING_LABELS[
                    detail_key
                ]
                duration = timings.get(
                    detail_key,
                    0.0,
                )
                print(
                    f"  - {label}: "
                    f"{duration:.3f} сек"
                )


def comparable_source_path(
    input_dir: Path,
    file_value: str,
) -> Path | None:
    input_root = input_dir.resolve()
    file_value = file_value.strip()

    if not file_value:
        return None

    relative_path = Path(file_value)

    if relative_path.is_absolute() or relative_path.drive:
        return None

    candidate = (
        input_root
        / relative_path
    ).resolve()

    if not candidate.is_relative_to(input_root):
        return None

    return candidate


def select_source_rows(
    rows: list[CoordinateRow],
    input_dir: Path,
    source: str,
    limit: int | None = None,
) -> list[CoordinateRow]:
    """Выбирает варианты одного source в исходном порядке."""

    if limit is not None and limit <= 0:
        raise ValueError(
            "--limit должен быть больше нуля."
        )

    source_path = resolve_source_path(
        input_dir,
        source,
    )
    source_key = os.path.normcase(
        str(source_path)
    )
    selected = [
        row
        for row in rows
        if (
            (
                row_path := comparable_source_path(
                    input_dir,
                    row.file,
                )
            )
            is not None
            and os.path.normcase(
                str(row_path)
            )
            == source_key
        )
    ]

    if limit is not None:
        selected = selected[:limit]

    if not selected:
        raise ValueError(
            "В CSV нет строк для source: "
            f"{source}"
        )

    missing_output_rows = [
        row.row
        for row in selected
        if not row.output_file.strip()
    ]

    if missing_output_rows:
        rows_text = ", ".join(
            str(row_number)
            for row_number in missing_output_rows
        )
        raise ValueError(
            "Для grouped-обработки обязателен "
            "столбец output_file. "
            f"Пустое значение в строках: {rows_text}."
        )

    return selected


def prepare_group_tasks(
    csv_path: Path,
    input_dir: Path,
    output_dir: Path,
    source: str,
    limit: int | None = None,
) -> tuple[Path, list[PreparedTask]]:
    source_path = resolve_source_path(
        input_dir,
        source,
    )
    rows = read_coordinate_csv(
        csv_path
    )
    selected_rows = select_source_rows(
        rows,
        input_dir,
        source,
        limit=limit,
    )
    tasks = preflight_batch(
        selected_rows,
        input_dir,
        output_dir,
    )

    return source_path, tasks


def create_group_working_copy(
    source_path: Path,
    output_dir: Path,
) -> Path:
    """Создаёт единственную рабочую EMB-копию группы."""

    working_dir = (
        output_dir.resolve()
        / ".working"
    )
    working_dir.mkdir(
        parents=True,
        exist_ok=True,
    )
    working_path = (
        working_dir
        / (
            f"{source_path.stem}"
            f"__groupwork_{uuid.uuid4().hex}.EMB"
        )
    )
    shutil.copy2(
        source_path,
        working_path,
    )

    return working_path


def remove_group_working_copy(
    working_path: Path,
) -> None:
    """Удаляет рабочую копию без ожиданий и повторов."""

    try:
        working_path.unlink()
    except FileNotFoundError:
        pass
    except OSError as error:
        print(
            "Не удалось удалить working copy: "
            f"{error}"
        )


def open_working_document(
    working_path: Path,
    es_path: Path | None = None,
    timings: dict[str, float] | None = None,
) -> int:
    es_exe = find_es_exe(es_path)
    print("Wilcom:")
    print(es_exe)
    print()
    print("Открываю рабочую копию:")
    print(working_path)

    open_started = start_timing(
        timings is not None
    )

    try:
        os.startfile(
            str(working_path)
        )
    finally:
        if timings is not None:
            finish_timing(
                timings,
                "open_emb",
                open_started,
            )

    wait_started = start_timing(
        timings is not None
    )

    try:
        raise_for_known_open_error_dialog()
        main_hwnd = wait_for_es_main_window(
            timeout=60.0,
        )
        raise_for_known_open_error_dialog()
        wait_for_document_open(
            main_hwnd,
            working_path,
            timeout=60.0,
        )
        time.sleep(0.75)
        raise_for_known_open_error_dialog()
    finally:
        if timings is not None:
            finish_timing(
                timings,
                "wait_wilcom_window",
                wait_started,
            )

    return main_hwnd


def create_fresh_main_window(
    main_hwnd: int,
):
    return Desktop(
        backend="uia"
    ).window(
        handle=main_hwnd
    )


def extract_active_document_stem(
    title: str,
) -> str | None:
    """Возвращает имя активного документа из последней пары [...]."""

    closing_bracket = title.rfind("]")

    if closing_bracket < 0:
        return None

    opening_bracket = title.rfind(
        "[",
        0,
        closing_bracket,
    )

    if opening_bracket < 0:
        return None

    stem = title[
        opening_bracket + 1 : closing_bracket
    ].strip().rstrip("*").rstrip()

    return stem or None


def normalize_document_stem(
    stem: str,
) -> str:
    normalized = stem.strip().rstrip("*").rstrip()

    if normalized.casefold().endswith(".emb"):
        normalized = normalized[:-4]

    return normalized.casefold()


def title_shows_document(
    title: str,
    document_stem: str,
) -> bool:
    active_stem = extract_active_document_stem(
        title
    )

    if active_stem is None:
        return False

    return normalize_document_stem(
        document_stem
    ) == normalize_document_stem(
        active_stem
    )


def wait_after_group_close(
    main_hwnd: int,
    document_stem: str,
    timeout: float,
    emergency: bool,
    timings: dict[str, float] | None = None,
) -> str:
    """Быстро ждёт исчезновения именно активного документа."""

    del emergency
    deadline = time.monotonic() + timeout
    last_title = ""

    while True:
        try:
            if not win32gui.IsWindow(main_hwnd):
                return last_title
        except Exception:
            return last_title

        title_was_read = False

        try:
            last_title = win32gui.GetWindowText(
                main_hwnd
            )
            title_was_read = True
        except Exception:
            pass

        remaining = deadline - time.monotonic()

        save_dialog = find_save_changes_dialog(
            document_stem
        )

        if (
            save_dialog is None
            and title_was_read
            and not title_shows_document(
                last_title,
                document_stem,
            )
        ):
            return last_title

        if remaining <= 0 and save_dialog is None:
            break

        if save_dialog is not None:
            dialog_started = start_timing(
                timings is not None
            )
            dismissed = dismiss_save_changes_dialog(
                document_stem,
                save=False,
                timeout=min(
                    2.0,
                    max(0.05, remaining),
                ),
            )

            if timings is not None:
                duration = finish_timing(
                    {},
                    "save_changes_dialog",
                    dialog_started,
                )
                timings["save_changes_dialog"] = (
                    timings.get(
                        "save_changes_dialog",
                        0.0,
                    )
                    + duration
                )

            if not dismissed:
                raise RuntimeError(
                    "Не удалось закрыть диалог "
                    "«Сохранить изменения» без сохранения."
                )

            if remaining <= 0:
                break

            continue

        time.sleep(
            min(0.1, remaining)
        )

    raise TimeoutError(
        "Wilcom не закрыл активный документ "
        f"за {timeout:g} секунд.\n"
        f"Документ: {document_stem}\n"
        "Фактический заголовок: "
        f"{last_title or '<пустой заголовок>'}"
    )


def close_group_document(
    main_hwnd: int,
    document_stem: str,
    emergency: bool = False,
    timings: dict[str, float] | None = None,
) -> str:
    """Закрывает текущий документ с быстрым Win32 success-path."""

    stage_timings = (
        timings
        if timings is not None
        else {}
    )

    if not safe_window_exists(main_hwnd):
        return ""

    wrapper_started = start_timing(
        timings is not None
    )
    window = create_fresh_main_window(
        main_hwnd
    )

    if timings is not None:
        wrapper_duration = finish_timing(
            stage_timings,
            "fresh_wrapper",
            wrapper_started,
        )
        print_timing_line(
            "fresh_wrapper",
            wrapper_duration,
        )

    stem_started = start_timing(
        timings is not None
    )

    try:
        current_title = win32gui.GetWindowText(
            main_hwnd
        )
        active_stem = extract_active_document_stem(
            current_title
        )
    except Exception as error:
        raise RuntimeError(
            "Не удалось прочитать актуальный заголовок "
            "главного окна Wilcom перед Ctrl+F4."
        ) from error

    if timings is not None:
        stem_duration = finish_timing(
            stage_timings,
            "active_stem",
            stem_started,
        )
        print_timing_line(
            "active_stem",
            stem_duration,
        )
        print("Активный документ перед закрытием:")
        print(current_title or "<пустой заголовок>")
        print("Ожидаемый stem:")
        print(active_stem or "<документ уже закрыт>")

    if active_stem is None:
        for key in (
            "send_ctrl_f4",
            "wait_document_closed",
            "save_changes_dialog",
            "uia_close_fallback",
        ):
            stage_timings.setdefault(
                key,
                0.0,
            )

            if timings is not None:
                print_timing_line(
                    key,
                    0.0,
                )

        return current_title

    ctrl_f4_started = start_timing(
        timings is not None
    )
    focus_window(main_hwnd)

    try:
        window.set_focus()
    except Exception:
        pass

    canvas = find_document_canvas(main_hwnd)

    if canvas is not None:
        canvas_hwnd, _, _ = canvas

        try:
            Desktop(
                backend="win32"
            ).window(
                handle=canvas_hwnd
            ).wrapper_object().click_input()
            time.sleep(0.05)
        except Exception:
            pass

    send_ctrl_virtual_key(
        win32con.VK_F4
    )

    if timings is not None:
        ctrl_f4_duration = finish_timing(
            stage_timings,
            "send_ctrl_f4",
            ctrl_f4_started,
        )
        print_timing_line(
            "send_ctrl_f4",
            ctrl_f4_duration,
        )

    wait_started = start_timing(
        timings is not None
    )

    try:
        closed_title = wait_after_group_close(
            main_hwnd,
            active_stem,
            timeout=5.0,
            emergency=emergency,
            timings=timings,
        )
    except TimeoutError:
        if timings is not None:
            wait_duration = finish_timing(
                stage_timings,
                "wait_document_closed",
                wait_started,
            )
            print(
                "- ожидание закрытия документа "
                "до UIA fallback: "
                f"{wait_duration:.3f} сек"
            )

        if find_save_changes_dialog(
            active_stem
        ) is not None:
            raise RuntimeError(
                "После Ctrl+F4 остался открытым диалог "
                "«Сохранить изменения»."
            )

        if group_document_is_closed(
            main_hwnd,
            active_stem,
        ):
            if timings is not None:
                print_timing_line(
                    "save_changes_dialog",
                    stage_timings.get(
                        "save_changes_dialog",
                        0.0,
                    ),
                )
                print_timing_line(
                    "uia_close_fallback",
                    0.0,
                )

            return win32gui.GetWindowText(
                main_hwnd
            )

        fallback_started = start_timing(
            timings is not None
        )

        fallback_invoked = False

        try:
            fallback_invoked = invoke_uia_file_menu_item(
                main_hwnd,
                CLOSE_MENU_TEXTS,
            )
        finally:
            if timings is not None:
                fallback_duration = finish_timing(
                    stage_timings,
                    "uia_close_fallback",
                    fallback_started,
                )
                print_timing_line(
                    "uia_close_fallback",
                    fallback_duration,
                )

        if not fallback_invoked:
            raise RuntimeError(
                "Не удалось вызвать File → Close "
                "через UIA."
            )

        fallback_wait_started = start_timing(
            timings is not None
        )
        closed_title = wait_after_group_close(
            main_hwnd,
            active_stem,
            timeout=2.0,
            emergency=emergency,
            timings=timings,
        )

        if timings is not None:
            fallback_wait_duration = finish_timing(
                {},
                "wait_document_closed",
                fallback_wait_started,
            )
            stage_timings[
                "wait_document_closed"
            ] = (
                stage_timings.get(
                    "wait_document_closed",
                    0.0,
                )
                + fallback_wait_duration
            )
            print_timing_line(
                "wait_document_closed",
                stage_timings[
                    "wait_document_closed"
                ],
            )
    else:
        if timings is not None:
            wait_duration = finish_timing(
                stage_timings,
                "wait_document_closed",
                wait_started,
            )
            print_timing_line(
                "wait_document_closed",
                wait_duration,
            )
            stage_timings.setdefault(
                "uia_close_fallback",
                0.0,
            )

    if timings is not None:
        print_timing_line(
            "save_changes_dialog",
            stage_timings.get(
                "save_changes_dialog",
                0.0,
            ),
        )

        if not stage_timings.get(
            "uia_close_fallback"
        ):
            print_timing_line(
                "uia_close_fallback",
                0.0,
            )

    return closed_title


def cleanup_group_document_best_effort(
    main_hwnd: int,
    document_stem: str,
) -> None:
    try:
        dialog_hwnd = find_save_as_dialog(
            main_hwnd
        )
        cancel_save_as_best_effort(
            dialog_hwnd,
            timeout=3.0,
        )

        if (
            dialog_hwnd
            and safe_window_exists(
                dialog_hwnd
            )
        ):
            return

        window = create_fresh_main_window(
            main_hwnd,
        )
        close_document_best_effort(
            main_hwnd,
            document_stem,
            window=window,
            timeout=8.0,
        )

        if find_save_changes_dialog(
            document_stem,
        ) is not None:
            dismiss_save_changes_dialog(
                document_stem,
                save=False,
                timeout=3.0,
            )

        if group_document_is_closed(
            main_hwnd,
            document_stem,
        ):
            print(
                "Документ закрыт без сохранения."
            )
    except Exception:
        pass


def safe_window_exists(hwnd: int) -> bool:
    try:
        return bool(
            win32gui.IsWindow(hwnd)
        )
    except Exception:
        return False


def group_document_is_closed(
    main_hwnd: int,
    document_stem: str,
) -> bool:
    try:
        if not win32gui.IsWindow(main_hwnd):
            return True
    except Exception:
        return False

    try:
        title = win32gui.GetWindowText(
            main_hwnd
        )
    except Exception:
        return False

    return not title_shows_document(
        title,
        document_stem,
    )


def choose_active_group_stem(
    main_hwnd: int,
    possible_stems: list[str],
    fallback: str,
) -> str:
    try:
        title = win32gui.GetWindowText(
            main_hwnd
        )
    except Exception:
        return fallback

    active_stem = extract_active_document_stem(
        title
    )

    if active_stem is None:
        return fallback

    normalized_active_stem = normalize_document_stem(
        active_stem
    )

    for stem in reversed(possible_stems):
        if (
            normalize_document_stem(stem)
            == normalized_active_stem
        ):
            return stem

    return fallback


def run_grouped_file(
    csv_path: Path,
    input_dir: Path,
    output_dir: Path,
    source: str,
    limit: int | None = None,
    es_path: Path | None = None,
    timings: bool = False,
) -> int:
    """Создаёт несколько вариантов из одного открытого EMB."""

    started_at = time.monotonic()
    opening_timings: dict[str, float] = {}
    source_path, tasks = prepare_group_tasks(
        csv_path,
        input_dir,
        output_dir,
        source,
        limit=limit,
    )
    opening_started = start_timing(timings)
    copy_started = start_timing(timings)

    try:
        working_path = create_group_working_copy(
            source_path,
            output_dir,
        )
    finally:
        if timings:
            finish_timing(
                opening_timings,
                "create_working_copy",
                copy_started,
            )

    main_hwnd: int | None = None
    current_stem = working_path.stem
    possible_stems = [
        current_stem,
    ]
    document_opened = False
    opened_count = 0
    created_count = 0
    error_count = 0
    completion_started: float | None = None
    completion_timings: dict[str, float] = {}

    try:
        if timings:
            main_hwnd = open_working_document(
                working_path,
                es_path=es_path,
                timings=opening_timings,
            )
        else:
            main_hwnd = open_working_document(
                working_path,
                es_path=es_path,
            )

        document_opened = True
        opened_count = 1

        if timings:
            finish_timing(
                opening_timings,
                "total_opening",
                opening_started,
            )
            print_timing_section(
                "Открытие группы",
                opening_timings,
                (
                    "create_working_copy",
                    "open_emb",
                    "wait_wilcom_window",
                    "total_opening",
                ),
            )

        total = len(tasks)

        for index, task in enumerate(
            tasks,
            start=1,
        ):
            row = task.coordinate_row
            print()
            print(
                f"[{index}/{total}] "
                f"X={task.requested_x} "
                f"Y={task.requested_y}"
            )
            print(
                "  Save As:",
                task.output_path,
            )

            variant_timings: dict[str, float] = {}
            variant_started = start_timing(
                timings
            )

            try:
                window = create_fresh_main_window(
                    main_hwnd
                )
                position_started = start_timing(
                    timings
                )

                try:
                    set_document_position(
                        window,
                        main_hwnd,
                        task.requested_x,
                        task.requested_y,
                    )
                finally:
                    if timings:
                        finish_timing(
                            variant_timings,
                            "set_document_position",
                            position_started,
                        )

                possible_stems.append(
                    task.output_path.stem
                )

                if timings:
                    save_document_as(
                        main_hwnd,
                        task.output_path,
                        timings=variant_timings,
                    )
                else:
                    save_document_as(
                        main_hwnd,
                        task.output_path,
                    )

                current_stem = (
                    task.output_path.stem
                )
                created_count += 1
                print("  OK")

                if timings:
                    finish_timing(
                        variant_timings,
                        "total_variant",
                        variant_started,
                    )
                    print_timing_section(
                        "Длительность варианта",
                        variant_timings,
                        (
                            "set_document_position",
                            "open_save_as_dialog",
                            "set_save_as_path",
                            "click_save",
                            "wait_save_dialog_closed",
                            "wait_new_title",
                            "wait_output_file",
                            "wait_stable_size",
                            "total_variant",
                        ),
                    )
            except BaseException as error:
                error_count = 1
                print(
                    f"  ERROR в строке {row.row}: "
                    f"{error}"
                )
                raise

        completion_started = start_timing(
            timings
        )

        if timings:
            print()
            print("Завершение группы:")
            close_group_document(
                main_hwnd,
                current_stem,
                emergency=False,
                timings=completion_timings,
            )
        else:
            close_group_document(
                main_hwnd,
                current_stem,
                emergency=False,
            )

        document_opened = False

        return created_count

    except BaseException:
        error_count = max(
            1,
            error_count,
        )
        raise

    finally:
        if (
            document_opened
            and main_hwnd is not None
        ):
            cleanup_stem = (
                choose_active_group_stem(
                    main_hwnd,
                    possible_stems,
                    current_stem,
                )
            )
            try:
                cleanup_group_document_best_effort(
                    main_hwnd,
                    cleanup_stem,
                )
            except Exception:
                pass

        remove_started = start_timing(
            timings
        )
        remove_group_working_copy(
            working_path
        )

        if timings:
            remove_duration = finish_timing(
                completion_timings,
                "remove_working_copy",
                remove_started,
            )

            if completion_started is not None:
                print_timing_line(
                    "remove_working_copy",
                    remove_duration,
                )
                total_completion = finish_timing(
                    completion_timings,
                    "total_completion",
                    completion_started,
                )
                print_timing_line(
                    "total_completion",
                    total_completion,
                )

        elapsed = time.monotonic() - started_at
        print()
        print(
            "Исходный EMB открыт:",
            opened_count,
            "раз",
        )
        print(
            "Создано вариантов:",
            created_count,
        )
        print("Ошибок:", error_count)
        print(
            "Время:",
            f"{elapsed:.2f}",
            "секунд",
        )


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--csv",
        type=Path,
        required=True,
        help="CSV с вариантами координат",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        required=True,
        help="Корневая папка исходных EMB",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Папка вариантов и рабочей копии",
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Один относительный source из CSV",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Необязательное число первых вариантов",
    )
    parser.add_argument(
        "--es",
        type=Path,
        help="Необязательный путь к ES.EXE",
    )
    parser.add_argument(
        "--timings",
        action="store_true",
        help="Печатать длительность этапов через perf_counter",
    )

    return parser


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    try:
        run_grouped_file(
            csv_path=args.csv,
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            source=args.source,
            limit=args.limit,
            es_path=args.es,
            timings=args.timings,
        )
    except KeyboardInterrupt as error:
        print(
            "Обработка прервана пользователем.",
            file=sys.stderr,
        )
        raise SystemExit(130) from error
    except Exception as error:
        print(
            f"ERROR: {error}",
            file=sys.stderr,
        )
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
