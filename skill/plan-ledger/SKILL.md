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
plan-status --json        # --open — без Done-строк; счётчики всё равно по всему плану
plan-digest --active      # компактный срез: одна строка на задачу, без detail
plan-shard list      # какие шарды есть в dodo.py и какие задачи на них ссылаются
```

Читай `plan-status` целиком (~20 строк), а не план-документ. В план-документ (`docs/tasks/...`)
заглядывай только в разделы, названные в шагах выбранной задачи. `session_search "<задача>"` —
если нужны решения из прошлых чатов. Пустой план — это exit 3, а не «всё готово».

Порядок строк один для `plan-status` и `plan-task list`: `In Progress`, затем `priority`
(`high` → `medium` → `low`), затем натуральный id (`TASK-8` раньше `TASK-13`, `TASK-1000` после
`TASK-13`). `NEXT` — первая готовая открытая задача в этом порядке.

## Take (взял шард)

```powershell
plan-task set TASK-3 --status "In Progress" --if-status "To Do" --owner "session-7d23"
```

`--if-status` — compare-and-set: если соседняя сессия уже сдвинула статус, команда упадёт и
ничего не изменит.

## Verify (перед Done)

```powershell
plan-run --all        # все шарды из dodo.py (плюс шарды, на которые ссылается план)
plan-run --done       # только шарды Done-задач: пере-доказать закрытый набор после мержа
plan-task set TASK-3 --status Done --check-ac 1,2,3 `
    --outcome "что реально изменилось" `
    --decision "почему так, что отвергли" `
    --followup "что осталось" `
    --files src/parser.py --tests "pytest tests/test_parser.py"
```

Отмечай критерии, которые реально проверил: `--check-ac 1,2,3` (или повторяй флаг). `Done` без
отмеченных критериев отвергается; `--force` — только осознанное исключение. Гейт всё равно покажет
`incomplete`.

`Done` требует `--outcome` в том же вызове: конверт `outcome/decisions/followups/files/tests` и
`evidence {shard, result, commit}` пишется один раз, `closed_date` фиксируется на переходе.
Повторное подтверждение `Done` **заменяет** блок, а не дописывает. `--force` записывает Done без
closeout — гейт покажет `no-closeout` (не блокирует без `--strict`).

`plan-run` — единственный правильный способ прогнать приёмку: он передаёт те же
`-f/-d/--db-file`, что и `plan-check`. Ручной `doit` без `--db-file` положит БД в корень кода и
гейт покажет «изменились» все файлы.

`Done` ставится только после успешной приёмки. Задача без метки `shard:<name>` приёмкой не
покрыта — либо добавь задачу в `dodo.py`, либо оставь `In Progress`.

`plan-run --all` берёт покрытие из `dodo.py`: шард без задач всё равно прогоняется, а в stderr
предупреждает «dodo.py shards without plan tasks: …». Раньше такой шард молча пропускался, и
удаление последней задачи шарда выключало проверку в CI. Гигиену плана держит
`plan-shard list --strict` (exit 1: шард без задачи, задача без шарда, шард отсутствует в `dodo.py`).

## Gate (перед коммитом/выходом)

```powershell
plan-check            # 0 — чисто, 1 — протухло, 2 — --strict: unverified/no-closeout, 3 — конфиг/пустой план
```

`stale` = задача Done, но файлы шарда изменились после приёмки (пути печатаются относительно
корня; по умолчанию первые три и «(+N more)», полный список — `--with-detail`). Открытая задача с
изменившимися входами — `not confirmed`, а не stale: у неё приёмка ещё не подтверждалась.
Лечится повторным `plan-run <shard>` или понижением статуса, если правка откатила работу.

## Close (конец чата)

```powershell
plan-task set TASK-3 --note "session 7d23: что сделано, чем проверено, что мешает"
```

Не оставляй «устное» состояние: следующий чат видит только файлы.

## Rules

- Не создавай шард без `shard:<name>` и задачи приёмки в `dodo.py`: `plan-task new … --shard s3`;
  `set --shard` заменяет метку, `-l shard:s3` остаётся алиасом.
- Не ставь `Done` без `plan-run`-подтверждения, без отмеченных критериев приёмки и без `--outcome`:
  closeout — это то, что читает следующая сессия, а `plan-digest` показывает одной строкой.
- Один пишущий чат на задачу: `--if-status` плюс `--owner`.
- Русский заголовок не обязан превращаться в длинное имя файла: `--id QUALITY-GATE --slug quality-gate`
  (slug — имя файла целиком, хранится в frontmatter, `set --slug` переименовывает).
- Мигрированные исторические задачи (label `migrated`) остаются `unverified` — гейт их не
  блокирует, но приёмки у них нет.
- Новая раскладка — `plan-init`; на пустом репозитории с хуком — `plan-init --with-placeholder`,
  иначе первый коммит блокируется exit 3.
- Находки гейта не переписывай руками: `plan-import --from-json findings.json --shard gate --apply`;
  длинные slug'и сокращай `--slug-depth 2`.
- `plan-shard list --strict` — гигиена плана в CI, а не только локальная привычка.
