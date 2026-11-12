"""Обнаружение шардов приёмки в dodo.py.

Основной путь — ``doit list``: он учитывает и задачи, созданные динамически.
Если doit недоступен или dodo падает, читаем имена функций ``task_*`` прямо
из исходника: этого достаточно для обычных dodo-файлов.
"""

from __future__ import annotations

import ast

from .config import Layout
from .doit_cli import run as run_doit


def declared_from_doit(layout: Layout) -> list[str] | None:
    """Шарды через `doit list`; None, если doit не смог прочитать dodo."""
    result = run_doit(layout, "list")
    if result.returncode != 0:
        return None
    names: list[str] = []
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if line:
            names.append(line.split()[0].rstrip(":"))
    return names or None


def declared_from_source(layout: Layout) -> list[str]:
    """Fallback: имена функций `task_*` из dodo.py, без запуска doit."""
    tree = ast.parse(layout.dodo.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
            "task_"
        ):
            names.append(node.name[len("task_") :])
    return names


def declared(layout: Layout) -> tuple[list[str], str]:
    """(имена шардов, источник: `doit` | `ast`)."""
    names = declared_from_doit(layout)
    if names is not None:
        return names, "doit"
    return declared_from_source(layout), "ast"
