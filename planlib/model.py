"""Модель задачи: markdown + YAML frontmatter, совместимая с файлами backlog.md.

Формат нарочно простой и стабильный: frontmatter несёт машинное состояние,
тело — человеческий текст. Читатель терпит HTML-маркеры секций backlog.md,
писатель их не создаёт.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import re
from dataclasses import dataclass, field

import yaml

STATUSES = ("To Do", "In Progress", "Blocked", "Done")
FRONT_MATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
SECTION = re.compile(r"^##\s+(.+?)\s*$", re.M)
AC_ITEM = re.compile(r"^\s*[-*]\s+\[(x|X| )\]\s*(?:#\d+)?\s*(.*)$", re.M)

TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
    "я": "ya",
}


@dataclass
class Task:
    id: str
    title: str
    slug: str | None = None
    status: str = STATUSES[0]
    labels: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    priority: str | None = None
    owner: str | None = None
    created: str = ""
    updated: str = ""
    references: list[str] = field(default_factory=list)
    description: str = ""
    plan: str = ""
    notes: list[str] = field(default_factory=list)
    acceptance: list[tuple[bool, str]] = field(default_factory=list)
    extra_sections: list[tuple[str, str]] = field(default_factory=list)

    @property
    def shard(self) -> str | None:
        for label in self.labels:
            if label.startswith("shard:"):
                return label.split(":", 1)[1]
        return None

    def check(self, index: int) -> None:
        self._validate_index(index)
        done, text = self.acceptance[index - 1]
        self.acceptance[index - 1] = (True, text)

    def uncheck(self, index: int) -> None:
        self._validate_index(index)
        done, text = self.acceptance[index - 1]
        self.acceptance[index - 1] = (False, text)

    def _validate_index(self, index: int) -> None:
        if not 1 <= index <= len(self.acceptance):
            raise ValueError(
                f"acceptance criterion #{index} does not exist: "
                f"the task has {len(self.acceptance)}"
            )

    @property
    def criteria(self) -> dict[str, int]:
        return {
            "checked": sum(1 for done, _ in self.acceptance if done),
            "total": len(self.acceptance),
        }

    def unchecked(self) -> list[int]:
        return [number for number, (done, _) in enumerate(self.acceptance, 1) if not done]

    def to_markdown(self) -> str:
        meta: dict[str, object] = {"id": self.id, "title": self.title, "status": self.status}
        if self.slug:
            meta["slug"] = self.slug
        if self.priority:
            meta["priority"] = self.priority
        if self.owner:
            meta["owner"] = self.owner
        if self.labels:
            meta["labels"] = list(self.labels)
        if self.dependencies:
            meta["dependencies"] = list(self.dependencies)
        if self.references:
            meta["references"] = list(self.references)
        meta["created_date"] = self.created or _now()
        meta["updated_date"] = self.updated or _now()
        front = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
        parts = [f"---\n{front}\n---\n"]
        if self.description:
            parts.append(f"## Description\n\n{self.description.strip()}\n")
        if self.plan:
            parts.append(f"## Implementation Plan\n\n{self.plan.strip()}\n")
        if self.acceptance:
            lines = [
                f"- [{'x' if done else ' '}] #{number} {text}".rstrip()
                for number, (done, text) in enumerate(self.acceptance, 1)
            ]
            parts.append("## Acceptance Criteria\n\n" + "\n".join(lines) + "\n")
        if self.notes:
            parts.append("## Notes\n\n" + "\n".join(f"- {note}" for note in self.notes) + "\n")
        for title, chunk in self.extra_sections:
            parts.append(f"## {title}\n\n{chunk.strip()}\n")
        return "\n".join(parts)


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def slugify(title: str) -> str:
    text = "".join(TRANSLIT.get(char, char) for char in title.lower())
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return "-".join(text.split("-")[:6]) or "task"


TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
TASK_SLUG = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def validate_id(task_id: str) -> str:
    if not TASK_ID.fullmatch(task_id):
        raise ValueError(
            f"id {task_id!r}: ASCII letters, digits, '.', '_' and '-' are allowed; "
            "the first character must be a letter or a digit"
        )
    return task_id


def validate_slug(slug: str) -> str:
    if not TASK_SLUG.fullmatch(slug):
        raise ValueError(
            f"slug {slug!r}: lowercase ASCII letters, digits, '.', '_' and '-' are allowed"
        )
    return slug


def file_name(task: Task) -> str:
    """Имя файла задачи: явный slug — это имя целиком, иначе legacy `id - title`."""
    if task.slug:
        return f"{task.slug}.md"
    return f"{task.id.lower()} - {slugify(task.title)}.md"


def parse(path: pathlib.Path) -> Task:
    text = path.read_text(encoding="utf-8")
    match = FRONT_MATTER.match(text)
    if not match:
        raise ValueError(f"{path}: no YAML frontmatter")
    meta = yaml.safe_load(match.group(1)) or {}
    body = HTML_COMMENT.sub("", text[match.end() :])
    description, plan, notes = "", "", []
    acceptance: list[tuple[bool, str]] = []
    extra: list[tuple[str, str]] = []
    headers = list(SECTION.finditer(body))
    for index, header in enumerate(headers):
        name = header.group(1).strip().lower()
        end = headers[index + 1].start() if index + 1 < len(headers) else len(body)
        chunk = body[header.end() : end].strip()
        if name == "description":
            description = chunk
        elif name == "implementation plan":
            plan = chunk
        elif name == "acceptance criteria":
            acceptance = [(flag.lower() == "x", text.strip()) for flag, text in AC_ITEM.findall(chunk)]
        elif name in {"notes", "implementation notes"}:
            notes = [line.lstrip("-* ").strip() for line in chunk.splitlines() if line.strip()]
        else:
            extra.append((header.group(1).strip(), chunk))
    return Task(
        id=str(meta.get("id", "")),
        title=str(meta.get("title", "")).strip(),
        slug=str(meta["slug"]).strip() if meta.get("slug") else None,
        status=str(meta.get("status", STATUSES[0])),
        labels=[str(item) for item in (meta.get("labels") or [])],
        dependencies=[str(item) for item in (meta.get("dependencies") or [])],
        priority=meta.get("priority"),
        owner=meta.get("owner"),
        created=str(meta.get("created_date", "")),
        updated=str(meta.get("updated_date", "")),
        references=[str(item) for item in (meta.get("references") or [])],
        description=description,
        plan=plan,
        notes=notes,
        acceptance=acceptance,
        extra_sections=extra,
    )


def load_tasks(tasks: pathlib.Path) -> list[Task]:
    """Задачи из каталога задач (обычно ``<state>/backlog/tasks``)."""
    tasks = pathlib.Path(tasks)
    loaded: list[Task] = []
    if not tasks.is_dir():
        return loaded
    for path in sorted(tasks.glob("*.md")):
        try:
            task = parse(path)
        except ValueError:
            continue
        task.path = path  # type: ignore[attr-defined]
        loaded.append(task)
    return loaded


def find(tasks: pathlib.Path, task_id: str) -> Task:
    wanted = task_id.lower()
    for task in load_tasks(tasks):
        by_id = task.id.lower() in {wanted, f"task-{wanted.removeprefix('task-')}"}
        by_slug = bool(task.slug) and task.slug.lower() == wanted
        if by_id or by_slug:
            return task
    raise SystemExit(f"task {task_id} not found in {pathlib.Path(tasks)}")


def next_id(tasks: pathlib.Path) -> str:
    highest = 0
    for task in load_tasks(tasks):
        match = re.fullmatch(r"TASK-(\d+)", task.id, re.I)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"TASK-{highest + 1}"


def save(task: Task, tasks: pathlib.Path) -> pathlib.Path:
    root = pathlib.Path(tasks)
    root.mkdir(parents=True, exist_ok=True)
    task.updated = _now()
    existing = pathlib.Path(task.path) if getattr(task, "path", None) else None
    if existing is not None and existing.exists() and not task.slug:
        # Без явного slug файл не переименовывается: правка заголовка не должна
        # плодить diff «удалил/добавил».
        path = existing
    else:
        path = root / file_name(task)
    if existing is not None and existing.exists() and path.resolve() != existing.resolve():
        if path.exists():
            raise ValueError(f"file {path.name} is already used by another task")
        path.write_text(task.to_markdown(), encoding="utf-8")
        existing.unlink()
    else:
        if existing is None and path.exists():
            raise ValueError(f"file {path.name} already exists")
        path.write_text(task.to_markdown(), encoding="utf-8")
    task.path = path  # type: ignore[attr-defined]
    return path


def create(
    tasks: pathlib.Path,
    title: str,
    description: str = "",
    status: str = STATUSES[0],
    labels: list[str] | None = None,
    dependencies: list[str] | None = None,
    acceptance: list[str] | None = None,
    priority: str | None = None,
    owner: str | None = None,
    references: list[str] | None = None,
    check_first: bool | None = None,
    task_id: str | None = None,
    slug: str | None = None,
) -> Task:
    if task_id is not None:
        validate_id(task_id)
        if any(item.id.lower() == task_id.lower() for item in load_tasks(tasks)):
            raise ValueError(f"a task with id {task_id} already exists")
    if slug is not None:
        validate_slug(slug)
        if (pathlib.Path(tasks) / f"{slug}.md").exists():
            raise ValueError(f"file {slug}.md already exists")
    task = Task(
        id=task_id or next_id(tasks),
        title=title,
        slug=slug,
        status=status,
        labels=list(labels or []),
        dependencies=list(dependencies or []),
        priority=priority,
        owner=owner,
        created=_now(),
        references=list(references or []),
        description=description,
        acceptance=[(False, item) for item in (acceptance or [])],
    )
    save(task, tasks)
    return task


def ready(task: Task, by_id: dict[str, Task]) -> bool:
    if task.status == "Blocked":
        return False
    for dep in task.dependencies:
        other = by_id.get(dep)
        if other is None or other.status != "Done":
            return False
    return True


PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
STATUS_ORDER = {"In Progress": 0, "To Do": 1, "Blocked": 1, "Done": 2}
_NUMERIC_ID = re.compile(r"([A-Za-z]+)-(\d+)")


def _id_key(task_id: str) -> tuple[int, str, int]:
    match = _NUMERIC_ID.fullmatch(task_id)
    if match:
        return (0, match.group(1).upper(), int(match.group(2)))
    return (1, task_id.upper(), 0)


def sort_key(task: Task) -> tuple[int, int, tuple[int, str, int]]:
    """Порядок отображения: In Progress, приоритет, натуральный id.

    ``TASK-8`` идёт раньше ``TASK-13`` (числовое сравнение), ``TASK-1000`` —
    после ``TASK-13``. Один ключ для plan-status, plan-task list и digest.
    """
    return (
        STATUS_ORDER.get(task.status, 1),
        PRIORITY_ORDER.get((task.priority or "").lower(), 3),
        _id_key(task.id),
    )
