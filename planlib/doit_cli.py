"""Единая точка вызова doit: ровно те аргументы, что проверяет `plan-check`.

`plan-run` и `acceptance_status` используют один и тот же построитель команды,
поэтому «прогнал» и «подтверждено» не могут разойтись по флагам, БД или каталогу.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

from .config import Layout


def doit_executable(layout: Layout) -> str | None:
    """doit из venv проекта, из окружения самого plan-ledger или из PATH."""
    names = ("doit.exe", "doit") if os.name == "nt" else ("doit", "doit.exe")
    candidates = []
    for base in (layout.root, layout.state):
        for scripts in (".venv/Scripts", ".venv/bin"):
            candidates.extend(base / scripts / name for name in names)
    for name in names:
        candidates.append(pathlib.Path(sys.executable).parent / name)
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return shutil.which("doit")


def command(layout: Layout, executable: str, action: str, *tasks: str) -> list[str]:
    """`doit -f <dodo> -d <root> <action> --db-file <db> [tasks…]`."""
    return [
        executable,
        "-f",
        str(layout.dodo),
        "-d",
        str(layout.root),
        action,
        "--db-file",
        str(layout.db),
        *tasks,
    ]


def run(layout: Layout, action: str, *tasks: str) -> subprocess.CompletedProcess:
    executable = doit_executable(layout)
    if executable is None:
        raise FileNotFoundError("doit not found: install it into the plan-ledger environment")
    # Каталог состояния может отсутствовать в свежем clone (пустая папка не
    # коммитится); doit не создаёт родителя для --db-file.
    layout.db.parent.mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        command(layout, executable, action, *tasks),
        cwd=layout.root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
    )
