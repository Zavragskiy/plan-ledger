"""Раскладка плана: конфиг, поиск вверх, резолв путей.

Конфиг ищется вверх от cwd: сначала ``plan-ledger.toml``, затем ``pyproject.toml``
с таблицей ``[tool.plan-ledger]``. Пути в конфиге — относительно его каталога.
"""

from __future__ import annotations

import argparse
import pathlib
from dataclasses import dataclass

try:  # Python 3.11+
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as _toml  # type: ignore[no-redef]

CONFIG_NAME = "plan-ledger.toml"
PYPROJECT_TABLE = ("tool", "plan-ledger")
DEFAULTS = {
    "root": ".",
    "state": ".",
    "tasks": "backlog/tasks",
    "dodo": "dodo.py",
    "db": ".doit.db",
}


class LayoutError(RuntimeError):
    """Конфиг или раскладка не разрешаются; CLI печатает сообщение и выходит с кодом 3."""


@dataclass(frozen=True)
class Layout:
    root: pathlib.Path
    state: pathlib.Path
    tasks: pathlib.Path
    dodo: pathlib.Path
    db: pathlib.Path
    config_file: pathlib.Path | None = None

    @property
    def tasks_exist(self) -> bool:
        return self.tasks.is_dir()

    def describe(self) -> str:
        state = "" if self.state == self.root else f" (state: {_rel(self.state, self.root)})"
        config = f" [config: {_rel(self.config_file, self.root)}]" if self.config_file else ""
        return f"{self.root}{state}{config}"

    def as_dict(self) -> dict[str, str | None]:
        return {
            "root": str(self.root),
            "state": str(self.state),
            "tasks": str(self.tasks),
            "dodo": str(self.dodo),
            "db": str(self.db),
            "config": str(self.config_file) if self.config_file else None,
        }


def _rel(path: pathlib.Path, base: pathlib.Path) -> str:
    try:
        return pathlib.Path(path).resolve().relative_to(base.resolve()).as_posix() or "."
    except ValueError:
        return str(path)


def _read_table(path: pathlib.Path) -> dict | None:
    try:
        data = _toml.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as error:
        raise LayoutError(f"{path}: не удалось прочитать конфиг ({error})") from error
    except _toml.TOMLDecodeError as error:
        raise LayoutError(f"{path}: некорректный TOML ({error})") from error
    if path.name == CONFIG_NAME:
        table = data.get("plan-ledger", data)
    else:
        table = data.get("tool", {}).get("plan-ledger")
    if not isinstance(table, dict):
        return None
    unknown = set(table) - set(DEFAULTS)
    if unknown:
        raise LayoutError(f"{path}: неизвестные ключи [plan-ledger]: {', '.join(sorted(unknown))}")
    for key, value in table.items():
        if not isinstance(value, str):
            raise LayoutError(f"{path}: [plan-ledger].{key} должно быть строкой")
    return table


def find_config(start: pathlib.Path) -> tuple[pathlib.Path, dict] | None:
    """Ближайший конфиг вверх от start."""
    start = start.resolve()
    for directory in (start, *start.parents):
        explicit = directory / CONFIG_NAME
        if explicit.is_file():
            table = _read_table(explicit)
            if table is not None:
                return explicit, table
        pyproject = directory / "pyproject.toml"
        if pyproject.is_file():
            table = _read_table(pyproject)
            if table is not None:
                return pyproject, table
    return None


def resolve(
    project: pathlib.Path | None = None,
    root: pathlib.Path | None = None,
    config: pathlib.Path | None = None,
    start: pathlib.Path | None = None,
) -> Layout:
    """Собирает раскладку: конфиг + override'ы, либо прежняя схема по --project."""
    start = (start or pathlib.Path.cwd()).resolve()
    search_start = (pathlib.Path(project).resolve() if project is not None else start)
    found: tuple[pathlib.Path, dict] | None
    if config is not None:
        config = config.resolve()
        if not config.is_file():
            raise LayoutError(f"конфиг не найден: {config}")
        table = _read_table(config)
        if table is None:
            raise LayoutError(f"{config}: нет таблицы [plan-ledger] или [tool.plan-ledger]")
        found = (config, table)
    else:
        found = find_config(search_start)

    if found is None:
        state = (project or start).resolve()
        code_root = (root or state).resolve()
        layout = Layout(
            root=code_root,
            state=state,
            tasks=state / DEFAULTS["tasks"],
            dodo=code_root / DEFAULTS["dodo"],
            db=state / DEFAULTS["db"],
            config_file=None,
        )
    else:
        config_file, table = found
        base = config_file.parent
        state = (project or base / table.get("state", DEFAULTS["state"])).resolve()
        code_root = (root or base / table.get("root", DEFAULTS["root"])).resolve()
        tasks_rel = table.get("tasks", DEFAULTS["tasks"])
        dodo_rel = table.get("dodo", DEFAULTS["dodo"])
        db_rel = table.get("db", DEFAULTS["db"])
        layout = Layout(
            root=code_root,
            state=state,
            tasks=(state / tasks_rel).resolve(),
            dodo=(code_root / dodo_rel).resolve(),
            db=(state / db_rel).resolve(),
            config_file=config_file,
        )

    if not layout.root.is_dir():
        raise LayoutError(f"каталог проекта не найден: {layout.root}")
    return layout


def add_layout_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", type=pathlib.Path, help="каталог состояния (backlog + БД)")
    parser.add_argument("--root", type=pathlib.Path, help="корень кода (dodo.py и file_dep)")
    parser.add_argument("--config", type=pathlib.Path, help="явный путь к конфигу")


def layout_arguments_parent(suppress_defaults: bool = False) -> argparse.ArgumentParser:
    """Родитель с общими флагами; suppress_defaults для подкоманд (--project после команды)."""
    parent = argparse.ArgumentParser(add_help=False)
    kwargs = {"default": argparse.SUPPRESS} if suppress_defaults else {}
    parent.add_argument("--project", type=pathlib.Path, **kwargs)
    parent.add_argument("--root", type=pathlib.Path, **kwargs)
    parent.add_argument("--config", type=pathlib.Path, **kwargs)
    return parent


def layout_from_args(args: argparse.Namespace) -> Layout:
    return resolve(
        project=getattr(args, "project", None),
        root=getattr(args, "root", None),
        config=getattr(args, "config", None),
    )
