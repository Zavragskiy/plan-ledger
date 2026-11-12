"""Импорт существующих планов и находок гейта в задачи плана.

Поддерживает три формата:
  roadmap  — `## Phase N: … — DONE` с зависимостями и acceptance criteria
  numbered — `**Статус:**`, `**Приоритет:**`, `**Зависимости:**`, разделы «Что сделать»
  json     — `--from-json findings.json`: машиночитаемый список находок (lizard/xenon,
             сложностной гейт), одна задача на находку или на файл/правило

JSON: список объектов или `{"shard": "gate", "findings": [...]}`;
поля находки — `title`, `message`, `rule`, `file`, `line`, `description`,
`acceptance` (список), `labels`, `priority`, `id`, `slug`, `reference`.

По умолчанию dry-run; с --apply создаёт задачи через planlib.model.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
from dataclasses import dataclass, field

from planlib import load_tasks
from planlib.config import LayoutError, layout_arguments_parent, layout_from_args
from planlib.console import enable_utf8

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
    task_id: str | None = None
    slug: str | None = None
    body: str = ""
    references: list[str] = field(default_factory=list)


class JsonImportError(RuntimeError):
    """Некорректный JSON-отчёт: CLI печатает сообщение и выходит с кодом 3."""


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


JSON_LIST_KEYS = ("findings", "issues", "items", "tasks")
JSON_PRIORITIES = {"high", "medium", "low"}
JSON_GROUPINGS = ("none", "file", "rule")


def _plural(count: int, one: str, few: str, many: str) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return one
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return few
    return many


def _text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    return "" if value is None else str(value).strip()


def _texts(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def load_findings(path: pathlib.Path) -> tuple[list[dict], dict]:
    """Список находок + метаданные обёртки (`shard`, `labels`)."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        raise JsonImportError(f"{path}: не удалось прочитать ({error})") from error
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        raise JsonImportError(f"{path}: некорректный JSON ({error})") from error
    meta: dict = {}
    if isinstance(data, dict):
        for key in JSON_LIST_KEYS:
            if isinstance(data.get(key), list):
                meta = {name: value for name, value in data.items() if name != key}
                data = data[key]
                break
        else:
            data = [data]
    if not isinstance(data, list):
        raise JsonImportError(f"{path}: ожидался список находок или объект с 'findings'")
    for number, item in enumerate(data, 1):
        if not isinstance(item, dict):
            raise JsonImportError(f"{path}: находка #{number} — не объект")
    return data, meta


def _finding_file(item: dict) -> str:
    return _text(item.get("file") or item.get("path") or item.get("source"))


def _finding_line(item: dict) -> str:
    return _text(item.get("line") or item.get("lineno") or item.get("row"))


def _finding_rule(item: dict) -> str:
    return _text(item.get("rule") or item.get("check") or item.get("code") or item.get("kind"))


def _finding_message(item: dict) -> str:
    return _text(item.get("message") or item.get("detail") or item.get("text"))


def _where(item: dict) -> str:
    file = _finding_file(item)
    line = _finding_line(item)
    if file and line:
        return f"{file}:{line}"
    return file


def finding_reference(item: dict) -> str:
    explicit = _text(item.get("reference"))
    if explicit:
        return explicit
    where = _where(item)
    if where:
        return where
    rule = _finding_rule(item)
    return rule or _clean(_finding_message(item)) or "находка"


def finding_title(item: dict) -> str:
    title = _text(item.get("title") or item.get("name"))
    rule, message = _finding_rule(item), _finding_message(item)
    if not title:
        if rule and message:
            title = f"{rule}: {message}"
        elif message:
            title = message
        elif rule:
            title = rule
        else:
            title = _where(item) or "находка гейта"
    return _clean(title)[:120]


def finding_acceptance(item: dict) -> list[str]:
    acceptance = _texts(item.get("acceptance") or item.get("ac") or item.get("criteria"))
    if acceptance:
        return acceptance
    where, rule = _where(item), _finding_rule(item)
    target = " ".join(part for part in (rule, where) if part) or finding_reference(item)
    return [f"находка устранена: {target}"]


def finding_labels(item: dict) -> list[str]:
    labels = _texts(item.get("labels") or item.get("tags"))
    rule = _finding_rule(item)
    if rule and len(rule) <= 40:
        labels.append(f"rule:{rule}")
    return list(dict.fromkeys(labels))


def _file_slug(path: str, depth: int) -> str:
    """`--slug-depth N`: slug из последних N сегментов пути (0 — весь путь)."""
    from planlib import model

    parts = [part for part in re.split(r"[\\/]+", path.strip()) if part]
    if not parts:
        return "gate"
    if depth > 0:
        parts = parts[-depth:]
    parts = [*parts[:-1], pathlib.PurePosixPath(parts[-1]).stem or parts[-1]]
    return "gate-" + model.slugify(" ".join(parts))


