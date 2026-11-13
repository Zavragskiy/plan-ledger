"""Один вердикт для plan-status и plan-check.

``stale`` — только ``Done``-задача с неподтверждённой приёмкой. Открытая
задача с изменившимися входами не «сломана»: приёмка у неё ещё не
подтверждалась, поэтому она ``open`` с пометкой «not confirmed».
"""

from __future__ import annotations

from .acceptance import compact_detail
from .model import Task

VERDICTS = ("ok", "stale", "incomplete", "unverified", "open")
ERROR_STATES = {"error", "no-doit", "no-dodo"}


def classify(task: Task, acceptance: str) -> str:
    """Вердикт задачи по её статусу и состоянию приёмки шарда."""
    if task.status != "Done":
        return "open"
    if task.criteria["total"] and task.unchecked():
        return "incomplete"
    if acceptance == "up-to-date":
        return "ok"
    if acceptance == "no-acceptance":
        return "unverified"
    return "stale"


def detail_for(
    task: Task,
    acceptance: str,
    acceptance_detail: str,
    verdict: str,
    with_detail: bool = False,
) -> str | None:
    """Подробность по бюджету: полный список путей или первые три.

    ``None`` — вердикту подробность не нужна (открытая задача без ошибки
    окружения); представление печатает такую строку без диагностики.
    """
    shown = acceptance_detail if with_detail else compact_detail(acceptance_detail or "")
    if verdict == "incomplete":
        numbers = ", ".join(str(number) for number in task.unchecked())
        text = f"unchecked criteria: {numbers}"
        if acceptance != "up-to-date":
            text += f"; acceptance {acceptance}"
            if shown:
                text += f" ({shown})"
        return text
    if verdict in {"stale", "unverified"}:
        return shown or None
    if verdict == "ok":
        return None
    # open: ошибка окружения — диагностика, «изменились входы» — шум.
    if with_detail or acceptance in ERROR_STATES:
        return shown or None
    return None
