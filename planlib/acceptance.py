"""Статус приёмки шарда через doit: up-to-date | run | unknown | no-doit."""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess

CHANGED = re.compile(r"The following file dependencies have changed:\s*\n((?:\s*-\s*.+\n?)+)")


def doit_executable(project: pathlib.Path) -> str | None:
    candidates = [
        project / ".venv" / "Scripts" / "doit.exe",
        project / ".venv" / "bin" / "doit",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return shutil.which("doit")


def acceptance_status(project: pathlib.Path, shard: str) -> tuple[str, str]:
    """Возвращает (состояние, подробность) для задачи doit с именем шарда."""
    executable = doit_executable(project)
    if executable is None:
        return "no-doit", "doit не установлен в этом проекте"
    result = subprocess.run(
        [executable, "info", shard],
        cwd=project,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = result.stdout
    if "up-to-date" in output:
        return "up-to-date", ""
    changed = CHANGED.search(output)
    if changed:
        files = [line.strip(" -") for line in changed.group(1).splitlines() if line.strip()]
        return "run", "изменились: " + ", ".join(files)
    if "Task not found" in output or result.returncode != 0 and not output.strip():
        return "unknown", f"приёмка '{shard}' не найдена в dodo.py"
    return "run", ""
