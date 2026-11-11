"""Совместимость импорта: модель задачи и её загрузка (реализация в planlib.model)."""

from .model import (
    STATUSES,
    Task,
    create,
    find,
    load_tasks,
    next_id,
    parse,
    ready,
    save,
    slugify,
)

__all__ = [
    "STATUSES",
    "Task",
    "create",
    "find",
    "load_tasks",
    "next_id",
    "parse",
    "ready",
    "save",
    "slugify",
]
