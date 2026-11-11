"""Импорт существующих планов в задачи плана.

Поддерживает два распространённых формата:
  roadmap  — `## Phase N: … — DONE` с зависимостями и acceptance criteria
  numbered — `**Статус:**`, `**Приоритет:**`, `**Зависимости:**`, разделы «Что сделать»

По умолчанию dry-run; с --apply создаёт задачи через planlib.model.
"""

from __future__ import annotations

import argparse
import pathlib
import re
from dataclasses import dataclass, field

PHASE = re.compile(r"^(#{2,3})[ \t]+Phase[ \t]+(\d+)[ \t]*[:—–-][ \t]*(.+?)[ \t]*$", re.M)
STATUS_WORD = re.compile(r"^(done|pending|planned|todo|not started|in progress)\b", re.I)
SECTIONS = ("tasks", "dependencies", "acceptance criteria", "references", "status")
AC = re.compile(r"^\s*[-*]\s+\[(x|X| )\]\s+(.+)$", re.M)
BULLET = re.compile(r"^\s*[-*]\s+(?!\[[ xX]\])\s*(.+)$", re.M)
NUMBERED = re.compile(r"^\d+\.\s+(?:\*\*)?(.+?)(?:\*\*)?\s*(?:[—–-]\s*(DONE))?\s*$", re.M)


@dataclass
class Imported:
    key: str
    title: str
    status: str
    steps: list[str] = field(default_factory=list)
    acceptance: list[str] = field(default_factory=list)
    deps: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    priority: str | None = None
    source: str = ""


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _section(block: str, name: str) -> str:
    pattern = re.compile(rf"^###\s+{re.escape(name)}\s*$(.*?)(?=^###\s|\Z)", re.M | re.S | re.I)
    match = pattern.search(block)
    return match.group(1) if match else ""


def _numbered_titles(text: str) -> list[str]:
    return [_clean(match.group(1)) for match in NUMBERED.finditer(text)]


def _peel_status(title: str) -> tuple[str, str | None]:
    """Отделяет хвостовой статус заголовка: 'Phase 3 — UI — in progress'."""
    parts = re.split(r"\s+[—–]\s+|\s+-\s+", title)
    if len(parts) > 1:
        word = parts[-1].strip().lower()
        match = STATUS_WORD.match(word)
        if match:
            status = (
                "Done"
                if match.group(1).lower() == "done"
                else ("In Progress" if "progress" in word else "To Do")
            )
            return " — ".join(parts[:-1]).strip(), status
    return title.strip(), None


def _status_from(block: str, acceptance: list[str], checked: int, header_done: bool) -> str:
    if header_done:
        return "Done"
    explicit = re.search(r"\*\*(?:Status|Статус)[^*]*\*\*\s*:?\s*(.+?)(?:\n|$)", block, re.I)
    if explicit:
        value = explicit.group(1).strip().lower()
        if value.startswith("done") or "выполн" in value or "✅" in value:
            return "Done"
        if "progress" in value or "работе" in value or "started" in value:
            return "In Progress"
    if acceptance:
        return "Done" if checked == len(acceptance) else ("In Progress" if checked else "To Do")
    return "To Do"


def parse_roadmap(path: pathlib.Path) -> list[Imported]:
    text = path.read_text(encoding="utf-8")
    headers = list(PHASE.finditer(text))
    items: list[Imported] = []
    for index, match in enumerate(headers):
        start = match.end()
        end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        block = text[start:end]
        title, header_status = _peel_status(_clean(match.group(3)))
        tasks_text = _section(block, "Tasks")
        steps = _numbered_titles(tasks_text or block)
        if not steps:
            steps = [_clean(match.group(1)) for match in BULLET.finditer(tasks_text or block)]
        steps = [re.sub(r"\s*[—–-]\s*DONE\s*$", "", step, flags=re.I) for step in steps]
        acceptance = [_clean(item[1]) for item in AC.findall(block)]
        checked = sum(1 for item in AC.findall(block) if item[0].lower() == "x")
        deps_text = _section(block, "Dependencies")
        deps = sorted(set(re.findall(r"Phases?\s+(\d+)", deps_text)))
        if len(deps) == 1 and re.search(r"Phases\s+(\d+)–(\d+)", deps_text):
            low, high = re.search(r"Phases\s+(\d+)–(\d+)", deps_text).groups()
            deps = [str(number) for number in range(int(low), int(high) + 1)]
        status = header_status or _status_from(block, acceptance, checked, False)
        items.append(
            Imported(
                key=match.group(2),
                title=f"Phase {match.group(2)}: {title}",
                status=status,
                steps=steps,
                acceptance=acceptance,
                deps=deps,
                labels=[f"phase:{match.group(2)}", "migrated"],
                source=str(path),
            )
        )
    return items


