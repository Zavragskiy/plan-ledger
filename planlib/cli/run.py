"""`plan-run`: прогнать приёмку шардов теми же аргументами, что проверяет plan-check.

Примеры:
  plan-run s3               # один шард
  plan-run s1 s2            # несколько
  plan-run --all            # все шарды, на которые ссылаются задачи плана
  plan-run                  # все задачи dodo
  plan-run --project .planlib s3
"""

from __future__ import annotations

import argparse

from planlib import load_tasks
from planlib.config import (
    LayoutError,
    layout_arguments_parent,
    layout_from_args,
)
from planlib.console import enable_utf8
from planlib.doit_cli import command, doit_executable, run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="plan-run", description=__doc__, parents=[layout_arguments_parent()])
    parser.add_argument("shards", nargs="*", help="имена задач doit (по умолчанию — все)")
    parser.add_argument(
        "--all",
        action="store_true",
        help="все шарды, на которые ссылаются задачи плана (без ручного перечисления)",
    )
    parser.add_argument("--quiet", action="store_true", help="не печатать команду")
    enable_utf8()
    args = parser.parse_args(argv)

    try:
        layout = layout_from_args(args)
    except LayoutError as error:
        print(f"ошибка конфига: {error}")
        return 3

    if args.all and args.shards:
        print("--all нельзя сочетать с явным списком шардов")
        return 2
    if args.all:
        shards = [task.shard for task in load_tasks(layout.tasks) if task.shard]
        args.shards = list(dict.fromkeys(shards))
        if not args.shards:
            print(
                f"в плане нет задач с меткой shard:<name>: {layout.tasks}\n"
                "Создайте задачи с --shard или укажите шарды явно."
            )
            return 1
        print("шарды из плана: " + ", ".join(args.shards))

    if not layout.dodo.is_file():
        print(f"нет dodo-файла: {layout.dodo}")
        return 3
    executable = doit_executable(layout)
    if executable is None:
        print("doit не найден: установите его в окружение plan-ledger")
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
