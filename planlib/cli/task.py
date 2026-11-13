"""`plan-task`: create and edit plan tasks without an external tracker.

The layout comes from the config (plan-ledger.toml / pyproject) or --project.
Examples:
  plan-task list
  plan-task new "s4: spectrum cache" --ac "pytest tests/test_cache.py" --shard s4
  plan-task new "Remove complexity exclusions" --id QUALITY-GATE --slug quality-gate --shard gate
  plan-task set TASK-4 --status "In Progress" --if-status "To Do"
  plan-task set quality-gate --slug quality-gate-v2        # rename the file
  plan-task list --project .planlib
"""

from __future__ import annotations

import argparse
import json
import re

from planlib import model
from planlib.config import (
    Layout,
    LayoutError,
    layout_arguments_parent,
    layout_from_args,
)
from planlib.console import enable_utf8


SHARD = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _with_shard(labels: list[str], value: str) -> list[str]:
    name = value.strip()
    if not SHARD.fullmatch(name):
        raise ValueError(
            f"shard {value!r}: one token of ASCII letters, digits, '.', '_' and '-'"
        )
    rest = [label for label in labels if not label.startswith("shard:")]
    return rest + [f"shard:{name}"]


def _indices(values: list[str]) -> list[int]:
    """Индексы критериев: `--check-ac 1 --check-ac 2` или `--check-ac 1,2`."""
    result: list[int] = []
    for value in values:
        for part in str(value).split(","):
            part = part.strip()
            if not part:
                continue
            try:
                result.append(int(part))
            except ValueError as error:
                raise SystemExit(f"not a number: {part!r}") from error
    return result


def _print_task(task: model.Task, layout: Layout) -> None:
    print(f"{task.id} [{task.status}] {task.title}")
    if task.labels:
        print(f"  labels: {', '.join(task.labels)}")
    if task.dependencies:
        print(f"  deps:   {', '.join(task.dependencies)}")
    for number, (done, text) in enumerate(task.acceptance, 1):
        print(f"  AC #{number} [{'x' if done else ' '}] {text}")
    if getattr(task, "path", None):
        try:
            shown = task.path.relative_to(layout.root).as_posix()
        except ValueError:
            shown = str(task.path)
        print(f"  file:   {shown}")


