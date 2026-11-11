"""`plan-task`: создание и правка задач плана без внешнего трекера.

Примеры:
  plan-task list
  plan-task new "s4: кэш спектров" --ac "pytest tests/test_cache.py" -l shard:s4
  plan-task set TASK-4 --status "In Progress" --if-status "To Do"
  plan-task set TASK-4 --check-ac 1 --note "session 7d23: приёмка зелёная"
"""

from __future__ import annotations

import argparse
import json
import pathlib

from planlib import model


def _print_task(task: model.Task) -> None:
    print(f"{task.id} [{task.status}] {task.title}")
    if task.labels:
        print(f"  labels: {', '.join(task.labels)}")
    if task.dependencies:
        print(f"  deps:   {', '.join(task.dependencies)}")
    for number, (done, text) in enumerate(task.acceptance, 1):
        print(f"  AC #{number} [{'x' if done else ' '}] {text}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="plan-task", description=__doc__)
    parser.add_argument("--project", type=pathlib.Path, default=pathlib.Path.cwd())
    sub = parser.add_subparsers(dest="command", required=True)

    listing = sub.add_parser("list", help="список задач")
    listing.add_argument("--status")
    listing.add_argument("--json", action="store_true")

    new = sub.add_parser("new", help="создать задачу")
    new.add_argument("title")
    new.add_argument("-d", "--description", default="")
    new.add_argument("--ac", action="append", default=[], help="критерий приёмки (можно несколько)")
    new.add_argument("-l", "--label", action="append", default=[])
    new.add_argument("--dep", action="append", default=[])
    new.add_argument("--priority", choices=["high", "medium", "low"])
    new.add_argument("--status", default=model.STATUSES[0], choices=model.STATUSES)
    new.add_argument("--owner")

    edit = sub.add_parser("set", help="изменить задачу (CAS через --if-status)")
    edit.add_argument("task_id")
    edit.add_argument("--status", choices=model.STATUSES)
    edit.add_argument("--if-status", help="менять только если текущий статус ровно такой")
    edit.add_argument("--owner")
    edit.add_argument("--priority", choices=["high", "medium", "low"])
    edit.add_argument("--label", action="append", default=[])
    edit.add_argument("--dep", action="append", default=[])
    edit.add_argument("--note", action="append", default=[])
    edit.add_argument("--check-ac", type=int)
    edit.add_argument("--uncheck-ac", type=int)
    edit.add_argument("--description")

    show = sub.add_parser("show", help="показать задачу")
    show.add_argument("task_id")
    show.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    project = args.project

    if args.command == "list":
        tasks = model.load_tasks(project)
        if args.status:
            tasks = [task for task in tasks if task.status == args.status]
        if args.json:
            payload = [
                {
                    "id": task.id,
                    "title": task.title,
                    "status": task.status,
                    "labels": task.labels,
                    "dependencies": task.dependencies,
                    "acceptance": [{"done": done, "text": text} for done, text in task.acceptance],
                }
                for task in tasks
            ]
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        for task in tasks:
            print(f"{task.id} [{task.status}] {task.title}")
        return 0

    if args.command == "new":
        task = model.create(
            project,
            title=args.title,
            description=args.description,
            status=args.status,
            labels=args.label,
            dependencies=args.dep,
            acceptance=args.ac,
            priority=args.priority,
            owner=args.owner,
        )
        _print_task(task)
        return 0

    if args.command == "show":
        task = model.find(project, args.task_id)
        if args.json:
            print(
                json.dumps(
                    {
                        "id": task.id,
                        "title": task.title,
                        "status": task.status,
                        "labels": task.labels,
                        "dependencies": task.dependencies,
                        "owner": task.owner,
                        "acceptance": [{"done": done, "text": text} for done, text in task.acceptance],
                        "notes": task.notes,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            _print_task(task)
        return 0

    task = model.find(project, args.task_id)
    if args.if_status and task.status != args.if_status:
        print(f"отказ: {task.id} в статусе '{task.status}', ожидался '{args.if_status}'")
        return 1
    if args.status:
        task.status = args.status
    if args.owner is not None:
        task.owner = args.owner
    if args.priority:
        task.priority = args.priority
    if args.description is not None:
        task.description = args.description
    for label in args.label:
        if label not in task.labels:
            task.labels.append(label)
    for dependency in args.dep:
        if dependency not in task.dependencies:
            task.dependencies.append(dependency)
    for note in args.note:
        task.notes.append(note)
    if args.check_ac:
        task.check(args.check_ac)
    if args.uncheck_ac:
        task.uncheck(args.uncheck_ac)
    path = model.save(task, project)
    print(f"{task.id} сохранён ({task.status}) → {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
