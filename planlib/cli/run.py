"""`plan-run`: прогнать приёмку шардов теми же аргументами, что проверяет plan-check.

Примеры:
  plan-run s3               # один шард
  plan-run s1 s2            # несколько
  plan-run                  # все задачи dodo
  plan-run --project .planlib s3
"""

from __future__ import annotations

import argparse

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
    parser.add_argument("--quiet", action="store_true", help="не печатать команду")
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
