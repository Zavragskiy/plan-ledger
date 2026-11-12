---
name: plan-ledger
description: Use when a task spans many sessions and must stay current without Jira — resume plan state from backlog/, take the next shard, record evidence, and run the deterministic gate. Triggers on "продолжи план", "что дальше по плану", "возьми следующий шард", plan tracking, roadmap, backlog.
---

# Plan ledger

Источник истины — файлы в репозитории: `backlog/tasks/*.md` (что и в каком статусе) и `dodo.py`
(чем доказано). Раскладка берётся из `plan-ledger.toml` / `[tool.plan-ledger]`, поэтому
`--project` не нужен: конфиг ищется вверх от cwd.

## Resume (начало чата)

```powershell
plan-task list
plan-status --json
```

Читай `plan-status` целиком (~20 строк), а не план-документ. В план-документ (`docs/tasks/...`)
заглядывай только в разделы, названные в шагах выбранной задачи. `session_search "<задача>"` —
если нужны решения из прошлых чатов. Пустой план — это exit 3, а не «всё готово».

## Take (взял шард)

```powershell
plan-task set TASK-3 --status "In Progress" --if-status "To Do" --owner "session-7d23"
```

`--if-status` — compare-and-set: если соседняя сессия уже сдвинула статус, команда упадёт и
ничего не изменит.

## Verify (перед Done)

```powershell
plan-run s3
plan-task set TASK-3 --status Done --check-ac 1,2,3 --note "session 7d23: plan-run s3 — 1 passed"
```

Отмечай критерии, которые реально проверил: `--check-ac 1,2,3` (или повторяй флаг). `Done` без
отмеченных критериев отвергается; `--force` — только осознанное исключение. Гейт всё равно покажет
`incomplete`.

`plan-run` — единственный правильный способ прогнать приёмку: он передаёт те же
`-f/-d/--db-file`, что и `plan-check`. Ручной `doit` без `--db-file` положит БД в корень кода и
гейт покажет «изменились» все файлы.

`Done` ставится только после успешной приёмки. Задача без метки `shard:<name>` приёмкой не
покрыта — либо добавь задачу в `dodo.py`, либо оставь `In Progress`.

## Gate (перед коммитом/выходом)

```powershell
plan-check            # 0 — чисто, 1 — протухло, 3 — конфиг/пустой план
```

`stale` = задача Done, но файлы шарда изменились после приёмки (пути печатаются относительно
корня, длинный список обрезается до 10 с «… и ещё N»). Лечится повторным `plan-run <shard>` или
понижением статуса, если правка откатила работу.

## Close (конец чата)

```powershell
plan-task set TASK-3 --note "session 7d23: что сделано, чем проверено, что мешает"
```

Не оставляй «устное» состояние: следующий чат видит только файлы.

## Rules

- Не создавай шард без `shard:<name>` и задачи приёмки в `dodo.py`.
- Не ставь `Done` без `plan-run`-подтверждения и без отмеченных критериев приёмки.
- Один пишущий чат на задачу: `--if-status` плюс `--owner`.
- Мигрированные исторические задачи (label `migrated`) остаются `unverified` — гейт их не
  блокирует, но приёмки у них нет.
- Новая раскладка — `plan-init`; вручную конфиг и dodo не пиши.
