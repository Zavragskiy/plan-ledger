"""Статус приёмки шарда через doit.

doit вызывается с явными ``-f`` (dodo), ``-d`` (корень кода) и ``--db-file`` (БД
состояния), поэтому раскладка не зависит от cwd: относительные ``file_dep``
резолвятся от корня кода, а БД лежит в каталоге состояния.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys

from .config import Layout

CHANGED = re.compile(r"The following file dependencies have changed:\s*\n((?:\s*-\s*.+\n?)+)")
MISSING = re.compile(r"The following file dependencies are missing:\s*\n((?:\s*-\s*.+\n?)+)")


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


def _relative(root: pathlib.Path, raw: str) -> str:
    text = raw.strip().strip("-").strip()
    path = pathlib.Path(text)
    if not path.is_absolute():
        path = root / path
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return path.as_posix()


def _listed(pattern: re.Pattern[str], output: str, root: pathlib.Path) -> list[str] | None:
    match = pattern.search(output)
    if not match:
        return None
    items = [line.strip(" -") for line in match.group(1).splitlines() if line.strip()]
    return [_relative(root, item) for item in items]


def acceptance_status(layout: Layout, shard: str) -> tuple[str, str]:
    """(up-to-date | run | error | unknown | no-doit | no-dodo, подробность)."""
    if not layout.dodo.is_file():
        return "no-dodo", "нет dodo-файла: " + _relative(layout.root, str(layout.dodo))
    executable = doit_executable(layout)
    if executable is None:
        return "no-doit", "doit не найден: установите его в окружение plan-ledger"
    result = subprocess.run(
        [
            executable,
            "-f",
            str(layout.dodo),
            "-d",
            str(layout.root),
            "info",
            "--db-file",
            str(layout.db),
            shard,
        ],
        cwd=layout.root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
    )
    output = (result.stdout or "") + (result.stderr or "")
    if "up-to-date" in output:
        return "up-to-date", ""
    missing = _listed(MISSING, output, layout.root)
    if missing is not None:
        return "error", "не найдены file_dep: " + ", ".join(missing)
    changed = _listed(CHANGED, output, layout.root)
    if changed is not None:
        return "run", "изменились: " + ", ".join(changed)
    if re.search(r"Unknown task|Task not found|Invalid parameter", output, re.I):
        return "unknown", f"приёмка '{shard}' не найдена в {_relative(layout.root, str(layout.dodo))}"
    if result.returncode != 0:
        tail = " ".join(output.split())[-200:]
        return "error", tail or f"doit завершился с кодом {result.returncode}"
    return "run", ""
