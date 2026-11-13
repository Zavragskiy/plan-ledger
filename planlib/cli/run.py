"""`plan-run`: run shard acceptance with exactly the arguments plan-check uses.

Examples:
  plan-run s3               # one shard
  plan-run s1 s2            # several
  plan-run --all            # every shard in dodo.py (plus any the plan references)
  plan-run --done           # only the shards of Done tasks (re-prove the closed set)
  plan-run                  # every doit task
  plan-run --project .planlib s3
"""

from __future__ import annotations

import argparse
import sys

from planlib import load_tasks
from planlib.config import (
    LayoutError,
    layout_arguments_parent,
    layout_from_args,
)
from planlib.console import enable_utf8
from planlib.doit_cli import command, doit_executable, run
from planlib.shards import declared


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="plan-run", description=__doc__, parents=[layout_arguments_parent()])
    parser.add_argument("shards", nargs="*", help="doit task names (all by default)")
    parser.add_argument(
        "--all",
        action="store_true",
        help="every shard declared by dodo.py, plus any shard the plan references",
    )
    parser.add_argument(
        "--done",
        action="store_true",
        help="only the shards of Done tasks; the skipped shards are printed",
    )
    parser.add_argument("--quiet", action="store_true", help="do not print the command")
    enable_utf8()
    args = parser.parse_args(argv)

    try:
        layout = layout_from_args(args)
    except LayoutError as error:
        print(f"config error: {error}")
        return 3

    if args.all and args.shards:
        print("--all cannot be combined with an explicit shard list")
        return 2
    if args.done and (args.all or args.shards):
        print("--done cannot be combined with --all or an explicit shard list")
        return 2

    if not layout.dodo.is_file():
        print(f"no dodo file: {layout.dodo}")
        return 3

    if args.done:
        # Пере-доказать ровно закрытый набор: шарды Done-задач, без контрактов
        # незапущенных стадий, которые падают по устройству дерева.
        tasks = load_tasks(layout.tasks)
        done_shards = list(
            dict.fromkeys(task.shard for task in tasks if task.status == "Done" and task.shard)
        )
        open_shards = list(
            dict.fromkeys(
                task.shard
                for task in tasks
                if task.status != "Done" and task.shard and task.shard not in done_shards
            )
        )
        if not done_shards:
            print(
                "no Done tasks with a shard:<name> label: "
                f"{layout.tasks}\nMark a task Done before re-proving it."
            )
            return 1
        args.shards = done_shards
        print("shards of Done tasks: " + ", ".join(done_shards))
        if open_shards:
            print(
                "skipped (not Done): " + ", ".join(open_shards),
                file=sys.stderr,
            )

    if args.all:
        # Покрытие — из dodo.py: шард без задач всё равно прогоняется, иначе
        # удаление последней задачи шарда тихо выключает проверку в CI.
        plan_shards = [task.shard for task in load_tasks(layout.tasks) if task.shard]
        try:
            declared_shards, _ = declared(layout)
        except (OSError, SyntaxError):
            declared_shards = []
        args.shards = list(dict.fromkeys([*declared_shards, *plan_shards]))
        if not args.shards:
            print(
                "no shards to run: dodo.py declares none and the plan has no "
                f"shard:<name> label ({layout.tasks})"
            )
            return 1
        print("shards from dodo.py and plan: " + ", ".join(args.shards))
        without_tasks = [name for name in declared_shards if name not in set(plan_shards)]
        if without_tasks:
            print(
                "warning: dodo.py shards without plan tasks: "
                + ", ".join(without_tasks)
                + " — plan-run --all runs them anyway (coverage comes from dodo.py)",
                file=sys.stderr,
            )

    executable = doit_executable(layout)
    if executable is None:
        print("doit not found: install it into the plan-ledger environment")
        return 3

    argv_out = command(layout, executable, "run", *args.shards)
    if not args.quiet:
        print("$ " + " ".join(argv_out))
    result = run(layout, "run", *args.shards)
    output = (result.stdout or "").rstrip()
    if output:
        print(output)
    errors = (result.stderr or "").rstrip()
    if errors:
        print(errors)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
