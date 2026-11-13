"""Статус приёмки шарда через doit.

doit вызывается с явными ``-f`` (dodo), ``-d`` (корень кода) и ``--db-file`` (БД
состояния), поэтому раскладка не зависит от cwd: относительные ``file_dep``
резолвятся от корня кода, а БД лежит в каталоге состояния.
"""

from __future__ import annotations

import os
import pathlib
import re

from .config import Layout
from .doit_cli import doit_executable, run as run_doit

CHANGED = re.compile(r"The following file dependencies have changed:\s*\n((?:\s*-\s*.+\n?)+)")
MISSING = re.compile(r"The following file dependencies are missing:\s*\n((?:\s*-\s*.+\n?)+)")
TRACEBACK = re.compile(r"Traceback \(most recent call last\)")
EXCEPTION = re.compile(r"^([A-Za-z_][\w.]*(?:Error|Exception)):\s*(.+)$", re.M)
DEFAULT_MAX_LISTED = 10


def _max_listed() -> int:
    try:
        return max(1, int(os.environ.get("PLAN_LEDGER_MAX_LISTED", DEFAULT_MAX_LISTED)))
    except ValueError:
        return DEFAULT_MAX_LISTED


def _relative(root: pathlib.Path, raw: str) -> str:
    text = raw.strip().strip("-").strip()
    path = pathlib.Path(text)
    if not path.is_absolute():
        path = root / path
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return path.as_posix()


def _listed(
    pattern: re.Pattern[str], output: str, root: pathlib.Path, label: str
) -> str | None:
    match = pattern.search(output)
    if not match:
        return None
    raw_items = [line.strip(" -") for line in match.group(1).splitlines() if line.strip()]
    items = [_relative(root, item) for item in raw_items]
    limit = _max_listed()
    shown = ", ".join(items[:limit])
    if len(items) > limit:
        shown += f" … and {len(items) - limit} more"
    return f"{label}: {shown}"


def _error_line(output: str) -> str:
    """Одна строка ошибки вместо хвоста трассировки."""
    exceptions = EXCEPTION.findall(output)
    if exceptions:
        kind, message = exceptions[-1]
        return f"{kind}: {message}"[:200]
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    for line in reversed(lines):
        if line.upper().startswith("ERROR:"):
            return line[:200]
    return lines[-1][:200] if lines else ""


COMPACT_LISTED = 3


def compact_detail(detail: str, limit: int = COMPACT_LISTED) -> str:
    """Сжать список путей в диагностике: ``changed: a.py, b.py (+343 more)``.

    Полный список остаётся в ``acceptance_status`` — сжатие нужно только
    представлению (plan-status/plan-check), а не самому факту.
    """
    prefix, sep, rest = detail.partition(": ")
    if not sep or not rest:
        return detail
    tail = 0
    match = re.search(r"\s*… and (\d+) more$", rest)
    if match:
        rest = rest[: match.start()]
        tail = int(match.group(1))
    items = [item for item in rest.split(", ") if item.strip()]
    text = f"{prefix}: " + ", ".join(items[:limit])
    hidden = len(items) + tail - len(items[:limit])
    if hidden > 0:
        text += f" (+{hidden} more)"
    return text


_BATCH_CODES = {"U": "up-to-date", "R": "run", "E": "error"}
_STATUS_LINE = re.compile(r"^([A-Z])\s+(\S+)\s*$")
_CACHE: dict[tuple[str, str, int, str], tuple[str, str]] = {}
_BATCH: dict[tuple[str, str, int], dict[str, str] | None] = {}


def clear_cache() -> None:
    """Забыть закэшированные состояния (тесты и долгоживущие процессы)."""
    _CACHE.clear()
    _BATCH.clear()


def _db_stamp(path: pathlib.Path) -> int:
    """Версия БД: правка doit-базы (plan-run) сбрасывает кэш этого шарда.

    doit хранит состояние не одним файлом (``dbm``: ``.doit.db.dat``,
    ``.doit.db.dir``, ``.doit.db.bak``), поэтому берём максимум mtime по
    артефактам ``<db>*``; отсутствие БД — версия 0.
    """
    stamp = 0
    candidates = [path]
    try:
        candidates.extend(path.parent.glob(path.name + "*"))
    except OSError:  # pragma: no cover - нечитаемый каталог состояния
        pass
    for candidate in candidates:
        try:
            stamp = max(stamp, candidate.stat().st_mtime_ns)
        except OSError:
            continue
    return stamp


