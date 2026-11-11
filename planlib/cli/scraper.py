"""Скрейпит планы и таски проектов в локальный каталог примеров и пишет MANIFEST.md."""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import shutil

ROOT = pathlib.Path.cwd()
EXCLUDE = re.compile(
    r"\\node_modules\\|\\\.venv\\|__pycache__|site-packages|\\build\\|\\dist\\|"
    r"\\\.git\\|\\Temp\\|public\\all_modules|\\plan-pilot\\|\\examples\\",
    re.I,
)
NAME_HINT = re.compile(r"(?i)plan|task|spec|todo|roadmap|design|backlog")
DIR_HINT = re.compile(r"(?i)plans?|tasks?|specs?|roadmaps?")


def kind_of(path: pathlib.Path, text: str) -> str:
    name = path.name.lower()
    if "## phase" in text.lower():
        return "roadmap"
    if "**статус" in text.lower() or "**status:" in text.lower():
        return "task"
    if re.match(r"\|\s*P[0-3]\s*\|", text):
        return "backlog-table"
    if name.startswith("readme") or name in {"index.md"}:
        return "index"
    if "review" in name:
        return "review"
    return "plan"


def heading(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("#"):
            return re.sub(r"\s+", " ", line.lstrip("# ")).strip()[:90]
    return ""


def collect(projects: pathlib.Path) -> list[tuple[pathlib.Path, pathlib.Path, str, str, int]]:
    found = []
    for path in projects.rglob("*.md"):
        full = str(path)
        if EXCLUDE.search(full):
            continue
        if not (NAME_HINT.search(path.name) or DIR_HINT.search(str(path.parent))):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        project = path.relative_to(projects).parts[0]
        found.append((path, pathlib.Path(project), kind_of(path, text), heading(text), len(text)))
    return sorted(found, key=lambda item: (item[1].as_posix(), item[0].as_posix()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--projects",
        type=pathlib.Path,
        default=pathlib.Path(os.environ.get("PLAN_PROJECTS", pathlib.Path.cwd())),
        help="каталог с репозиториями (или переменная PLAN_PROJECTS)",
    )
    parser.add_argument("--out", type=pathlib.Path, default=ROOT / "examples" / "local")
    args = parser.parse_args(argv)

    items = collect(args.projects)
    rows = []
    for path, project, kind, title, size in items:
        relative = path.relative_to(args.projects)
        destination = args.out / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        rows.append((project.as_posix(), relative.as_posix(), kind, size, title))

    manifest = ["# Примеры планов и тасок из реальных репозиториев", ""]
    manifest.append(f"Источник: `{args.projects}`. Файлов: **{len(rows)}**. Пересобрать: `python scrape_plans.py`.")
    manifest.append("")
    manifest.append("| Проект | Файл | Тип | КБ | Заголовок |")
    manifest.append("|---|---|---|---:|---|")
    for project, relative, kind, size, title in rows:
        manifest.append(f"| {project} | `{relative}` | {kind} | {size / 1024:.1f} | {title} |")
    (args.out / "MANIFEST.md").write_text("\n".join(manifest) + "\n", encoding="utf-8")

    by_kind: dict[str, int] = {}
    for row in rows:
        by_kind[row[2]] = by_kind.get(row[2], 0) + 1
    print(f"скопировано {len(rows)} файлов в {args.out}")
    for kind, count in sorted(by_kind.items(), key=lambda pair: -pair[1]):
        print(f"  {kind:14} {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
