"""Порядок задач: один ключ для plan-status и plan-task list."""

from __future__ import annotations

import pathlib

import yaml

from planlib import model
from planlib.cli import status as plan_status
from planlib.cli import task as plan_task


def make(task_id: str, status: str = "To Do", priority: str | None = None) -> model.Task:
    return model.Task(id=task_id, title=task_id, status=status, priority=priority)


def test_numeric_ids_sort_as_numbers():
    tasks = [make("TASK-13"), make("TASK-8"), make("TASK-1000")]
    assert [task.id for task in sorted(tasks, key=model.sort_key)] == [
        "TASK-8",
        "TASK-13",
        "TASK-1000",
    ]


def test_in_progress_then_priority_then_id():
    tasks = [
        make("TASK-1", "Done"),
        make("TASK-2", "To Do"),
        make("TASK-3", "To Do", "high"),
        make("TASK-4", "In Progress", "low"),
    ]
    assert [task.id for task in sorted(tasks, key=model.sort_key)] == [
        "TASK-4",
        "TASK-3",
        "TASK-2",
        "TASK-1",
    ]


def test_next_respects_priority(tmp_path, monkeypatch):
    tasks_dir = tmp_path / "backlog" / "tasks"
    tasks_dir.mkdir(parents=True)
    model.create(tasks_dir, title="low one", labels=["shard:s1"], task_id="TASK-1")
    model.create(
        tasks_dir,
        title="urgent",
        labels=["shard:s1"],
        task_id="TASK-2",
        priority="high",
    )
    monkeypatch.setattr(
        "planlib.cli.status.acceptance_status", lambda layout, shard: ("up-to-date", "")
    )
    data = plan_status.build(_layout(tmp_path, tasks_dir))
    assert data["next"] == "TASK-2", "high-задача важнее меньшего id"
    assert [row["id"] for row in data["tasks"]] == ["TASK-2", "TASK-1"]


def test_task_list_uses_the_same_order(tmp_path, capsys):
    tasks_dir = tmp_path / "backlog" / "tasks"
    tasks_dir.mkdir(parents=True)
    for task_id in ("TASK-13", "TASK-8"):
        (tasks_dir / f"{task_id.lower()}.md").write_text(
            "---\n"
            + yaml.safe_dump({"id": task_id, "title": task_id, "status": "To Do"})
            + "---\n",
            encoding="utf-8",
        )
    assert plan_task.main(["list", "--project", str(tmp_path)]) == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert lines == ["TASK-8 [To Do] TASK-8", "TASK-13 [To Do] TASK-13"]


def _layout(tmp_path: pathlib.Path, tasks_dir: pathlib.Path):
    from planlib.config import Layout

    return Layout(
        root=tmp_path,
        state=tmp_path,
        tasks=tasks_dir,
        dodo=tmp_path / "dodo.py",
        db=tmp_path / ".doit.db",
    )