def _scope(layout: Layout) -> tuple[str, str, int]:
    return (str(layout.dodo), str(layout.db), _db_stamp(layout.db))


def _batch_states(layout: Layout) -> dict[str, str] | None:
    """Все статусы шардов одним ``doit list --status``; None, если так нельзя.

    ``doit info`` принимает ровно один шард, ``list --status`` печатает U/R/E
    для всего ``dodo.py`` за один процесс. План из тридцати шардов стоит один
    вызов, а ``info`` остаётся только для шардов, которым нужна подробность.
    """
    key = _scope(layout)
    if key in _BATCH:
        return _BATCH[key]
    states: dict[str, str] | None = None
    if layout.dodo.is_file() and doit_executable(layout) is not None:
        result = run_doit(layout, "list", "--status")
        if result.returncode == 0:
            parsed: dict[str, str] = {}
            for line in (result.stdout or "").splitlines():
                match = _STATUS_LINE.match(line.strip())
                if match and match.group(1) in _BATCH_CODES:
                    parsed[match.group(2)] = _BATCH_CODES[match.group(1)]
            states = parsed or None
    _BATCH[key] = states
    return states


def _info(layout: Layout, shard: str) -> tuple[str, str]:
    key = (*_scope(layout), shard)
    if key not in _CACHE:
        _CACHE[key] = _acceptance_status(layout, shard)
    return _CACHE[key]


def acceptance_state(layout: Layout, shard: str) -> str:
    """Состояние шарда без подробности: из батча, иначе из ``doit info``."""
    if not layout.dodo.is_file():
        return "no-dodo"
    if doit_executable(layout) is None:
        return "no-doit"
    states = _batch_states(layout)
    if states is not None and shard in states:
        return states[shard]
    return _info(layout, shard)[0]


def acceptance_detail(layout: Layout, shard: str) -> str:
    """Подробность (``changed: …``) через ``doit info``; кэшируется с состоянием."""
    return _info(layout, shard)[1]


def acceptance_states(layout: Layout) -> dict[str, str] | None:
    """Все состояния шардов одним батчем; None, если ``doit list --status`` недоступен."""
    if not layout.dodo.is_file() or doit_executable(layout) is None:
        return None
    return _batch_states(layout)


def acceptance_status(layout: Layout, shard: str) -> tuple[str, str]:
    """(up-to-date | run | error | unknown | no-doit | no-dodo, подробность).

    Совместимый вход: ``up-to-date`` разрешается из батча без ``doit info``;
    для остальных состояний вызывается ``info``, потому что подробность —
    единственное, что даёт именно он.
    """
    state = acceptance_state(layout, shard)
    if state == "up-to-date":
        return "up-to-date", ""
    return _info(layout, shard)


def _acceptance_status(layout: Layout, shard: str) -> tuple[str, str]:
    if not layout.dodo.is_file():
        return "no-dodo", "no dodo file: " + _relative(layout.root, str(layout.dodo))
    if doit_executable(layout) is None:
        return "no-doit", "doit not found: install it into the plan-ledger environment"
    result = run_doit(layout, "info", shard)
    output = (result.stdout or "") + (result.stderr or "")
    if "up-to-date" in output:
        return "up-to-date", ""
    missing = _listed(MISSING, output, layout.root, "missing file_dep")
    if missing is not None:
        return "error", missing
    changed = _listed(CHANGED, output, layout.root, "changed")
    if changed is not None:
        return "run", changed
    where = _relative(layout.root, str(layout.dodo))
    if re.search(r"Unknown task|Task not found|Invalid parameter", output, re.I):
        return "unknown", f"acceptance '{shard}' not found in {where}"
    if result.returncode != 0:
        detail = _error_line(output) or f"doit exited with code {result.returncode}"
        exceptions = EXCEPTION.findall(output)
        if TRACEBACK.search(output) and exceptions and exceptions[-1][0] == "KeyError":
            if shard.strip("'\"") in exceptions[-1][1]:
                return "unknown", f"acceptance '{shard}' is missing from {where}: {detail}"
        return "error", f"doit: {detail}"
    return "run", ""