def _unique_slug(base: str, seen: set[str]) -> str:
    candidate, number = base, 2
    while candidate in seen:
        candidate = f"{base}-{number}"
        number += 1
    seen.add(candidate)
    return candidate


def _one_finding(item: dict, shard: str | None, labels: list[str]) -> Imported:
    from planlib import model

    where = _where(item)
    reference = finding_reference(item)
    body = [part for part in (_text(item.get("description")), _finding_message(item)) if part]
    rule = _finding_rule(item)
    if where:
        body.append(f"Источник: {where}" + (f" ({rule})" if rule else ""))
    if not body:
        body.append(f"Импортировано из отчёта гейта: {reference}")
    merged = list(dict.fromkeys([*finding_labels(item), *labels]))
    task_labels = _merge_shard(merged, shard)
    return Imported(
        key=reference,
        title=finding_title(item),
        status="To Do",
        acceptance=finding_acceptance(item),
        labels=task_labels,
        priority=(
            _text(item.get("priority")).lower()
            if _text(item.get("priority")).lower() in JSON_PRIORITIES
            else None
        ),
        source=reference,
        task_id=_text(item.get("id")) or None,
        slug=_text(item.get("slug")) or None,
        body="\n\n".join(body),
        references=[reference],
    )


def _merge_shard(labels: list[str], shard: str | None) -> list[str]:
    if not shard:
        return labels
    return [label for label in labels if not label.startswith("shard:")] + [f"shard:{shard}"]


def _grouped_finding(
    key: str,
    grouping: str,
    members: list[dict],
    shard: str | None,
    labels: list[str],
    slug_depth: int = 0,
) -> Imported:
    from planlib import model

    where_label = "файл" if grouping == "file" else "правило"
    count = len(members)
    title = (
        f"Гейт: {where_label} {key} — {count} {_plural(count, 'находка', 'находки', 'находок')}"
    )[:120]
    lines = [f"Импортировано из отчёта гейта ({where_label}: {key}).", "", "Находки:"]
    acceptance: list[str] = []
    references: list[str] = []
    for item in members:
        rule, message = _finding_rule(item), _finding_message(item)
        where = _where(item)
        text = " ".join(part for part in (rule, message) if part) or where or finding_reference(item)
        suffix = f" ({where})" if where and where not in text else ""
        lines.append(f"- {text}{suffix}")
        references.append(finding_reference(item))
        own = _texts(item.get("acceptance") or item.get("ac") or item.get("criteria"))
        acceptance.extend(own or [f"находка устранена: {text}{suffix}"])
    if grouping == "file":
        slug = _file_slug(key, slug_depth)
    else:
        slug = "gate-" + model.slugify(key) if key else "gate-findings"
    merged = list(dict.fromkeys([*labels, "findings"]))
    return Imported(
        key=f"{grouping}:{key}",
        title=title,
        status="To Do",
        acceptance=acceptance,
        labels=_merge_shard(merged, shard),
        source=references[0],
        slug=slug,
        body="\n".join(lines),
        references=references,
    )


def from_findings(
    findings: list[dict],
    shard: str | None = None,
    grouping: str = "none",
    labels: list[str] | None = None,
    slug_depth: int = 0,
) -> list[Imported]:
    """Находки → задачи: по одной, по файлу или по правилу."""
    if grouping not in JSON_GROUPINGS:
        raise JsonImportError(f"неизвестная группировка {grouping!r}: {', '.join(JSON_GROUPINGS)}")
    base_labels = ["gate", *(labels or [])]
    if grouping == "none":
        return [_one_finding(item, shard, base_labels) for item in findings]

    groups: dict[str, list[dict]] = {}
    for item in findings:
        key = _finding_file(item) if grouping == "file" else _finding_rule(item)
        groups.setdefault(key or "прочее", []).append(item)
    items = [
        _grouped_finding(key, grouping, members, shard, base_labels, slug_depth)
        for key, members in groups.items()
    ]
    seen: set[str] = set()
    for item in items:
        if item.slug:
            item.slug = _unique_slug(item.slug, seen)
    return items


def parse(path: pathlib.Path) -> tuple[str, list[Imported]]:
    text = path.read_text(encoding="utf-8")
    if PHASE.search(text):
        return "roadmap", parse_roadmap(path)
    if re.search(r"\*\*Статус[:\*]", text):
        return "numbered", parse_numbered(path)
    raise SystemExit(f"неизвестный формат: {path} (нет '## Phase N' и нет '**Статус:**')")


