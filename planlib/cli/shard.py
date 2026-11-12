"""`plan-shard`: какие шарды объявлены в dodo.py и какие задачи на них ссылаются.

Примеры:
  plan-shard list           # таблица: шард, приёмка, задачи
  plan-shard list --json    # то же для агента
"""

from __future__ import annotations

import argparse
import ast
import json

from planlib import acceptance_status, load_tasks
from planlib.config import (
    Layout,
    LayoutError,
    layout_arguments_parent,
    layout_from_args,
)
from planlib.console import enable_utf8
from planlib.doit_cli import run as run_doit


def declared_from_doit(layout: Layout) -> list[str] | None:
    """Шарды через `doit list`: учитывает и динамически созданные задачи."""
    result = run_doit(layout, "list")
    if result.returncode != 0:
        return None
    names: list[str] = []
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if line:
            names.append(line.split()[0].rstrip(":"))
    return names or None


def declared_from_source(layout: Layout) -> list[str]:
    """Fallback: имена функций `task_*` прямо из dodo.py, без запуска doit."""
    tree = ast.parse(layout.dodo.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
            "task_"
        ):
            names.append(node.name[len("task_") :])
    return names


def declared(layout: Layout) -> tuple[list[str], str]:
    names = declared_from_doit(layout)
    if names is not None:
        return names, "doit"
    return declared_from_source(layout), "ast"


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
    return {
        "layout": layout.as_dict(),
        "dodo": str(layout.dodo),
        "source": source,
        "shards": rows,
        "unlinked_tasks": unlinked,
    }


def main(argv: list[str] | None = None) -> int:
    top = layout_arguments_parent()
    sub_flags = layout_arguments_parent(suppress_defaults=True)
    parser = argparse.ArgumentParser(prog="plan-shard", description=__doc__, parents=[top])
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list", parents=[sub_flags], help="шарды dodo.py и их задачи")
    listing.add_argument("--json", action="store_true")

    enable_utf8()
    args = parser.parse_args(argv)
    try:
        layout = layout_from_args(args)
    except LayoutError as error:
        print(f"ошибка конфига: {error}")
        return 3
    if not layout.dodo.is_file():
        print(f"нет dodo-файла: {layout.dodo}")
        return 3

    try:
        data = build(layout)
    except (OSError, SyntaxError) as error:
        print(f"не удалось прочитать dodo.py: {error}")
        return 3
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    print(f"План: {layout.describe()}")
    print(f"dodo: {layout.dodo} ({data['source']})")
    print(f"{'shard':12} {'приёмка':13} задачи")
    for row in data["shards"]:
        tasks = ", ".join(row["tasks"]) or "—"
        if not row["in_dodo"]:
            tasks += "  (нет в dodo.py)"
        print(f"{row['name']:12} {row['acceptance']:13} {tasks}")
        if row["detail"] and row["acceptance"] in {"error", "no-dodo", "no-doit"}:
            print(f"{'':12} └─ {row['detail']}")
    for item in data["unlinked_tasks"]:
        print(f"{'—':12} {'—':13} {item['id']} (без метки shard)")
    covered = sum(1 for row in data["shards"] if row["tasks"])
    print(
        f"\nшардов в dodo.py: {sum(1 for row in data['shards'] if row['in_dodo'])}, "
        f"с задачами: {covered}, задач без шарда: {len(data['unlinked_tasks'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
