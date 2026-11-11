"""Совместимость импорта: задача, загрузка, готовность (реализация в planlib.model)."""

from .model import (
    STATUSES,
    Task,
    create,
    find,
    load_tasks,
    next_id,
    parse,
    project_root,
    ready,
    save,
    slugify,
    tasks_dir,
)

__all__ = [
    "STATUSES",
    "Task",
    "create",
    "find",
    "load_tasks",
    "next_id",
    "parse",
    "project_root",
    "ready",
    "save",
    "slugify",
    "tasks_dir",
]
