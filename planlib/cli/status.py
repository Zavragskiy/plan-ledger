"""New-chat entry point: what is in the plan, what is done, what is next.

Prints a compact overview (or --json for agents): layout, statuses,
dependencies, acceptance, and one recommended next task.
"""

from __future__ import annotations

import argparse
import json

from planlib import acceptance_status, load_tasks, ready
from planlib.config import (
    Layout,
    LayoutError,
    layout_arguments_parent,
    layout_from_args,
)
from planlib.console import enable_utf8


def build(layout: Layout) -> dict:
    tasks = load_tasks(layout.tasks)
    by_id = {task.id: task for task in tasks}
    rows = []
    for task in tasks:
        state, detail = (
            acceptance_status(layout, task.shard) if task.shard else ("no-acceptance", "")
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
                "criteria": task.criteria,
            }
        )
    open_rows = [row for row in rows if row["status"] != "Done" and row["ready"]]
    open_rows.sort(key=lambda row: (row["status"] != "In Progress", row["id"]))
    return {
        "layout": layout.as_dict(),
        "tasks": rows,
        "next": open_rows[0]["id"] if open_rows else None,
        "summary": {
            "total": len(rows),
            "done": sum(row["status"] == "Done" for row in rows),
            "in_progress": sum(row["status"] == "In Progress" for row in rows),
            "todo": sum(row["status"] == "To Do" for row in rows),
            "blocked": sum(not row["ready"] for row in rows if row["status"] != "Done"),
            "stale": sum(row["acceptance"] in {"run", "error"} for row in rows),
            "incomplete": sum(
                1
                for row in rows
                if row["status"] == "Done"
                and row["criteria"]["total"]
                and row["criteria"]["checked"] < row["criteria"]["total"]
            ),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, parents=[layout_arguments_parent()])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--allow-empty", action="store_true", help="an empty plan is not an error")
    enable_utf8()
    args = parser.parse_args(argv)

    try:
        layout = layout_from_args(args)
    except LayoutError as error:
        print(f"config error: {error}")
        return 3

    if not layout.tasks_exist and not args.allow_empty:
        print(
            f"no tasks directory: {layout.tasks}\n"
            "Run `plan-init --with-placeholder` or pass --project/--config."
        )
        return 3

    data = build(layout)
    if not data["tasks"] and not args.allow_empty:
        print(
            f"the plan has no tasks: {layout.tasks} "
            "(an empty plan is not success; see plan-init --with-placeholder)"
        )
        return 3

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    print(f"Plan: {layout.describe()}")
    print(f"{'task':8} {'status':12} {'AC':6} {'ready':6} {'shard':9} {'acceptance':13} title")
    for row in data["tasks"]:
        shard = row["shard"] or "-"
        criteria = row["criteria"]
        ac = f"{criteria['checked']}/{criteria['total']}" if criteria["total"] else "-"
        print(
            f"{row['id']:8} {row['status']:12} {ac:6} {'yes' if row['ready'] else 'no':6} "
            f"{shard:9} {row['acceptance']:13} {row['title'][:70]}"
        )
        if row["acceptance"] in {"error", "no-doit", "no-dodo"} and row["detail"]:
            print(f"{'':8} └─ {row['detail']}")
    summary = data["summary"]
    print(
        f"\ntotal {summary['total']}: done {summary['done']}, "
        f"in progress {summary['in_progress']}, to do {summary['todo']}, "
        f"blocked {summary['blocked']}, stale acceptance {summary['stale']}, "
        f"unchecked criteria {summary['incomplete']}"
    )
    print(f"NEXT: {data['next'] or '— (no ready tasks)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
