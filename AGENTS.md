# Протокол ведения плана (вставить в AGENTS.md репозитория)

## Task plans

- **Layout:** раскладка берётся из `plan-ledger.toml` (или `[tool.plan-ledger]` в `pyproject.toml`),
  поиск идёт вверх от cwd. `--project`/`--root` нужны только для override.
- **Resume:** `plan-status` (+ `plan-task list`); план-документ читать только по разделам шагов
  выбранной задачи, `session_search "<slug>"` — для прошлых решений.
- **Take:** `plan-task set <id> --status "In Progress" --if-status "To Do"` — compare-and-set;
  чужая сессия сдвинула статус → команда падает, ничего не меняя.
- **Evidence:** `Done` только после `plan-run <shard>` и с отмеченными критериями
  (`--check-ac 1,2,…`); в том же коммите — `--note "session <id>: plan-run <shard> → <результат>"`.
- **Gate:** `plan-check` в pre-commit; `stale` (Done с изменившимися файлами) — блокер, а пустой
  план даёт exit 3, а не «зелено».
- **Close:** `--note` с итогом и блокерами; «что дальше» живёт в статусах и `next`, не в чате.
