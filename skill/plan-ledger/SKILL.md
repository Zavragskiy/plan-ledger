---
name: plan-ledger
description: Use when a task spans many sessions and must stay current without Jira — resume plan state from backlog/, take the next shard, record evidence, and run the deterministic gate. Triggers on "продолжи план", "что дальше по плану", "возьми следующий шард", plan tracking, roadmap, backlog.
---

# Plan ledger

Источник истины — файлы в репозитории: `backlog/tasks/*.md` (что и в каком статусе) и `dodo.py`
(чем доказано). Внешнего трекера нет.

## Resume (начало чата)

```powershell
plan-task list
plan-status --json
```

Читай `plan-status` целиком (это ~20 строк вывода), а не план-документ. В план-документ
(`docs/tasks/...`) заглядывай только в разделы, названные в шагах выбранного шарда.
`session_search "<задача>"` — если нужны решения из прошлых чатов.

## Take (взял шард)

```powershell
plan-task set TASK-3 --status "In Progress" --if-status "To Do" --owner "session-7d23"
```

`--if-status` — compare-and-set: если соседняя сессия уже сдвинула статус, команда упадёт и
ничего не изменит. Это защита от двух чатов в одной задаче.

## Verify (перед Done)

```powershell
poetry run doit s3
plan-task set TASK-3 --status Done --check-ac 1 --note "session 7d23: doit s3 — 1 passed"
```

`Done` ставится только после успешной приёмки. Задача без метки `shard:<name>` приёмкой не
покрыта — либо добавь задачу в `dodo.py`, либо оставь `In Progress`.

## Gate (перед коммитом/выходом)

```powershell
plan-check            # 0 — чисто, 1 — протухло
```

`stale` = задача Done, но файлы шарда изменились после приёмки. Лечится повторным
`doit <shard>` (или понижением статуса, если правка реально откатила работу).

## Close (конец чата)

```powershell
plan-task set TASK-3 --note "session 7d23: что сделано, чем проверено, что мешает"
```

Не оставляй «устное» состояние: следующий чат видит только файлы.

## Rules

- Не создавай шард без `shard:<name>` и задачи приёмки в `dodo.py`.
- Не ставь `Done` без `doit`-подтверждения; гейт всё равно покраснеет.
- Один пишущий чат на задачу: `--if-status` плюс `--owner`; остальные — read-only и `plan-check`.
- Мигрированные исторические задачи (label `migrated`) остаются `unverified` — гейт их не
  блокирует, но приёмки у них нет; новую работу ведём только с приёмкой.
