# EmbroideryAI — audit kit

Скопируйте содержимое архива в корень проекта. Старые исследовательские скрипты не удаляются.

## Почему добавлен `pytest.ini`

Сейчас файлы `tests/test_parser.py`, `tests/test_ddd_parser.py` и `tests/test_dst_parser.py` — это запускаемые вручную скрипты без функций `test_*`. Pytest импортирует их, выполняет верхнеуровневый код, но не считает тестами. Новый `pytest.ini` собирает только настоящие тесты из `tests/unit` и `tests/integration`.

## Запуск быстрых тестов

```powershell
python -m pytest tests\unit -vv
```

Ожидаются три `XFAIL`: они фиксируют уже найденные проблемы, а не поломку запуска.

## Запуск интеграционных тестов

```powershell
$env:EMB_AUDIT_LIMIT = "100"
python -m pytest tests\integration -vv -m integration
```

## Полный аудит корпуса

```powershell
python audit\audit_pipeline.py
```

Результаты появятся в:

```text
logs/audit_pipeline/report.json
logs/audit_pipeline/report.md
```
