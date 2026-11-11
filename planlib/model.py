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
        done, text = self.acceptance[index - 1]
        self.acceptance[index - 1] = (True, text)

    def uncheck(self, index: int) -> None:
        done, text = self.acceptance[index - 1]
        self.acceptance[index - 1] = (False, text)

    def to_markdown(self) -> str:
        meta: dict[str, object] = {"id": self.id, "title": self.title, "status": self.status}
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


def parse(path: pathlib.Path) -> Task:
    text = path.read_text(encoding="utf-8")
    match = FRONT_MATTER.match(text)
    if not match:
        raise ValueError(f"{path}: нет YAML frontmatter")
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
        if task.id.lower() in {wanted, f"task-{wanted.removeprefix('task-')}"}:
            return task
    raise SystemExit(f"задача {task_id} не найдена в {pathlib.Path(tasks)}")


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
    if getattr(task, "path", None) and pathlib.Path(task.path).exists():
        path = pathlib.Path(task.path)
    else:
        path = root / f"{task.id.lower()} - {slugify(task.title)}.md"
        task.path = path  # type: ignore[attr-defined]
    path.write_text(task.to_markdown(), encoding="utf-8")
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
) -> Task:
    task = Task(
        id=next_id(tasks),
        title=title,
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
