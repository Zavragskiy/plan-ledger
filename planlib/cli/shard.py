"""`plan-shard`: which shards dodo.py declares and which tasks reference them.

Examples:
  plan-shard list           # table: shard, acceptance, tasks
  plan-shard list --strict  # exit 1 on a shard without tasks or a task without a shard
  plan-shard list --json    # the same for agents
"""

from __future__ import annotations

import argparse
import json

from planlib import acceptance_status, load_tasks
from planlib.config import (
    Layout,
    LayoutError,
    layout_arguments_parent,
    layout_from_args,
)
from planlib.console import enable_utf8
from planlib.shards import declared

def build(layout: Layout) -> dict:
    tasks = load_tasks(layout.tasks)
    names, source = declared(layout)
    linked: dict[str, list[str]] = {}
    unlinked: list[dict[str, str]] = []
    for task in tasks:
        if task.shard:
            linked.setdefault(task.shard, []).append(task.id)
        else:
            unlinked.append({"id": task.id, "title": task.title})

    rows: list[dict] = []
    for name in names:
        state, detail = acceptance_status(layout, name)
        rows.append(
            {
                "name": name,
                "in_dodo": True,
                "tasks": linked.get(name, []),
                "acceptance": state,
                "detail": detail,
            }
        )
    for name in sorted(set(linked) - set(names)):
        rows.append(
            {
                "name": name,
                "in_dodo": False,
                "tasks": linked[name],
                "acceptance": "unknown",
                "detail": "",
            }
        )

    violations: list[dict[str, str]] = []
    for row in rows:
        if row["in_dodo"] and not row["tasks"]:
            violations.append(
                {"kind": "empty-shard", "shard": row["name"], "detail": row["name"]}
            )
        elif not row["in_dodo"]:
            violations.append(
                {
                    "kind": "unknown-shard",
                    "shard": row["name"],
                    "detail": row["name"],
                }
            )
    for item in unlinked:
        violations.append({"kind": "unlinked-task", "id": item["id"], "detail": item["id"]})

    return {
        "layout": layout.as_dict(),
        "dodo": str(layout.dodo),
        "source": source,
        "shards": rows,
        "unlinked_tasks": unlinked,
        "violations": violations,
    }


def _violation_text(violation: dict[str, str]) -> str:
    if violation["kind"] == "empty-shard":
        return f"shard {violation['shard']}: no tasks"
    if violation["kind"] == "unknown-shard":
        return f"shard {violation['shard']}: tasks reference it, but dodo.py has no such shard"
    return f"{violation['id']}: no shard:<name> label"


def main(argv: list[str] | None = None) -> int:
    top = layout_arguments_parent()
    sub_flags = layout_arguments_parent(suppress_defaults=True)
    parser = argparse.ArgumentParser(prog="plan-shard", description=__doc__, parents=[top])
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list", parents=[sub_flags], help="dodo.py shards and their tasks")
    listing.add_argument("--json", action="store_true")
    listing.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 on hygiene violations: a shard without tasks, a task without a shard",
    )

    enable_utf8()
    args = parser.parse_args(argv)
    try:
        layout = layout_from_args(args)
    except LayoutError as error:
        print(f"config error: {error}")
        return 3
    if not layout.dodo.is_file():
        print(f"no dodo file: {layout.dodo}")
        return 3

    try:
        data = build(layout)
    except (OSError, SyntaxError) as error:
        print(f"failed to read dodo.py: {error}")
        return 3
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        if args.strict and data["violations"]:
            return 1
        return 0

    print(f"Plan: {layout.describe()}")
    print(f"dodo: {layout.dodo} ({data['source']})")
    print(f"{'shard':12} {'acceptance':13} tasks")
    for row in data["shards"]:
        tasks = ", ".join(row["tasks"]) or "—"
        if not row["in_dodo"]:
            tasks += "  (not in dodo.py)"
        print(f"{row['name']:12} {row['acceptance']:13} {tasks}")
        if row["detail"] and row["acceptance"] in {"error", "no-dodo", "no-doit"}:
            print(f"{'':12} └─ {row['detail']}")
    for item in data["unlinked_tasks"]:
        print(f"{'—':12} {'—':13} {item['id']} (no shard label)")

    violations = data["violations"]
    if violations:
        print("\nHYGIENE VIOLATIONS:")
        for violation in violations:
            print(f" - {_violation_text(violation)}")
    covered = sum(1 for row in data["shards"] if row["tasks"])
    print(
        f"\nshards in dodo.py: {sum(1 for row in data['shards'] if row['in_dodo'])}, "
        f"with tasks: {covered}, tasks without a shard: {len(data['unlinked_tasks'])}, "
        f"violations: {len(violations)}"
    )
    if args.strict and violations:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