def main(argv: list[str] | None = None) -> int:
    top = layout_arguments_parent()
    sub_flags = layout_arguments_parent(suppress_defaults=True)
    parser = argparse.ArgumentParser(prog="plan-task", description=__doc__, parents=[top])
    sub = parser.add_subparsers(dest="command", required=True)

    listing = sub.add_parser("list", parents=[sub_flags], help="list tasks")
    listing.add_argument("--status")
    listing.add_argument("--json", action="store_true")

    new = sub.add_parser("new", parents=[sub_flags], help="create a task")
    new.add_argument("title")
    new.add_argument("-d", "--description", default="")
    new.add_argument("--ac", action="append", default=[], help="acceptance criterion (repeatable)")
    new.add_argument("-l", "--label", action="append", default=[])
    new.add_argument("--shard", help="shard:<name> label; same as -l shard:<name>")
    new.add_argument("--dep", action="append", default=[])
    new.add_argument("--priority", choices=["high", "medium", "low"])
    new.add_argument("--status", default=model.STATUSES[0], choices=model.STATUSES)
    new.add_argument("--owner")
    new.add_argument("--id", dest="task_id", help="explicit id instead of TASK-N (e.g. QUALITY-GATE)")
    new.add_argument(
        "--slug",
        help="file stem without .md instead of transliterating the title "
        "(ASCII letters, digits, '.', '_', '-')",
    )

    edit = sub.add_parser("set", parents=[sub_flags], help="edit a task (CAS via --if-status)")
    edit.add_argument("task_id")
    edit.add_argument("--status", choices=model.STATUSES)
    edit.add_argument("--if-status", help="change only if the current status is exactly this")
    edit.add_argument("--owner")
    edit.add_argument("--priority", choices=["high", "medium", "low"])
    edit.add_argument("--label", action="append", default=[])
    edit.add_argument("--shard", help="replace the shard:<name> label (other labels stay)")
    edit.add_argument("--slug", help="rename the task file; an empty string clears the slug")
    edit.add_argument("--dep", action="append", default=[])
    edit.add_argument("--note", action="append", default=[])
    edit.add_argument("--check-ac", action="append", default=[], metavar="N",
                      help="check criterion N; repeat or use a comma list: 1,2,3")
    edit.add_argument("--uncheck-ac", action="append", default=[], metavar="N",
                      help="uncheck criterion N; repeat or use a comma list")
    edit.add_argument("--description")
    edit.add_argument("--force", action="store_true",
                      help="allow Done even when not every criterion is checked")

    show = sub.add_parser("show", parents=[sub_flags], help="show a task")
    show.add_argument("task_id")
    show.add_argument("--json", action="store_true")

    enable_utf8()
    args = parser.parse_args(argv)
    try:
        layout = layout_from_args(args)
    except LayoutError as error:
        print(f"config error: {error}")
        return 3
    tasks = layout.tasks

    if args.command == "list":
        items = model.load_tasks(tasks)
        if args.status:
            items = [task for task in items if task.status == args.status]
        if args.json:
            print(
                json.dumps(
                    [
                        {
                            "id": task.id,
                            "title": task.title,
                            "slug": task.slug,
                            "status": task.status,
                            "labels": task.labels,
                            "dependencies": task.dependencies,
                            "acceptance": [
                                {"done": done, "text": text} for done, text in task.acceptance
                            ],
                        }
                        for task in items
                    ],
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        for task in items:
            print(f"{task.id} [{task.status}] {task.title}")
        return 0

    if args.command == "new":
        labels = list(args.label)
        try:
            if args.shard:
                labels = _with_shard(labels, args.shard)
            task = model.create(
                tasks,
                title=args.title,
                description=args.description,
                status=args.status,
                labels=labels,
                dependencies=args.dep,
                acceptance=args.ac,
                priority=args.priority,
                owner=args.owner,
                task_id=args.task_id,
                slug=args.slug,
            )
        except ValueError as error:
            print(f"refused: {error}")
            return 1
        _print_task(task, layout)
        return 0

    if args.command == "show":
        task = model.find(tasks, args.task_id)
        if args.json:
            print(
                json.dumps(
                    {
                        "id": task.id,
                        "title": task.title,
                        "slug": task.slug,
                        "status": task.status,
                        "labels": task.labels,
                        "dependencies": task.dependencies,
                        "owner": task.owner,
                        "acceptance": [
                            {"done": done, "text": text} for done, text in task.acceptance
                        ],
                        "notes": task.notes,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            _print_task(task, layout)
        return 0

    task = model.find(tasks, args.task_id)
    if args.if_status and task.status != args.if_status:
        print(f"refused: {task.id} is in status '{task.status}', expected '{args.if_status}'")
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
    if args.shard:
        try:
            task.labels = _with_shard(task.labels, args.shard)
        except ValueError as error:
            print(f"refused: {error}")
            return 1
    if args.slug is not None:
        slug = args.slug.strip() or None
        try:
            if slug:
                model.validate_slug(slug)
        except ValueError as error:
            print(f"refused: {error}")
            return 1
        task.slug = slug
    for dependency in args.dep:
        if dependency not in task.dependencies:
            task.dependencies.append(dependency)
    for note in args.note:
        task.notes.append(note)
    check_indices = _indices(args.check_ac)
    uncheck_indices = _indices(args.uncheck_ac)
    for index in check_indices:
        try:
            task.check(index)
        except ValueError as error:
            print(f"refused: {error}")
            return 1
    for index in uncheck_indices:
        try:
            task.uncheck(index)
        except ValueError as error:
            print(f"refused: {error}")
            return 1
    if args.status == "Done" and not args.force and task.unchecked():
        numbers = ", ".join(str(number) for number in task.unchecked())
        print(
            f"refused: {task.id} has unchecked criteria {numbers} "
            "(use --force to record Done anyway)"
        )
        return 1
    try:
        path = model.save(task, tasks)
    except ValueError as error:
        print(f"refused: {error}")
        return 1
    try:
        shown = path.relative_to(layout.root).as_posix()
    except ValueError:
        shown = str(path)
    print(f"{task.id} saved ({task.status}) → {shown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
