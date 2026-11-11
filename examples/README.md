# Примеры форматов планов

Обезличенные образцы планов, на которых проверяется импорт (`plan-import`) и парсинг.
Все проекты, названия и пути здесь вымышленные.

| Файл | Формат | Что демонстрирует |
|---|---|---|
| `roadmap/roadmap.md` | roadmap | `## Phase N: … — DONE`, зависимости, acceptance criteria |
| `numbered-task/01-tests.md` | numbered | `**Статус:**`, `**Приоритет:**`, шаги, критерий готовности |
| `imports/demo-roadmap/` | backlog | результат `plan-import` из `roadmap/roadmap.md` |

## Импорт

```powershell
plan-import examples/roadmap/roadmap.md --project examples/imports/demo-roadmap --apply
plan-status --project examples/imports/demo-roadmap
```

## Локальные копии

Реальные планы проектов не публикуются: `plan-scrape` по умолчанию пишет в `examples/local/`,
а этот каталог в `.gitignore`.
