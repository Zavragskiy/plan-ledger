"""Plan gate: Done must be proven by acceptance and closed by criteria.

Exit codes: 0 clean, 1 stale/incomplete, 2 --strict with unverified Done,
3 config error or empty plan.
"""

from __future__ import annotations

import argparse
import json
import sys

from planlib import acceptance_status, load_tasks
from planlib.config import (
    Layout,
    LayoutError,
    layout_arguments_parent,
    layout_from_args,
)
from planlib.console import enable_utf8


def collect(layout: Layout, tasks) -> list[dict]:
    rows: list[dict] = []
    for task in tasks:
        if task.shard:
            state, state_detail = acceptance_status(layout, task.shard)
        else:
            state, state_detail = "no-acceptance", "the task has no shard:<name> label"
        criteria = task.criteria
        unchecked = task.unchecked()
        detail = state_detail
        if task.status == "Done":
            if criteria["total"] and unchecked:
                verdict = "incomplete"
                detail = "unchecked criteria: " + ", ".join(str(number) for number in unchecked)
                if state != "up-to-date":
                    detail += f"; acceptance {state}"
                    if state_detail:
                        detail += f" ({state_detail})"
            elif state == "up-to-date":
                verdict = "ok"
            elif state == "no-acceptance":
                verdict = "unverified"
            else:
                verdict = "stale"
        else:
            verdict = "open"
        rows.append(
            {
                "id": task.id,
                "title": task.title,
                "status": task.status,
                "shard": task.shard,
                "acceptance": state,
                "detail": detail,
                "verdict": verdict,
                "criteria": criteria,
            }
        )
    return rows


def _empty_message(layout: Layout) -> str:
    if not layout.tasks_exist:
        return (
            f"no tasks directory: {layout.tasks}\n"
            "Run `plan-init --with-placeholder` (or --allow-empty) "
            "or pass --project/--config."
        )
    return (
        f"the plan has no tasks: {layout.tasks}\n"
        "This is not a green result: no tasks were found. "
        "Run `plan-init --with-placeholder`, `plan-check --allow-empty` "
        "or check the config (--project/--config)."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, parents=[layout_arguments_parent()])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="also fail on unverified Done tasks")
    parser.add_argument("--allow-empty", action="store_true", help="an empty plan is not an error")
    enable_utf8()
    args = parser.parse_args(argv)

    try:
        layout = layout_from_args(args)
    except LayoutError as error:
        print(f"config error: {error}")
        return 3

    tasks = load_tasks(layout.tasks)
    if not tasks and not args.allow_empty:
        print(_empty_message(layout))
        return 3
    if not tasks:
        print(
            "warning: the empty plan was accepted because of --allow-empty — "
            "this is not proof of work, only a bootstrap escape hatch.",
            file=sys.stderr,
        )

    rows = collect(layout, tasks)
    stale = [row for row in rows if row["verdict"] == "stale"]
    incomplete = [row for row in rows if row["verdict"] == "incomplete"]
    unverified = [row for row in rows if row["verdict"] == "unverified"]
    summary = {
        "tasks": len(rows),
        "ok": sum(row["verdict"] == "ok" for row in rows),
        "stale": len(stale),
        "incomplete": len(incomplete),
        "unverified": len(unverified),
        "open": sum(row["verdict"] == "open" for row in rows),
    }

    if args.json:
        print(
            json.dumps(
                {"layout": layout.as_dict(), "rows": rows, "summary": summary},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"Plan: {layout.describe()}")
        print(f"{'task':8} {'status':12} {'AC':6} {'shard':9} {'acceptance':13} verdict")
        for row in rows:
            shard = row["shard"] or "-"
            criteria = row["criteria"]
            ac = f"{criteria['checked']}/{criteria['total']}" if criteria["total"] else "-"
            print(
                f"{row['id']:8} {row['status']:12} {ac:6} {shard:9} "
                f"{row['acceptance']:13} {row['verdict']}"
            )
            if row["verdict"] in {"stale", "incomplete"} and row["detail"]:
                print(f"{'':8} └─ {row['detail']}")
        if stale:
            print("\nSTALE:")
            for row in stale:
                print(f" - {row['id']}: Done, but acceptance {row['shard']} is not confirmed")
        if incomplete:
            print("\nINCOMPLETE (Done with unchecked criteria):")
            for row in incomplete:
                print(f" - {row['id']}: {row['detail']}")
        if unverified:
            print("\nUNVERIFIED (historical, not blocking without --strict):")
            for row in unverified:
                print(f" - {row['id']}: {row['title'][:60]}")

    if stale or incomplete:
        return 1
    if args.strict and unverified:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
