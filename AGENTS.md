# Протокол ведения плана (вставить в AGENTS.md репозитория)

## Task plans

- **Resume:** `plan-status` (+ `plan-task list`); план-документ читать только по разделам шагов
  выбранной задачи, `session_search "<slug>"` — для прошлых решений.
- **Take:** `plan-task set <id> --status "In Progress" --if-status "To Do"` — compare-and-set;
  чужая сессия сдвинула статус → команда падает, ничего не меняя.
- **Evidence:** `Done` только после `poetry run doit <shard>`; в том же коммите — `--check-ac N` и
  `--note "session <id>: <команда> → <результат>"`.
- **Gate:** `plan-check` в pre-commit; `stale` (Done с изменившимися файлами) — блокер.
- **Close:** `--note` с итогом и блокерами; «что дальше» живёт в статусах и `next`, не в чате.
