"""`plan-digest`: the compact snapshot an agent reads every few steps.

One row per task, no acceptance detail by default, totals always printed. The
answer to "what is relevant now": open tasks plus recent `Done` closeouts, with
`--task ID` pulling the closeouts of Done tasks that share the shard or files.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re

from planlib import (
    acceptance_detail,
    acceptance_state,
    acceptance_states,
    clear_cache,
    load_tasks,
    ready,
)
from planlib.config import (
    Layout,
    LayoutError,
    layout_arguments_parent,
    layout_from_args,
)
from planlib.console import enable_utf8
from planlib.model import Task, find, sort_key
from planlib.shards import declared
from planlib.verdicts import classify

DURATIONS = {"m": 60, "h": 3600, "d": 86400, "w": 604800}
SINCE = re.compile(r"\s*(\d+)\s*([mhdw])\s*", re.I)


def parse_since(value: str) -> dt.datetime:
    """`90d` → момент в прошлом; формат m/h/d/w, без календарных дат."""
    match = SINCE.fullmatch(value)
    if not match:
        raise ValueError(f"--since {value!r}: use a duration like 90d, 12h or 30m")
    return dt.datetime.now() - dt.timedelta(
        seconds=int(match.group(1)) * DURATIONS[match.group(2).lower()]
    )


def _closed_after(task: Task, since: dt.datetime) -> bool:
    if not task.closed:
        return False
    try:
        moment = dt.datetime.strptime(task.closed, "%Y-%m-%d %H:%M")
    except ValueError:
        return False
    return moment >= since


def _relation(target: Task, other: Task) -> list[str]:
    """Почему Done-задача относится к target: общий шард или общие файлы."""
    reasons: list[str] = []
    if target.shard and other.shard == target.shard:
        reasons.append(f"same shard {other.shard}")
    if target.closeout and other.closeout:
        shared = sorted(set(target.closeout.files) & set(other.closeout.files))
        if shared:
            reasons.append("files " + ", ".join(shared[:3]))
    return reasons


def _shard_states(layout: Layout) -> tuple[dict[str, str], dict[str, int]]:
    """(состояния dodo-шардов, {declared, proven}) — батч, без вызова на задачу."""
    try:
        names, _ = declared(layout)
    except (OSError, SyntaxError):
        names = []
    states = acceptance_states(layout) or {}
    proven = 0
    for name in names:
        state = states.get(name)
        if state is None:
            state = acceptance_state(layout, name)
        proven += state == "up-to-date"
    return states, {"declared": len(names), "proven": proven}


def build(layout: Layout, args: argparse.Namespace) -> dict:
    tasks = sorted(load_tasks(layout.tasks), key=sort_key)
    by_id = {task.id: task for task in tasks}
    since = parse_since(args.since) if args.since else None
    target = find(layout.tasks, args.task) if args.task else None

    states: dict[str, str] = {}

    def state_of(task: Task) -> str:
        if not task.shard:
            return "no-acceptance"
        if task.shard not in states:
            states[task.shard] = acceptance_state(layout, task.shard)
        return states[task.shard]

    rows: list[dict] = []
    hidden = {"active": 0, "since": 0, "status": 0, "task": 0, "limit": 0}
    for task in tasks:
        if target is None:
            if args.active and task.status == "Done":
                hidden["active"] += 1
                continue
            if since is not None and task.status == "Done" and not _closed_after(task, since):
                hidden["since"] += 1
                continue
            if args.status and task.status != args.status:
                hidden["status"] += 1
                continue
        state = state_of(task)
        criteria = task.criteria
        row = {
            "id": task.id,
            "status": task.status,
            "shard": task.shard,
            "ready": ready(task, by_id),
            "ac": f"{criteria['checked']}/{criteria['total']}" if criteria["total"] else "-",
            "acceptance": state,
        }
        if task.closeout and task.closeout.present:
            row["outcome"] = task.closeout.outcome
        if task.closed:
            row["closed"] = task.closed
        if target is not None and task.id != target.id:
            reasons = _relation(target, task)
            if not reasons:
                hidden["task"] += 1
                continue
            row["why"] = reasons
        rows.append(row)

    if args.limit is not None and len(rows) > args.limit:
        hidden["limit"] = len(rows) - args.limit
        rows = rows[: args.limit]

    totals = {
        "total": len(tasks),
        "done": sum(task.status == "Done" for task in tasks),
        "open": sum(task.status != "Done" for task in tasks),
        "stale": 0,
        "unconfirmed": 0,
        "no_closeout": 0,
    }
    for task in tasks:
        state = state_of(task)
        verdict = classify(task, state)
        totals["stale"] += verdict == "stale"
        totals["no_closeout"] += verdict == "no-closeout"
        totals["unconfirmed"] += (
            task.status != "Done" and state not in {"up-to-date", "no-acceptance"}
        )
    _, totals["shards"] = _shard_states(layout)

    next_task = next((task for task in tasks if task.status != "Done" and ready(task, by_id)), None)
    return {
        "plan": layout.describe(),
        "totals": totals,
        "shown": len(rows),
        "hidden": hidden,
        "next": next_task.id if next_task is not None else None,
        "tasks": rows,
    }


def _print(data: dict) -> None:
    print(f"Plan: {data['plan']}")
    print(f"{'task':12} {'status':12} {'shard':10} {'AC':6} {'acceptance':13} outcome")
    for row in data["tasks"]:
        outcome = row.get("outcome") or (f"closed {row['closed']}" if row.get("closed") else "-")
        if "why" in row:
            outcome += "  [" + "; ".join(row["why"]) + "]"
        print(
            f"{row['id']:12} {row['status']:12} {row['shard'] or '-':10} {row['ac']:6} "
            f"{row['acceptance']:13} {outcome[:60]}"
        )
    totals = data["totals"]
    print(
        f"\ntotal {totals['total']}: done {totals['done']}, open {totals['open']}, "
        f"stale {totals['stale']}, not confirmed {totals['unconfirmed']}, "
        f"no closeout {totals['no_closeout']}"
    )
    print(
        f"shards proven: {totals['shards']['proven']}/{totals['shards']['declared']} of dodo.py"
    )
    hidden = [f"{count} {name}" for name, count in data["hidden"].items() if count]
    if hidden:
        print("hidden: " + ", ".join(hidden))
    print(f"NEXT: {data['next'] or '— (no ready tasks)'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="plan-digest", description=__doc__, parents=[layout_arguments_parent()]
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--limit", type=int, metavar="N", help="show at most N rows")
    parser.add_argument("--active", action="store_true", help="hide Done rows")
    parser.add_argument("--status", help="only rows with this status")
    parser.add_argument(
        "--since", metavar="DURATION", help="only Done rows closed within 90d / 12h / 30m"
    )
    parser.add_argument(
        "--task",
        metavar="ID",
        help="this task plus Done tasks related by shard or files (overrides the filters)",
    )
    parser.add_argument(
        "--with-detail", action="store_true", help="include the acceptance detail (debugging)"
    )
    enable_utf8()
    args = parser.parse_args(argv)
    clear_cache()

    try:
        layout = layout_from_args(args)
    except LayoutError as error:
        print(f"config error: {error}")
        return 3
    if not layout.tasks_exist:
        print(
            f"no tasks directory: {layout.tasks}\n"
            "Run `plan-init --with-placeholder` or pass --project/--config."
        )
        return 3
    try:
        data = build(layout, args)
    except SystemExit:
        print(f"refused: task {args.task} not found in {layout.tasks}")
        return 3
    except ValueError as error:
        print(f"refused: {error}")
        return 3

    if args.with_detail:
        by_id = {task.id: task for task in load_tasks(layout.tasks)}
        for row in data["tasks"]:
            task = by_id[row["id"]]
            row["detail"] = acceptance_detail(layout, task.shard) if task.shard else None

    if args.json:
        print(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        return 0
    _print(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
