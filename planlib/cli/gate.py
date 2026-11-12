"""Гейт плана: Done обязан быть и подтверждён приёмкой, и закрыт по критериям.

Коды выхода: 0 — чисто, 1 — stale/incomplete, 2 — --strict и непроверенные Done,
3 — конфиг/пустой план.
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


def collect(layout: Layout, tasks) -> list[dict]:
    rows: list[dict] = []
    for task in tasks:
        if task.shard:
            state, state_detail = acceptance_status(layout, task.shard)
        else:
            state, state_detail = "no-acceptance", "у задачи нет метки shard:<name>"
        criteria = task.criteria
        unchecked = task.unchecked()
        detail = state_detail
        if task.status == "Done":
            if criteria["total"] and unchecked:
                verdict = "incomplete"
                detail = "не отмечены критерии: " + ", ".join(str(number) for number in unchecked)
                if state != "up-to-date":
                    detail += f"; приёмка {state}"
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
            f"нет каталога задач: {layout.tasks}\n"
            "Запустите `plan-init` или укажите --project/--config."
        )
    return (
        f"в плане нет задач: {layout.tasks}\n"
        "Это не «зелёный» результат: задачи не найдены. "
        "Запустите `plan-init` или проверьте конфиг (--project/--config)."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, parents=[layout_arguments_parent()])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="непроверенные Done тоже ошибка")
    parser.add_argument("--allow-empty", action="store_true", help="пустой план не ошибка")
    enable_utf8()
    args = parser.parse_args(argv)

    try:
        layout = layout_from_args(args)
    except LayoutError as error:
        print(f"ошибка конфига: {error}")
        return 3

    tasks = load_tasks(layout.tasks)
    if not tasks and not args.allow_empty:
        print(_empty_message(layout))
        return 3

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
        print(f"План: {layout.describe()}")
        print(f"{'task':8} {'status':12} {'AC':6} {'shard':9} {'приёмка':13} вердикт")
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
            print("\nПРОТУХЛО:")
            for row in stale:
                print(f" - {row['id']}: Done, но приёмка {row['shard']} не подтверждена")
        if incomplete:
            print("\nНЕПОЛНЫЕ (Done с незакрытыми критериями):")
            for row in incomplete:
                print(f" - {row['id']}: {row['detail']}")
        if unverified:
            print("\nБЕЗ ПРИЁМКИ (историческое, не блокирует без --strict):")
            for row in unverified:
                print(f" - {row['id']}: {row['title'][:60]}")

    if stale or incomplete:
        return 1
    if args.strict and unverified:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