def parse_numbered(path: pathlib.Path) -> list[Imported]:
    text = path.read_text(encoding="utf-8")
    heading = re.search(r"^#\s+(.+)$", text, re.M)
    title = _clean(heading.group(1)) if heading else path.stem
    title = re.sub(r"^(Задача|Task)\s*:\s*", "", title, flags=re.I)
    status = _status_from(text, [], 0, False)
    priority_raw = re.search(r"\*\*Приоритет[:\*]*\*?\*?\s*:?\s*\*?\*?(.+?)(?:\n|$)", text)
    priority = None
    if priority_raw:
        value = priority_raw.group(1).strip().lower()
        priority = {"высокий": "high", "средний": "medium", "низкий": "low"}.get(value, value)
    steps_block = re.search(r"##\s+Что сделать\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    steps = _numbered_titles(steps_block.group(1)) if steps_block else []
    acceptance_block = re.search(r"##\s+Критери[йи]\s+готовности\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    acceptance = []
    if acceptance_block:
        block_text = acceptance_block.group(1)
        fences = [" ".join(fence.split()) for fence in re.findall(r"```(?:\w+)?\n(.*?)```", block_text, re.S)]
        rest = _clean(re.sub(r"```.*?```", "", block_text, flags=re.S))
        parts = [part for part in [*fences, rest] if part]
        if parts:
            acceptance = [" — ".join(parts)[:300]]
    deps_raw = re.search(r"\*\*Зависимости[:\*]*\*?\*?\s*:?\s*\*?\*?(.+?)(?:\n|$)", text)
    deps: list[str] = []
    if deps_raw and deps_raw.group(1).strip().lower() not in {"нет", "none", "—", "-"}:
        deps = [_clean(item) for item in re.split(r"[,;]", deps_raw.group(1)) if _clean(item)]
    return [
        Imported(
            key=path.stem,
            title=title,
            status=status,
            steps=steps,
            acceptance=acceptance,
            deps=[],
            labels=["migrated", f"src:{path.parent.name}"],
            priority=priority,
            source=str(path),
        )
    ]


def parse(path: pathlib.Path) -> tuple[str, list[Imported]]:
    text = path.read_text(encoding="utf-8")
    if PHASE.search(text):
        return "roadmap", parse_roadmap(path)
    if re.search(r"\*\*Статус[:\*]", text):
        return "numbered", parse_numbered(path)
    raise SystemExit(f"неизвестный формат: {path} (нет '## Phase N' и нет '**Статус:**')")


def description_for(item: Imported) -> str:
    lines = [f"Импортировано из {pathlib.Path(item.source).name}."]
    if item.steps:
        lines.append("")
        lines.append("Шаги:")
        lines.extend(f"{number}. {step}" for number, step in enumerate(item.steps, 1))
    return "\n".join(lines)


def write_task(project: pathlib.Path, item: Imported) -> str:
    from planlib import model

    task = model.create(
        project,
        title=item.title,
        description=description_for(item),
        status=item.status,
        labels=item.labels,
        acceptance=item.acceptance,
        priority=item.priority,
        references=[item.source],
    )
    print(f"  + {task.id} [{item.status}] {item.title}")
    return task.id


def link_dependencies(project: pathlib.Path, task_id: str, dependencies: list[str]) -> None:
    from planlib import model

    task = model.find(project, task_id)
    task.dependencies = dependencies
    model.save(task, project)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=pathlib.Path, help="путь к roadmap или numbered-плану")
    parser.add_argument("--project", type=pathlib.Path, required=True, help="каталог backlog-проекта")
    parser.add_argument("--apply", action="store_true", help="создать задачи (иначе dry-run)")
    args = parser.parse_args(argv)

    fmt, items = parse(args.source)
    print(f"формат: {fmt}; найдено единиц: {len(items)}")
    for item in items:
        print(f"  - [{item.status}] {item.title} (шагов {len(item.steps)}, AC {len(item.acceptance)}, deps {item.deps})")
    if not args.apply:
        print("\ndry-run: ничего не создано. Повторите с --apply.")
        return 0

    created: dict[str, str] = {}
    for item in items:
        created[item.key] = write_task(args.project, item)
    for item in items:
        dependencies = [created[dep] for dep in item.deps if dep in created]
        if dependencies:
            link_dependencies(args.project, created[item.key], dependencies)
    print(f"\nсоздано задач: {len(created)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
