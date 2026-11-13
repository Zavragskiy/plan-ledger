"""New-chat entry point: what is in the plan, what is done, what is next.

Prints a compact overview (or --json for agents): layout, statuses,
dependencies, acceptance, and one recommended next task.

Order is one contract (``planlib.model.sort_key``): In Progress first, then
priority, then a natural id. ``stale`` means a ``Done`` task whose acceptance
is not confirmed; an open task with changed inputs is ``not confirmed``.
"""

from __future__ import annotations

import argparse
import json

from planlib import acceptance_detail, acceptance_state, clear_cache, load_tasks, ready
from planlib.config import (
    Layout,
    LayoutError,
    layout_arguments_parent,
    layout_from_args,
)
from planlib.console import enable_utf8
from planlib.model import sort_key
from planlib.verdicts import ERROR_STATES, classify, detail_for, needs_detail

PRIORITY_SHORT = {"high": "high", "medium": "med", "low": "low"}


def build(layout: Layout, with_detail: bool = False) -> dict:
    tasks = sorted(load_tasks(layout.tasks), key=sort_key)
    by_id = {task.id: task for task in tasks}
    rows = []
    for task in tasks:
        if task.shard:
            state = acceptance_state(layout, task.shard)
            verdict = classify(task, state)
            detail = ""
            if needs_detail(task, state, verdict, with_detail):
                detail = acceptance_detail(layout, task.shard)
        else:
            state, verdict, detail = "no-acceptance", classify(task, "no-acceptance"), ""
        rows.append(
            {
                "id": task.id,
                "title": task.title,
                "status": task.status,
                "ready": ready(task, by_id),
                "dependencies": task.dependencies,
                "shard": task.shard,
                "acceptance": state,
                "detail": detail_for(task, state, detail, verdict, with_detail),
                "verdict": verdict,
                "priority": task.priority,
                "criteria": task.criteria,
            }
        )
    next_row = next(
        (row for row in rows if row["status"] != "Done" and row["ready"]),
        None,
    )
    return {
        "layout": layout.as_dict(),
        "tasks": rows,
        "next": next_row["id"] if next_row else None,
        "summary": {
            "total": len(rows),
            "done": sum(row["status"] == "Done" for row in rows),
            "in_progress": sum(row["status"] == "In Progress" for row in rows),
            "todo": sum(row["status"] == "To Do" for row in rows),
            "blocked": sum(not row["ready"] for row in rows if row["status"] != "Done"),
            "stale": sum(row["verdict"] == "stale" for row in rows),
            "unconfirmed": sum(
                row["status"] != "Done"
                and row["acceptance"] not in {"up-to-date", "no-acceptance"}
                for row in rows
            ),
            "incomplete": sum(row["verdict"] == "incomplete" for row in rows),
        },
    }


def _detail_line(row: dict) -> str | None:
    if row["detail"] and row["acceptance"] in ERROR_STATES:
        return row["detail"]
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, parents=[layout_arguments_parent()])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--open", action="store_true", help="hide Done rows (totals stay)")
    parser.add_argument(
        "--with-detail",
        action="store_true",
        help="print the full acceptance detail instead of the first three paths",
    )
    parser.add_argument("--allow-empty", action="store_true", help="an empty plan is not an error")
    enable_utf8()
    args = parser.parse_args(argv)
    clear_cache()  # кэш живёт один вызов команды, а не процесс целиком

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

    data = build(layout, args.with_detail)
    if not data["tasks"] and not args.allow_empty:
        print(
            f"the plan has no tasks: {layout.tasks} "
            "(an empty plan is not success; see plan-init --with-placeholder)"
        )
        return 3

    if args.open:
        hidden = sum(row["status"] == "Done" for row in data["tasks"])
        data["tasks"] = [row for row in data["tasks"] if row["status"] != "Done"]
        data["summary"]["hidden_done"] = hidden

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    print(f"Plan: {layout.describe()}")
    print(
        f"{'task':8} {'status':12} {'prio':5} {'AC':6} {'ready':6} "
        f"{'shard':9} {'acceptance':13} title"
    )
    for row in data["tasks"]:
        shard = row["shard"] or "-"
        criteria = row["criteria"]
        ac = f"{criteria['checked']}/{criteria['total']}" if criteria["total"] else "-"
        priority = PRIORITY_SHORT.get((row["priority"] or "").lower(), "-")
        print(
            f"{row['id']:8} {row['status']:12} {priority:5} {ac:6} "
            f"{'yes' if row['ready'] else 'no':6} {shard:9} {row['acceptance']:13} "
            f"{row['title'][:70]}"
        )
        detail = _detail_line(row)
        if detail:
            print(f"{'':8} └─ {detail}")
    if args.open:
        print(f"… {data['summary']['hidden_done']} Done hidden (--open); totals below cover all")
    summary = data["summary"]
    print(
        f"\ntotal {summary['total']}: done {summary['done']}, "
        f"in progress {summary['in_progress']}, to do {summary['todo']}, "
        f"blocked {summary['blocked']}, stale {summary['stale']}, "
        f"not confirmed {summary['unconfirmed']}, "
        f"unchecked criteria {summary['incomplete']}"
    )
    print(f"NEXT: {data['next'] or '— (no ready tasks)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
