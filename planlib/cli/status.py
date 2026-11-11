"""Точка входа для нового чата: что в плане, что готово, что дальше.

Печатает компактный обзор (или --json для агента): статусы, зависимости,
приёмку и одну рекомендованную следующую задачу.
"""

from __future__ import annotations

import argparse
import json
import pathlib

from planlib import acceptance_status, load_tasks, project_root, ready
from planlib.console import enable_utf8

ROOT = pathlib.Path.cwd()
BEGIN = "<!-- plans:begin -->"
END = "<!-- plans:end -->"


def build(project: pathlib.Path) -> dict:
    tasks = load_tasks(project)
    by_id = {task.id: task for task in tasks}
    rows = []
    for task in tasks:
        state, detail = (
            acceptance_status(project, task.shard) if task.shard else ("no-acceptance", "")
        )
        rows.append(
            {
                "id": task.id,
                "title": task.title,
                "status": task.status,
                "ready": ready(task, by_id),
                "dependencies": task.dependencies,
                "shard": task.shard,
                "acceptance": state,
                "detail": detail,
                "priority": task.priority,
            }
        )
    open_rows = [row for row in rows if row["status"] != "Done" and row["ready"]]
    open_rows.sort(key=lambda row: (row["status"] != "In Progress", row["id"]))
    return {
        "project": str(project_root(project)),
        "tasks": rows,
        "next": open_rows[0]["id"] if open_rows else None,
        "summary": {
            "total": len(rows),
            "done": sum(row["status"] == "Done" for row in rows),
            "in_progress": sum(row["status"] == "In Progress" for row in rows),
            "todo": sum(row["status"] == "To Do" for row in rows),
            "blocked": sum(not row["ready"] for row in rows if row["status"] != "Done"),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=pathlib.Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    enable_utf8()
    args = parser.parse_args(argv)

    data = build(args.project.resolve())
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    print(f"План: {data['project']}")
    print(f"{'task':8} {'status':12} {'ready':6} {'shard':9} {'приёмка':13} title")
    for row in data["tasks"]:
        shard = row["shard"] or "-"
        print(
            f"{row['id']:8} {row['status']:12} {'да' if row['ready'] else 'нет':6} "
            f"{shard:9} {row['acceptance']:13} {row['title'][:70]}"
        )
    summary = data["summary"]
    print(
        f"\nвсего {summary['total']}: done {summary['done']}, "
        f"in progress {summary['in_progress']}, to do {summary['todo']}, "
        f"заблокировано {summary['blocked']}"
    )
    print(f"СЛЕДУЮЩАЯ: {data['next'] or '— (нет готовых к работе задач)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
