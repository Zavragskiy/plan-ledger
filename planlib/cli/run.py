"""`plan-run`: run shard acceptance with exactly the arguments plan-check uses.

Examples:
  plan-run s3               # one shard
  plan-run s1 s2            # several
  plan-run --all            # every shard referenced by the plan
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
        help="every shard referenced by the plan (no manual list)",
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
    if args.all:
        shards = [task.shard for task in load_tasks(layout.tasks) if task.shard]
        args.shards = list(dict.fromkeys(shards))
        if not args.shards:
            print(
                f"the plan has no tasks with a shard:<name> label: {layout.tasks}\n"
                "Create tasks with --shard or pass shard names explicitly."
            )
            return 1
        print("shards from plan: " + ", ".join(args.shards))

    if not layout.dodo.is_file():
        print(f"no dodo file: {layout.dodo}")
        return 3

    if args.all:
        try:
            names, _ = declared(layout)
        except (OSError, SyntaxError):
            names = []
        unused = [name for name in names if name not in set(args.shards)]
        if unused:
            print(
                "warning: dodo.py declares shards without tasks: "
                + ", ".join(unused)
                + " — plan-run --all does not run them",
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