def description_for(item: Imported) -> str:
    if item.body:
        return item.body
    lines = [f"Импортировано из {pathlib.Path(item.source).name}."]
    if item.steps:
        lines.append("")
        lines.append("Шаги:")
        lines.extend(f"{number}. {step}" for number, step in enumerate(item.steps, 1))
    return "\n".join(lines)


def write_task(tasks: pathlib.Path, item: Imported) -> str:
    from planlib import model

    task = model.create(
        tasks,
        title=item.title,
        description=description_for(item),
        status=item.status,
        labels=item.labels,
        acceptance=item.acceptance,
        priority=item.priority,
        references=item.references or [item.source],
        task_id=item.task_id,
        slug=item.slug,
    )
    print(f"  + {task.id} [{item.status}] {item.title}")
    return task.id


def link_dependencies(tasks: pathlib.Path, task_id: str, dependencies: list[str]) -> None:
    from planlib import model

    task = model.find(tasks, task_id)
    task.dependencies = dependencies
    model.save(task, tasks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, parents=[layout_arguments_parent()])
    parser.add_argument(
        "source",
        nargs="?",
        type=pathlib.Path,
        help="путь к roadmap или numbered-плану",
    )
    parser.add_argument(
        "--from-json",
        type=pathlib.Path,
        help="JSON-отчёт находок гейта (lizard/xenon и подобные)",
    )
    parser.add_argument("--shard", help="метка shard:<name> для импортируемых задач")
    parser.add_argument(
        "--group-by",
        choices=list(JSON_GROUPINGS),
        default="none",
        help="json: одна задача на находку (none), на файл (file) или на правило (rule)",
    )
    parser.add_argument(
        "--slug-depth",
        type=int,
        default=0,
        metavar="N",
        help="json + --group-by file: slug из последних N сегментов пути "
        "(1 — имя файла; 0 — весь путь)",
    )
    parser.add_argument("--label", action="append", default=[], help="json: дополнительная метка")
    parser.add_argument(
        "--dedupe",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="json: пропускать находки, уже импортированные по reference (по умолчанию да)",
    )
    parser.add_argument("--apply", action="store_true", help="создать задачи (иначе dry-run)")
    enable_utf8()
    args = parser.parse_args(argv)

    if bool(args.source) == bool(args.from_json):
        print("нужен ровно один источник: SOURCE (roadmap/numbered) или --from-json FILE")
        return 2
    if args.slug_depth < 0:
        print("--slug-depth должен быть >= 0")
        return 2
    if args.from_json is None and (args.group_by != "none" or args.slug_depth):
        print("--group-by и --slug-depth работают только с --from-json")
        return 2
    if args.slug_depth and args.group_by != "file":
        print("--slug-depth работает только с --group-by file")
        return 2

    try:
        layout = layout_from_args(args)
    except LayoutError as error:
        print(f"ошибка конфига: {error}")
        return 3
    tasks = layout.tasks

    if args.from_json is not None:
        try:
            findings, meta = load_findings(args.from_json)
            shard = args.shard or _text(meta.get("shard")) or None
            labels = [*args.label, *_texts(meta.get("labels"))]
            items = from_findings(
                findings,
                shard=shard,
                grouping=args.group_by,
                labels=labels,
                slug_depth=args.slug_depth,
            )
        except JsonImportError as error:
            print(f"ошибка импорта: {error}")
            return 3
        count = len(findings)
        fmt = f"json ({count} {_plural(count, 'находка', 'находки', 'находок')})"
    else:
        fmt, items = parse(args.source)

    print(f"формат: {fmt}; к созданию: {len(items)}")
    for item in items:
        extra = f"AC {len(item.acceptance)}"
        if item.task_id:
            extra += f", id {item.task_id}"
        if item.slug:
            extra += f", slug {item.slug}"
        print(f"  - [{item.status}] {item.title} ({extra})")
    if not args.apply:
        print("\ndry-run: ничего не создано. Повторите с --apply.")
        return 0

    existing = load_tasks(tasks)
    existing_refs = {ref for task in existing for ref in task.references}
    created: dict[str, str] = {}
    skipped = 0
    failed = 0
    for item in items:
        if (
            args.from_json is not None
            and args.dedupe
            and item.references
            and any(ref in existing_refs for ref in item.references)
        ):
            print(f"  = пропуск (уже импортировано): {item.title[:80]}")
            skipped += 1
            continue
        try:
            created[item.key] = write_task(tasks, item)
            existing_refs.update(item.references)
        except ValueError as error:
            print(f"  ! {item.key}: {error}")
            failed += 1
    for item in items:
        if item.key not in created:
            continue
        dependencies = [created[dep] for dep in item.deps if dep in created]
        if dependencies:
            link_dependencies(tasks, created[item.key], dependencies)
    print(f"\nсоздано задач: {len(created)}, пропущено: {skipped}, ошибок: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
