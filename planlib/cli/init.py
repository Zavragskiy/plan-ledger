"""`plan-init`: скаффолд состояния плана и конфига раскладки.

Примеры:
  plan-init                       # состояние в .planlib, dodo.py в корне
  plan-init --state .             # корневая раскладка (как было)
  plan-init --config pyproject    # записать [tool.plan-ledger] в pyproject.toml
  plan-init --dry-run             # показать, что будет создано
"""

from __future__ import annotations

import argparse
import pathlib

from planlib.console import enable_utf8

DODO_TEMPLATE = '''"""Приёмка шардов плана.

Сгенерировано `plan-init`. doit меняет cwd на каталог этого файла, поэтому:
* file_dep собираются от ROOT (абсолютные пути на момент запуска);
* у каждой команды явно задан cwd=ROOT, иначе pytest/git унаследуют каталог dodo.
БД лежит рядом с состоянием: {db_path!r}.

Запускайте приёмку через `plan-run <shard>`: он передаёт те же -f/-d/--db-file,
что и `plan-check`. Ручной `doit` без `--db-file` положит БД в корень кода.
"""

from __future__ import annotations

import pathlib
import sys

from doit.action import CmdAction

ROOT = pathlib.Path(__file__).resolve().parent
STATE = ROOT / {state_rel!r}

DOIT_CONFIG = {{"verbosity": 2, "dep_file": str(STATE / {db_name!r})}}


def task_s1():
    """приёмка s1: замените команду и file_dep на реальные"""
    return {{
        "actions": [
            CmdAction(
                [sys.executable, "-c", "print('acceptance placeholder for s1')"],
                cwd=str(ROOT),
            )
        ],
        "file_dep": [str(ROOT / "dodo.py")],
        "verbosity": 2,
    }}
'''


def _write_config(
    root: pathlib.Path, table: dict[str, str], mode: str, force: bool, dry_run: bool
) -> pathlib.Path:
    lines = ["[plan-ledger]"] + [f'{key} = "{value}"' for key, value in table.items()] + [""]
    block = "\n".join(lines)
    if mode == "pyproject":
        target = root / "pyproject.toml"
        existing = target.read_text(encoding="utf-8") if target.is_file() else ""
        if "[tool.plan-ledger]" in existing:
            if not force:
                print(f"  = {target.name}: [tool.plan-ledger] уже есть, не трогаю")
                return target
            print("  ! pyproject уже содержит [tool.plan-ledger]; правьте вручную при --force")
            return target
        marker = "" if not existing else ("\n" if existing.endswith("\n") else "\n\n")
        text = existing + marker + "[tool.plan-ledger]\n" + "\n".join(
            f'{key} = "{value}"' for key, value in table.items()
        ) + "\n"
        if not dry_run:
            target.write_text(text, encoding="utf-8")
        print(f"  + {target.name}: добавлена таблица [tool.plan-ledger]")
        return target
    target = root / "plan-ledger.toml"
    if target.is_file() and target.read_text(encoding="utf-8") == block and not force:
        print(f"  = {target.name}: уже актуален")
        return target
    if target.is_file() and not force:
        print(f"  ! {target.name} уже есть и отличается; повторите с --force")
        return target
    if not dry_run:
        target.write_text(block, encoding="utf-8")
    print(f"  + {target.name}")
    return target


def _write_dodo(
    root: pathlib.Path, dodo_rel: str, state_rel: str, db_name: str, force: bool, dry_run: bool
) -> pathlib.Path:
    target = root / dodo_rel
    if target.is_file() and not force:
        print(f"  = {dodo_rel}: уже есть (перезапись только с --force)")
        return target
    content = DODO_TEMPLATE.format(state_rel=state_rel, db_name=db_name, db_path=f"{state_rel}/{db_name}")
    if not dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    print(f"  + {dodo_rel}")
    return target


def _update_gitignore(root: pathlib.Path, entries: list[str], dry_run: bool) -> None:
    target = root / ".gitignore"
    existing = target.read_text(encoding="utf-8") if target.is_file() else ""
    missing = [entry for entry in entries if entry not in existing.splitlines()]
    if not missing:
        print("  = .gitignore: уже содержит нужные строки")
        return
    text = existing.rstrip("\n")
    text = (text + "\n" if text else "") + "\n".join(missing) + "\n"
    if not dry_run:
        target.write_text(text, encoding="utf-8")
    print("  + .gitignore: " + ", ".join(missing))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="plan-init", description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path("."), help="корень кода")
    parser.add_argument("--state", type=pathlib.Path, default=pathlib.Path(".planlib"), help="каталог состояния")
    parser.add_argument("--tasks", default="backlog/tasks", help="каталог задач внутри состояния")
    parser.add_argument("--dodo", default="dodo.py", help="dodo-файл внутри корня")
    parser.add_argument("--db", default=".doit.db", help="файл БД внутри состояния")
    parser.add_argument(
        "--config", choices=["toml", "pyproject"], default="toml", help="куда писать конфиг"
    )
    parser.add_argument("--force", action="store_true", help="перезаписать dodo.py и конфиг")
    parser.add_argument("--dry-run", action="store_true", help="ничего не писать")
    enable_utf8()
    args = parser.parse_args(argv)

    root = (pathlib.Path.cwd() / args.root).resolve()
    state = (pathlib.Path.cwd() / args.state).resolve()
    if not root.is_dir():
        print(f"нет каталога проекта: {root}")
        return 3
    try:
        state_rel = state.relative_to(root).as_posix() or "."
    except ValueError:
        print(f"состояние {state} должно лежать внутри {root}")
        return 3
    if args.db.startswith("/") or ".." in pathlib.PurePosixPath(args.db).parts:
        print("--db должен быть путём внутри каталога состояния")
        return 3

    tasks_dir = state / args.tasks
    print(f"Раскладка: root={root}, state={state_rel}, tasks={tasks_dir}")
    if not args.dry_run:
        (tasks_dir).mkdir(parents=True, exist_ok=True)
        keep = tasks_dir / ".gitkeep"
        if not keep.exists():
            keep.write_text("", encoding="utf-8")
        print(f"  + {tasks_dir.relative_to(root).as_posix()}/")

    table = {
        "root": ".",
        "state": state_rel,
        "tasks": args.tasks,
        "dodo": args.dodo,
        "db": args.db,
    }
    _write_config(root, table, args.config, args.force, args.dry_run)
    _write_dodo(root, args.dodo, state_rel, args.db, args.force, args.dry_run)
    db_entry = f"{state_rel}/{args.db}" if state_rel != "." else args.db
    _update_gitignore(root, [f"{db_entry}*", "__pycache__/"], args.dry_run)

    if args.dry_run:
        print("\ndry-run: ничего не создано")
        return 0
    print(
        "\nГотово. Дальше:\n"
        "  plan-task new \"s1: первый шард\" --ac \"<команда приёмки>\" -l shard:s1\n"
        "  plan-run s1\n"
        "  plan-task set task-1 --status Done --check-ac 1 --note \"plan-run s1 — passed\"\n"
        "  plan-check"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
