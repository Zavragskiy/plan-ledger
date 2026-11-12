"""Тесты инструмента: модель, приёмка, адаптеры импорта, JSON-выход."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import import_plan  # noqa: E402
from planlib import Layout, acceptance_status, load_tasks, model, ready  # noqa: E402


def make_tasks(tmp_path: pathlib.Path, tasks: list[dict]) -> pathlib.Path:
    tasks_dir = tmp_path / "backlog" / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    for task in tasks:
        body = "---\n" + yaml.safe_dump(task, allow_unicode=True) + "---\n\n# Task\n"
        (tasks_dir / f"{task['id'].lower()}.md").write_text(body, encoding="utf-8")
    return tasks_dir


def make_layout(tmp_path: pathlib.Path) -> Layout:
    return Layout(
        root=tmp_path,
        state=tmp_path,
        tasks=tmp_path / "backlog" / "tasks",
        dodo=tmp_path / "dodo.py",
        db=tmp_path / ".doit.db",
    )


ROADMAP = """# Demo roadmap

## Phase 1: Setup
**Status:** Done (all green)

### Tasks

1. **Create skeleton** — DONE
2. **Wire entry point**

### Dependencies

- None

### Acceptance criteria

- [x] Package imports
- [x] CLI starts

---

## Phase 2: Extraction

### Tasks

1. **Move module**

### Dependencies

- Phase 1

### Acceptance criteria

- [ ] Module moved
- [ ] Tests green
"""

NUMBERED = """# Задача: Написать unit-тесты

**Статус:** ✅ Выполнено
**Приоритет:** Высокий
**Зависимости:** Нет

## Что сделать

1. Создать `tests/`.
2. Написать `test_tracker.py`.

## Критерий готовности

```bash
pytest tests/ -v
```
Все тесты проходят.
"""


def test_load_tasks_and_ready(tmp_path):
    tasks_dir = make_tasks(
        tmp_path,
        [
            {"id": "TASK-1", "title": "one", "status": "Done", "labels": ["shard:s1"]},
            {"id": "TASK-2", "title": "two", "status": "To Do", "dependencies": ["TASK-1"]},
        ],
    )
    tasks = load_tasks(tasks_dir)
    by_id = {task.id: task for task in tasks}
    assert len(tasks) == 2
    assert by_id["TASK-1"].shard == "s1"
    assert ready(by_id["TASK-2"], by_id) is True


def test_ready_blocks_on_unknown_dependency(tmp_path):
    tasks_dir = make_tasks(
        tmp_path, [{"id": "TASK-1", "title": "one", "status": "To Do", "dependencies": ["TASK-9"]}]
    )
    tasks = load_tasks(tasks_dir)
    assert ready(tasks[0], {task.id: task for task in tasks}) is False


def test_acceptance_without_doit(tmp_path, monkeypatch):
    monkeypatch.setattr("planlib.doit_cli.sys.executable", str(tmp_path / "python"))
    monkeypatch.setattr("planlib.doit_cli.shutil.which", lambda name: None)
    layout = make_layout(tmp_path)
    layout.dodo.write_text("", encoding="utf-8")
    state, _ = acceptance_status(layout, "s1")
    assert state == "no-doit"


def test_acceptance_without_dodo(tmp_path):
    state, detail = acceptance_status(make_layout(tmp_path), "s1")
    assert state == "no-dodo"
    assert "dodo" in detail


def test_roadmap_adapter(tmp_path):
    source = tmp_path / "roadmap.md"
    source.write_text(ROADMAP, encoding="utf-8")
    fmt, items = import_plan.parse(source)
    assert fmt == "roadmap"
    assert [item.status for item in items] == ["Done", "To Do"]
    assert items[1].deps == ["1"]
    assert items[0].steps == ["Create skeleton", "Wire entry point"]
    assert items[1].acceptance == ["Module moved", "Tests green"]


def test_numbered_adapter(tmp_path):
    source = tmp_path / "01-tests.md"
    source.write_text(NUMBERED, encoding="utf-8")
    fmt, items = import_plan.parse(source)
    assert fmt == "numbered"
    assert items[0].status == "Done"
    assert items[0].priority == "high"
    assert len(items[0].steps) == 2
    assert "pytest" in items[0].acceptance[0]


def test_plan_status_json_on_empty_project(tmp_path):
    make_tasks(tmp_path, [{"id": "TASK-1", "title": "one", "status": "To Do"}])
    result = subprocess.run(
        [sys.executable, str(ROOT / "plan_status.py"), "--project", str(tmp_path), "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["summary"]["total"] == 1
    assert data["next"] == "TASK-1"


def test_native_create_roundtrip(tmp_path):
    tasks_dir = tmp_path / "backlog" / "tasks"
    task = model.create(
        tasks_dir,
        title="s9: кэш спектров",
        description="Описание",
        labels=["shard:s9"],
        acceptance=["pytest tests/test_cache.py"],
    )
    assert task.id == "TASK-1"
    reloaded = load_tasks(tasks_dir)[0]
    assert reloaded.title == "s9: кэш спектров"
    assert reloaded.shard == "s9"
    assert reloaded.acceptance == [(False, "pytest tests/test_cache.py")]
    reloaded.check(1)
    model.save(reloaded, tasks_dir)
    assert load_tasks(tasks_dir)[0].acceptance[0][0] is True


def test_parses_backlog_written_file(tmp_path):
    """Файлы, созданные backlog.md (HTML-маркеры секций), читаются без миграции."""
    tasks_dir = make_tasks(tmp_path, [{"id": "TASK-3", "title": "demo", "status": "In Progress"}])
    (tasks_dir / "task-3 - demo.md").write_text(
        """---
id: TASK-3
title: 'demo'
status: In Progress
labels:
- shard:s3
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Текст
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 первый критерий
- [ ] #2 второй критерий
<!-- AC:END -->
""",
        encoding="utf-8",
    )
    task = load_tasks(tasks_dir)[0]
    assert task.status == "In Progress"
    assert task.shard == "s3"
    assert task.acceptance == [(True, "первый критерий"), (False, "второй критерий")]


def test_blocked_status_blocks_readiness(tmp_path):
    tasks_dir = make_tasks(
        tmp_path,
        [
            {"id": "TASK-1", "title": "one", "status": "Blocked"},
            {"id": "TASK-2", "title": "two", "status": "To Do"},
        ],
    )
    tasks = load_tasks(tasks_dir)
    by_id = {task.id: task for task in tasks}
    assert ready(by_id["TASK-1"], by_id) is False


def test_enable_utf8_is_safe_to_call_twice():
    from planlib.console import enable_utf8

    enable_utf8()
    enable_utf8()
    assert sys.stdout is not None


def test_check_index_is_validated(tmp_path):
    import pytest

    tasks_dir = tmp_path / "backlog" / "tasks"
    task = model.create(tasks_dir, title="one", acceptance=["only"])
    with pytest.raises(ValueError, match="критерия №2"):
        task.check(2)
    with pytest.raises(ValueError, match="критерия №0"):
        task.uncheck(0)
    assert task.criteria == {"checked": 0, "total": 1}
    assert task.unchecked() == [1]
