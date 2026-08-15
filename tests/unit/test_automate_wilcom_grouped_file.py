from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "automate_wilcom_grouped_file.py"
)
SPEC = importlib.util.spec_from_file_location(
    "automate_wilcom_grouped_file_tests",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
grouped = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = grouped
SPEC.loader.exec_module(grouped)


def make_task(
    row_number: int,
    source_path: Path,
    output_path: Path,
    x: str,
    y: str,
) -> grouped.PreparedTask:
    row = grouped.CoordinateRow(
        row=row_number,
        file="debug/Ghost_debug.EMB",
        x=x,
        y=y,
        output_file=output_path.name,
    )

    return grouped.PreparedTask(
        coordinate_row=row,
        source_path=source_path,
        output_path=output_path,
        relative_source_file=row.file,
        relative_output_file=output_path.name,
        requested_x=x,
        requested_y=y,
        task_key=(
            row.file,
            x,
            y,
            output_path.name,
        ),
    )


def test_select_source_rows_filters_and_preserves_order(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "dataset"
    source_path = (
        input_dir
        / "debug"
        / "Ghost_debug.EMB"
    )
    source_path.parent.mkdir(
        parents=True
    )
    source_path.write_bytes(b"source")
    rows = [
        grouped.CoordinateRow(
            1,
            "other.EMB",
            "0",
            "0",
            "other.EMB",
        ),
        grouped.CoordinateRow(
            2,
            "debug/Ghost_debug.EMB",
            "1",
            "2",
            "one.EMB",
        ),
        grouped.CoordinateRow(
            3,
            r"debug\Ghost_debug.EMB",
            "3",
            "4",
            "two.EMB",
        ),
    ]

    selected = grouped.select_source_rows(
        rows,
        input_dir,
        "debug/Ghost_debug.EMB",
    )

    assert [
        row.row
        for row in selected
    ] == [
        2,
        3,
    ]


def test_select_source_rows_applies_limit(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "dataset"
    source_path = input_dir / "Ghost.EMB"
    input_dir.mkdir()
    source_path.write_bytes(b"source")
    rows = [
        grouped.CoordinateRow(
            number,
            "Ghost.EMB",
            str(number),
            "0",
            f"variant_{number}.EMB",
        )
        for number in range(1, 5)
    ]

    selected = grouped.select_source_rows(
        rows,
        input_dir,
        "Ghost.EMB",
        limit=2,
    )

    assert [
        row.row
        for row in selected
    ] == [
        1,
        2,
    ]


def test_select_source_rows_requires_output_file(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "dataset"
    input_dir.mkdir()
    (input_dir / "Ghost.EMB").write_bytes(
        b"source"
    )

    with pytest.raises(
        ValueError,
        match="output_file",
    ):
        grouped.select_source_rows(
            [
                grouped.CoordinateRow(
                    7,
                    "Ghost.EMB",
                    "0",
                    "0",
                )
            ],
            input_dir,
            "Ghost.EMB",
        )


def test_working_copy_preserves_source(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "Ghost.EMB"
    output_dir = tmp_path / "output"
    source_path.write_bytes(b"original")

    working_path = (
        grouped.create_group_working_copy(
            source_path,
            output_dir,
        )
    )
    working_path.write_bytes(b"changed")

    assert source_path.read_bytes() == b"original"
    assert working_path.suffix == ".EMB"
    assert working_path.parent == (
        output_dir.resolve()
        / ".working"
    )


def test_run_opens_once_saves_each_variant_and_removes_working(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "Ghost.EMB"
    output_dir = tmp_path / "output"
    source_path.write_bytes(b"original")
    tasks = [
        make_task(
            number,
            source_path,
            output_dir / f"variant_{number}.EMB",
            str(number),
            str(-number),
        )
        for number in range(1, 4)
    ]
    events: list[object] = []
    wrappers: list[object] = []
    original_remove_working_copy = (
        grouped.remove_group_working_copy
    )

    def fresh_window(hwnd: int):
        wrapper = object()
        wrappers.append(wrapper)
        events.append(
            (
                "wrapper",
                hwnd,
                wrapper,
            )
        )
        return wrapper

    monkeypatch.setattr(
        grouped,
        "prepare_group_tasks",
        lambda *_args, **_kwargs: (
            source_path,
            tasks,
        ),
    )
    monkeypatch.setattr(
        grouped,
        "open_working_document",
        lambda path, es_path=None: (
            events.append(
                (
                    "open",
                    path,
                    es_path,
                )
            )
            or 123
        ),
    )
    monkeypatch.setattr(
        grouped,
        "create_fresh_main_window",
        fresh_window,
    )
    monkeypatch.setattr(
        grouped,
        "set_document_position",
        lambda window, hwnd, x, y: (
            events.append(
                (
                    "position",
                    window,
                    hwnd,
                    x,
                    y,
                )
            )
            or {}
        ),
    )
    monkeypatch.setattr(
        grouped,
        "save_document_as",
        lambda hwnd, path: events.append(
            (
                "save_as",
                hwnd,
                path,
            )
        ),
    )
    monkeypatch.setattr(
        grouped,
        "close_group_document",
        lambda hwnd, stem, emergency=False: (
            events.append(
                (
                    "close",
                    hwnd,
                    stem,
                    emergency,
                )
            )
            or ""
        ),
    )
    monkeypatch.setattr(
        grouped,
        "remove_group_working_copy",
        lambda path: (
            events.append(
                (
                    "remove_working_copy",
                    path,
                )
            ),
            original_remove_working_copy(path),
        )[-1],
    )

    result = grouped.run_grouped_file(
        csv_path=tmp_path / "unused.csv",
        input_dir=tmp_path,
        output_dir=output_dir,
        source="Ghost.EMB",
    )

    assert result == 3
    assert len(
        [
            event
            for event in events
            if event[0] == "open"
        ]
    ) == 1
    assert len(
        [
            event
            for event in events
            if event[0] == "save_as"
        ]
    ) == 3
    assert len(wrappers) == 3
    close_indexes = [
        index
        for index, event in enumerate(events)
        if event[0] == "close"
    ]
    save_indexes = [
        index
        for index, event in enumerate(events)
        if event[0] == "save_as"
    ]
    assert close_indexes == [
        len(events) - 2
    ]
    assert close_indexes[0] > max(save_indexes)
    assert events[-1][0] == "remove_working_copy"
    assert source_path.read_bytes() == b"original"
    assert not list(
        (
            output_dir
            / ".working"
        ).glob("*.EMB")
    )


def test_task_filter_skips_complete_group_without_opening_wilcom(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source_path = tmp_path / "Ghost.EMB"
    output_dir = tmp_path / "output"
    source_path.write_bytes(b"source")
    task = make_task(
        1,
        source_path,
        output_dir / "variant.EMB",
        "1",
        "2",
    )
    monkeypatch.setattr(
        grouped,
        "prepare_group_tasks",
        lambda *_args, **_kwargs: (
            source_path,
            [task],
        ),
    )
    monkeypatch.setattr(
        grouped,
        "create_group_working_copy",
        lambda *_: pytest.fail(
            "Полностью готовая группа не должна открывать Wilcom"
        ),
    )

    result = grouped.run_grouped_file(
        csv_path=tmp_path / "unused.csv",
        input_dir=tmp_path,
        output_dir=output_dir,
        source="Ghost.EMB",
        task_filter=lambda _: False,
    )

    assert result == 0
    output = capsys.readouterr().out
    assert "Исходный EMB открыт: 0 раз" in output
    assert "Пропущено готовых вариантов: 1" in output


def test_atomic_publish_checkpoints_before_final_path_appears(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "Ghost.EMB"
    output_dir = tmp_path / "output"
    output_path = output_dir / "variant.EMB"
    source_path.write_bytes(b"source")
    task = make_task(
        1,
        source_path,
        output_path,
        "1",
        "2",
    )
    save_paths: list[Path] = []
    checkpoint_values: list[dict[str, str]] = []
    position_values = {
        "old_x": "0",
        "old_y": "0",
        "new_x": "1",
        "new_y": "2",
    }
    monkeypatch.setattr(
        grouped,
        "prepare_group_tasks",
        lambda *_args, **_kwargs: (
            source_path,
            [task],
        ),
    )
    monkeypatch.setattr(
        grouped,
        "open_working_document",
        lambda *_args, **_kwargs: 123,
    )
    monkeypatch.setattr(
        grouped,
        "create_fresh_main_window",
        lambda _: object(),
    )
    monkeypatch.setattr(
        grouped,
        "set_document_position",
        lambda *_: position_values,
    )

    def save_variant(_hwnd: int, path: Path) -> None:
        save_paths.append(path)
        path.write_bytes(b"ready")

    def checkpoint(
        checkpoint_task: grouped.PreparedTask,
        values: dict[str, str],
    ) -> None:
        assert checkpoint_task is task
        assert not output_path.exists()
        assert save_paths[-1].read_bytes() == b"ready"
        checkpoint_values.append(values)

    monkeypatch.setattr(
        grouped,
        "save_document_as",
        save_variant,
    )
    monkeypatch.setattr(
        grouped,
        "close_group_document",
        lambda *_args, **_kwargs: "",
    )

    result = grouped.run_grouped_file(
        csv_path=tmp_path / "unused.csv",
        input_dir=tmp_path,
        output_dir=output_dir,
        source="Ghost.EMB",
        atomic_publish=True,
        on_variant_success=checkpoint,
    )

    assert result == 1
    assert checkpoint_values == [position_values]
    assert len(save_paths) == 1
    assert save_paths[0] != output_path
    assert ".__publishing_" in save_paths[0].name
    assert output_path.read_bytes() == b"ready"
    assert not save_paths[0].exists()


def test_atomic_publish_refuses_existing_final_without_mutating_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "Ghost.EMB"
    output_dir = tmp_path / "output"
    output_path = output_dir / "variant.EMB"
    source_path.write_bytes(b"source")
    output_path.parent.mkdir()
    output_path.write_bytes(b"verified")
    task = make_task(
        1,
        source_path,
        output_path,
        "1",
        "2",
    )
    errors: list[BaseException] = []
    monkeypatch.setattr(
        grouped,
        "prepare_group_tasks",
        lambda *_args, **_kwargs: (
            source_path,
            [task],
        ),
    )
    monkeypatch.setattr(
        grouped,
        "open_working_document",
        lambda *_args, **_kwargs: 123,
    )
    monkeypatch.setattr(
        grouped,
        "create_fresh_main_window",
        lambda _: pytest.fail(
            "Конфликт final output проверяется до изменения документа"
        ),
    )
    monkeypatch.setattr(
        grouped,
        "cleanup_group_document_best_effort",
        lambda *_: None,
    )

    with pytest.raises(
        FileExistsError,
        match="не будет его перезаписывать",
    ):
        grouped.run_grouped_file(
            csv_path=tmp_path / "unused.csv",
            input_dir=tmp_path,
            output_dir=output_dir,
            source="Ghost.EMB",
            atomic_publish=True,
            on_variant_error=(
                lambda _task, error, _values: errors.append(error)
            ),
        )

    assert len(errors) == 1
    assert isinstance(errors[0], FileExistsError)
    assert output_path.read_bytes() == b"verified"


def test_failed_variant_keeps_success_and_removes_working(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "Ghost.EMB"
    output_dir = tmp_path / "output"
    source_path.write_bytes(b"original")
    tasks = [
        make_task(
            number,
            source_path,
            output_dir / f"variant_{number}.EMB",
            str(number),
            "0",
        )
        for number in range(1, 3)
    ]
    cleanup_calls: list[tuple[int, str]] = []
    monkeypatch.setattr(
        grouped,
        "prepare_group_tasks",
        lambda *_args, **_kwargs: (
            source_path,
            tasks,
        ),
    )
    monkeypatch.setattr(
        grouped,
        "open_working_document",
        lambda *_args, **_kwargs: 123,
    )
    monkeypatch.setattr(
        grouped,
        "create_fresh_main_window",
        lambda _: object(),
    )
    monkeypatch.setattr(
        grouped,
        "set_document_position",
        lambda *_: {},
    )

    def save_variant(
        _hwnd: int,
        output_path: Path,
    ) -> None:
        if output_path == tasks[1].output_path:
            raise RuntimeError("variant failed")

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        output_path.write_bytes(b"success")

    monkeypatch.setattr(
        grouped,
        "save_document_as",
        save_variant,
    )
    monkeypatch.setattr(
        grouped,
        "cleanup_group_document_best_effort",
        lambda hwnd, stem: cleanup_calls.append(
            (
                hwnd,
                stem,
            )
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="variant failed",
    ):
        grouped.run_grouped_file(
            csv_path=tmp_path / "unused.csv",
            input_dir=tmp_path,
            output_dir=output_dir,
            source="Ghost.EMB",
        )

    assert tasks[0].output_path.read_bytes() == b"success"
    assert not tasks[1].output_path.exists()
    assert cleanup_calls == [
        (
            123,
            tasks[0].output_path.stem,
        )
    ]
    assert not list(
        (
            output_dir
            / ".working"
        ).glob("*.EMB")
    )


def test_close_group_document_uses_fresh_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []

    class FakeWindow:
        def set_focus(self) -> None:
            events.append("focus_wrapper")

    monkeypatch.setattr(
        grouped,
        "create_fresh_main_window",
        lambda hwnd: (
            events.append(
                (
                    "fresh",
                    hwnd,
                )
            )
            or FakeWindow()
        ),
    )
    monkeypatch.setattr(
        grouped,
        "focus_window",
        lambda hwnd: events.append(
            (
                "focus",
                hwnd,
            )
        ),
    )
    monkeypatch.setattr(
        grouped,
        "send_ctrl_virtual_key",
        lambda key: events.append(
            (
                "ctrl",
                key,
            )
        ),
    )
    monkeypatch.setattr(
        grouped,
        "wait_after_group_close",
        lambda *args, **kwargs: (
            events.append(
                (
                    "wait",
                    args,
                    kwargs,
                )
            )
            or "closed"
        ),
    )
    monkeypatch.setattr(
        grouped.win32gui,
        "GetWindowText",
        lambda _: "Wilcom - [variant]",
    )
    monkeypatch.setattr(
        grouped,
        "safe_window_exists",
        lambda _: True,
    )

    result = grouped.close_group_document(
        123,
        "variant",
    )

    assert result == "closed"
    assert events[0] == (
        "fresh",
        123,
    )
    assert (
        "ctrl",
        grouped.win32con.VK_F4,
    ) in events
    assert events.index("focus_wrapper") < events.index(
        (
            "ctrl",
            grouped.win32con.VK_F4,
        )
    )


def test_close_group_document_falls_back_to_uia_file_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    waits = 0
    wait_timeouts: list[float] = []
    menu_calls: list[tuple[int, set[str]]] = []

    class FakeWindow:
        def set_focus(self) -> None:
            pass

    def wait_close(*_args, **_kwargs) -> str:
        nonlocal waits
        waits += 1
        wait_timeouts.append(
            _kwargs["timeout"]
        )

        if waits == 1:
            raise TimeoutError("still open")

        return "closed"

    monkeypatch.setattr(
        grouped,
        "create_fresh_main_window",
        lambda _: FakeWindow(),
    )
    monkeypatch.setattr(
        grouped,
        "focus_window",
        lambda _: None,
    )
    monkeypatch.setattr(
        grouped,
        "send_ctrl_virtual_key",
        lambda _: None,
    )
    monkeypatch.setattr(
        grouped,
        "wait_after_group_close",
        wait_close,
    )
    monkeypatch.setattr(
        grouped.win32gui,
        "GetWindowText",
        lambda _: "Wilcom - [variant]",
    )
    monkeypatch.setattr(
        grouped.win32gui,
        "IsWindow",
        lambda _: True,
    )
    monkeypatch.setattr(
        grouped,
        "find_save_changes_dialog",
        lambda *_: None,
    )
    monkeypatch.setattr(
        grouped,
        "invoke_uia_file_menu_item",
        lambda hwnd, labels: (
            menu_calls.append(
                (
                    hwnd,
                    labels,
                )
            )
            or True
        ),
    )

    assert grouped.close_group_document(
        123,
        "variant",
    ) == "closed"
    assert menu_calls == [
        (
            123,
            grouped.CLOSE_MENU_TEXTS,
        )
    ]
    assert wait_timeouts == [
        5.0,
        2.0,
    ]


def test_close_uses_current_output_stem_not_groupwork(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    waited_stems: list[str] = []

    class FakeWindow:
        def set_focus(self) -> None:
            pass

    monkeypatch.setattr(
        grouped,
        "create_fresh_main_window",
        lambda _: FakeWindow(),
    )
    monkeypatch.setattr(
        grouped,
        "focus_window",
        lambda _: None,
    )
    monkeypatch.setattr(
        grouped,
        "send_ctrl_virtual_key",
        lambda _: None,
    )
    monkeypatch.setattr(
        grouped.win32gui,
        "GetWindowText",
        lambda _: "Wilcom - [variant_output]",
    )
    monkeypatch.setattr(
        grouped,
        "safe_window_exists",
        lambda _: True,
    )

    def wait_close(
        _hwnd: int,
        stem: str,
        **_kwargs,
    ) -> str:
        waited_stems.append(stem)
        return "Wilcom - No Design"

    monkeypatch.setattr(
        grouped,
        "wait_after_group_close",
        wait_close,
    )

    grouped.close_group_document(
        123,
        "Ghost_debug__groupwork_old",
    )

    assert waited_stems == [
        "variant_output"
    ]


def test_close_returns_immediately_when_active_stem_disappears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    titles = iter(
        [
            "Wilcom - [variant]",
            "Wilcom EmbroideryStudio - No Design",
        ]
    )
    ctrl_calls: list[int] = []

    class FakeWindow:
        def set_focus(self) -> None:
            pass

    monkeypatch.setattr(
        grouped,
        "create_fresh_main_window",
        lambda _: FakeWindow(),
    )
    monkeypatch.setattr(
        grouped,
        "focus_window",
        lambda _: None,
    )
    monkeypatch.setattr(
        grouped,
        "send_ctrl_virtual_key",
        lambda key: ctrl_calls.append(key),
    )
    monkeypatch.setattr(
        grouped,
        "find_save_changes_dialog",
        lambda *_: None,
    )
    monkeypatch.setattr(
        grouped.win32gui,
        "IsWindow",
        lambda _: True,
    )
    monkeypatch.setattr(
        grouped.win32gui,
        "GetWindowText",
        lambda _: next(titles),
    )
    monkeypatch.setattr(
        grouped,
        "invoke_uia_file_menu_item",
        lambda *_: pytest.fail(
            "UIA fallback не нужен после Ctrl+F4"
        ),
    )
    monkeypatch.setattr(
        grouped.time,
        "sleep",
        lambda _: pytest.fail(
            "Закрытие должно подтвердиться без ожидания"
        ),
    )

    result = grouped.close_group_document(
        123,
        "stale_groupwork",
    )

    assert "No Design" in result
    assert ctrl_calls == [
        grouped.win32con.VK_F4
    ]


def test_title_without_brackets_is_closed_document() -> None:
    title = "Wilcom EmbroideryStudio variant"

    assert not grouped.title_shows_document(
        title,
        "variant",
    )


def test_close_without_bracketed_document_sends_no_close_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeWindow:
        pass

    monkeypatch.setattr(
        grouped,
        "create_fresh_main_window",
        lambda _: FakeWindow(),
    )
    monkeypatch.setattr(
        grouped.win32gui,
        "GetWindowText",
        lambda _: "Wilcom EmbroideryStudio - No Design",
    )
    monkeypatch.setattr(
        grouped,
        "safe_window_exists",
        lambda _: True,
    )
    monkeypatch.setattr(
        grouped,
        "send_ctrl_virtual_key",
        lambda *_: pytest.fail(
            "Ctrl+F4 не нужен без активного документа"
        ),
    )
    monkeypatch.setattr(
        grouped,
        "invoke_uia_file_menu_item",
        lambda *_: pytest.fail(
            "UIA Close не нужен без активного документа"
        ),
    )

    result = grouped.close_group_document(
        123,
        "stale_groupwork",
    )

    assert result.endswith("No Design")


def test_stale_main_hwnd_sends_no_global_close_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        grouped,
        "safe_window_exists",
        lambda _: False,
    )
    monkeypatch.setattr(
        grouped,
        "create_fresh_main_window",
        lambda *_: pytest.fail(
            "Для stale HWND нельзя создавать wrapper"
        ),
    )
    monkeypatch.setattr(
        grouped,
        "send_ctrl_virtual_key",
        lambda *_: pytest.fail(
            "Для stale HWND нельзя слать Ctrl+F4"
        ),
    )

    assert grouped.close_group_document(
        123,
        "variant",
    ) == ""


def test_similar_document_stem_is_not_same_document() -> None:
    assert not grouped.title_shows_document(
        "Wilcom - [variant_copy]",
        "variant",
    )


def test_wait_close_dismisses_save_changes_without_saving(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    titles = iter(
        [
            "Wilcom EmbroideryStudio - No Design",
            "Wilcom EmbroideryStudio - No Design",
        ]
    )
    dismiss_calls: list[
        tuple[str, bool, float]
    ] = []
    dialog_visible = {
        "value": True,
    }
    monkeypatch.setattr(
        grouped.win32gui,
        "IsWindow",
        lambda _: True,
    )
    monkeypatch.setattr(
        grouped.win32gui,
        "GetWindowText",
        lambda _: next(titles),
    )
    monkeypatch.setattr(
        grouped,
        "find_save_changes_dialog",
        lambda *_: (
            (500, ["Сохранить изменения?"])
            if dialog_visible["value"]
            else None
        ),
    )

    def dismiss_dialog(
        stem: str,
        save: bool,
        timeout: float,
    ) -> bool:
        dismiss_calls.append(
            (
                stem,
                save,
                timeout,
            )
        )
        dialog_visible["value"] = False
        return True

    monkeypatch.setattr(
        grouped,
        "dismiss_save_changes_dialog",
        dismiss_dialog,
    )

    result = grouped.wait_after_group_close(
        123,
        "variant",
        timeout=5.0,
        emergency=False,
    )

    assert "No Design" in result
    assert dismiss_calls == [
        (
            "variant",
            False,
            pytest.approx(2.0),
        )
    ]


def test_wait_close_does_not_consume_full_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    titles = iter(
        [
            "Wilcom - [variant]",
            "Wilcom EmbroideryStudio - No Design",
        ]
    )
    sleeps: list[float] = []
    monkeypatch.setattr(
        grouped.win32gui,
        "IsWindow",
        lambda _: True,
    )
    monkeypatch.setattr(
        grouped.win32gui,
        "GetWindowText",
        lambda _: next(titles),
    )
    monkeypatch.setattr(
        grouped,
        "find_save_changes_dialog",
        lambda *_: None,
    )
    monkeypatch.setattr(
        grouped.time,
        "sleep",
        lambda seconds: sleeps.append(seconds),
    )

    result = grouped.wait_after_group_close(
        123,
        "variant",
        timeout=5.0,
        emergency=False,
    )

    assert "No Design" in result
    assert sleeps == [0.1]


def test_remove_missing_working_copy_is_not_error(
    tmp_path: Path,
) -> None:
    grouped.remove_group_working_copy(
        tmp_path / "missing.EMB"
    )


def test_timings_flag_is_supported() -> None:
    parser = grouped.build_argument_parser()
    args = parser.parse_args(
        [
            "--csv",
            "coordinates.csv",
            "--input-dir",
            "dataset",
            "--output-dir",
            "output",
            "--source",
            "Ghost.EMB",
            "--timings",
        ]
    )

    assert args.timings is True


def test_timing_uses_perf_counter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        grouped.time,
        "perf_counter",
        lambda: calls.append("perf_counter") or 12.5,
    )

    assert grouped.start_timing(True) == 12.5
    assert calls == ["perf_counter"]


def test_run_with_timings_forwards_collectors_and_prints_sections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source_path = tmp_path / "Ghost.EMB"
    output_dir = tmp_path / "output"
    source_path.write_bytes(b"source")
    task = make_task(
        1,
        source_path,
        output_dir / "variant.EMB",
        "1",
        "2",
    )
    perf_calls = 0
    open_collectors: list[
        dict[str, float]
    ] = []
    save_collectors: list[
        dict[str, float]
    ] = []
    close_collectors: list[
        dict[str, float]
    ] = []

    def perf_counter() -> float:
        nonlocal perf_calls
        perf_calls += 1
        return perf_calls / 100.0

    def open_document(
        _path: Path,
        es_path: Path | None = None,
        timings: dict[str, float] | None = None,
    ) -> int:
        del es_path
        assert timings is not None
        open_collectors.append(timings)
        timings["open_emb"] = 0.01
        timings["wait_wilcom_window"] = 0.02
        return 123

    def save_variant(
        _hwnd: int,
        _path: Path,
        timings: dict[str, float] | None = None,
    ) -> None:
        assert timings is not None
        save_collectors.append(timings)

        for key in (
            "open_save_as_dialog",
            "set_save_as_path",
            "click_save",
            "wait_save_dialog_closed",
            "wait_new_title",
            "wait_output_file",
            "wait_stable_size",
        ):
            timings[key] = 0.01

    def close_document(
        _hwnd: int,
        _stem: str,
        emergency: bool = False,
        timings: dict[str, float] | None = None,
    ) -> str:
        del emergency
        assert timings is not None
        close_collectors.append(timings)
        return "Wilcom - No Design"

    monkeypatch.setattr(
        grouped.time,
        "perf_counter",
        perf_counter,
    )
    monkeypatch.setattr(
        grouped,
        "prepare_group_tasks",
        lambda *_args, **_kwargs: (
            source_path,
            [task],
        ),
    )
    monkeypatch.setattr(
        grouped,
        "open_working_document",
        open_document,
    )
    monkeypatch.setattr(
        grouped,
        "create_fresh_main_window",
        lambda _: object(),
    )
    monkeypatch.setattr(
        grouped,
        "set_document_position",
        lambda *_: {},
    )
    monkeypatch.setattr(
        grouped,
        "save_document_as",
        save_variant,
    )
    monkeypatch.setattr(
        grouped,
        "close_group_document",
        close_document,
    )

    assert grouped.run_grouped_file(
        csv_path=tmp_path / "unused.csv",
        input_dir=tmp_path,
        output_dir=output_dir,
        source="Ghost.EMB",
        timings=True,
    ) == 1

    output = capsys.readouterr().out
    assert perf_calls > 0
    assert len(open_collectors) == 1
    assert len(save_collectors) == 1
    assert len(close_collectors) == 1
    assert "Открытие группы:" in output
    assert "Длительность варианта:" in output
    assert "fresh main wrapper" in output
    assert "find File menu" in output
    assert "find popup menu" in output
    assert "find Save As item" in output
    assert "wait dialog" in output
    assert "Завершение группы:" in output
    assert "всего завершение" in output


def test_error_cleanup_cancels_modal_before_document_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []
    dialog_exists = {
        "value": True,
    }
    fresh_window = object()
    monkeypatch.setattr(
        grouped,
        "find_save_as_dialog",
        lambda hwnd: (
            events.append(
                (
                    "find_save_as",
                    hwnd,
                )
            )
            or 500
        ),
    )

    def cancel_dialog(
        hwnd: int | None,
        timeout: float,
    ) -> None:
        events.append(
            (
                "cancel_save_as",
                hwnd,
                timeout,
            )
        )
        dialog_exists["value"] = False

    monkeypatch.setattr(
        grouped,
        "cancel_save_as_best_effort",
        cancel_dialog,
    )
    monkeypatch.setattr(
        grouped,
        "safe_window_exists",
        lambda hwnd: (
            events.append(
                (
                    "dialog_exists",
                    hwnd,
                )
            )
            or dialog_exists["value"]
        ),
    )
    monkeypatch.setattr(
        grouped,
        "create_fresh_main_window",
        lambda hwnd: (
            events.append(
                (
                    "fresh_wrapper",
                    hwnd,
                )
            )
            or fresh_window
        ),
    )
    monkeypatch.setattr(
        grouped,
        "close_document_best_effort",
        lambda hwnd, stem, window, timeout: (
            events.append(
                (
                    "close_document",
                    hwnd,
                    stem,
                    window,
                    timeout,
                )
            )
        ),
    )
    monkeypatch.setattr(
        grouped,
        "find_save_changes_dialog",
        lambda stem: (
            events.append(
                (
                    "find_dirty",
                    stem,
                )
            )
            or (
                600,
                ["Сохранить изменения?"],
            )
        ),
    )
    monkeypatch.setattr(
        grouped,
        "dismiss_save_changes_dialog",
        lambda stem, save, timeout: (
            events.append(
                (
                    "dismiss_dirty",
                    stem,
                    save,
                    timeout,
                )
            )
            or True
        ),
    )
    monkeypatch.setattr(
        grouped,
        "send_ctrl_virtual_key",
        lambda *_: pytest.fail(
            "Grouped cleanup не должен слать Ctrl+F4 "
            "до отмены Save As"
        ),
    )

    grouped.cleanup_group_document_best_effort(
        123,
        "variant",
    )

    names = [
        event[0]
        for event in events
    ]
    assert names.index(
        "cancel_save_as"
    ) < names.index(
        "dialog_exists"
    ) < names.index(
        "fresh_wrapper"
    ) < names.index(
        "close_document"
    ) < names.index(
        "dismiss_dirty"
    )
    assert (
        "close_document",
        123,
        "variant",
        fresh_window,
        8.0,
    ) in events
    assert (
        "dismiss_dirty",
        "variant",
        False,
        3.0,
    ) in events


def test_cleanup_does_not_close_document_while_save_as_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        grouped,
        "find_save_as_dialog",
        lambda _: 500,
    )
    monkeypatch.setattr(
        grouped,
        "cancel_save_as_best_effort",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        grouped,
        "safe_window_exists",
        lambda _: True,
    )
    monkeypatch.setattr(
        grouped,
        "create_fresh_main_window",
        lambda _: pytest.fail(
            "Нельзя закрывать документ при живом Save As"
        ),
    )

    grouped.cleanup_group_document_best_effort(
        123,
        "variant",
    )


def test_cleanup_failure_does_not_replace_variant_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "Ghost.EMB"
    output_dir = tmp_path / "output"
    source_path.write_bytes(b"source")
    task = make_task(
        1,
        source_path,
        output_dir / "variant.EMB",
        "1",
        "2",
    )
    original_error = RuntimeError(
        "original variant error"
    )
    monkeypatch.setattr(
        grouped,
        "prepare_group_tasks",
        lambda *_args, **_kwargs: (
            source_path,
            [task],
        ),
    )
    monkeypatch.setattr(
        grouped,
        "open_working_document",
        lambda *_args, **_kwargs: 123,
    )
    monkeypatch.setattr(
        grouped,
        "create_fresh_main_window",
        lambda _: object(),
    )
    monkeypatch.setattr(
        grouped,
        "set_document_position",
        lambda *_: {},
    )
    monkeypatch.setattr(
        grouped,
        "save_document_as",
        lambda *_: (
            (_ for _ in ()).throw(
                original_error
            )
        ),
    )
    monkeypatch.setattr(
        grouped.win32gui,
        "GetWindowText",
        lambda _: "Wilcom - [Ghost]",
    )
    monkeypatch.setattr(
        grouped,
        "cleanup_group_document_best_effort",
        lambda *_: (
            (_ for _ in ()).throw(
                RuntimeError("cleanup failed")
            )
        ),
    )

    with pytest.raises(RuntimeError) as captured:
        grouped.run_grouped_file(
            csv_path=tmp_path / "unused.csv",
            input_dir=tmp_path,
            output_dir=output_dir,
            source="Ghost.EMB",
        )

    assert captured.value is original_error
