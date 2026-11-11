# plan-ledger

Deterministic, file-first plan tracking for work that spans many sessions. No Jira, no database:
tasks are Markdown files with YAML frontmatter, and "done" is proven by an acceptance run instead of
a claim. A gate fails when a `Done` task's files changed after its acceptance.

```
task file  ─┐
            ├─ plan-status   → what exists, what is ready, what is next
doit gate  ─┘   plan-check   → is every "Done" actually proven?
                plan-task    → create / edit, with compare-and-set status changes
```

## Why

Long-running refactors rarely fit one chat. Prose plans drift: nobody knows which phase is really
finished, and two sessions happily edit the same state. `plan-ledger` keeps machine state in files
you already review — `git diff` shows a status change, an acceptance criterion tick, a note — and
derives "done" from the acceptance command, not from an agent's opinion.

## How it works

- **State** lives in `backlog/tasks/*.md`: `id`, `title`, `status` (`To Do` / `In Progress` /
  `Blocked` / `Done`), `labels` (`shard:<name>` binds a task to an acceptance job), `dependencies`,
  `priority`, `owner`, acceptance criteria, notes.
- **Evidence** lives in `doit`: each shard is a task with `file_dep` and a command (tests, linter,
  build). `.doit.db` records the last successful run.
- **Gate**: `plan-check` reports `ok` / `open` / `unverified` / `stale`. `stale` = `Done` task whose
  acceptance is `run` again, i.e. the files moved after the proof. Exit 1 blocks the commit.
- **Parallel sessions**: `plan-task set <id> --if-status "To Do"` is compare-and-set — a second
  session that lost the race gets an error instead of a silent overwrite.

## Install

```bash
poetry add --editable /path/to/plan-ledger   # development
# or
poetry build && poetry add dist/plan_ledger-0.1.0-py3-none-any.whl
```

Python `>=3.10`; dependencies `pyyaml` and `doit`.

The tracker format is compatible with [Backlog.md](https://github.com/MrLesk/Backlog.md) files:
existing `backlog/tasks/*.md` are read as-is and unknown sections (`Implementation Notes`,
`Definition of Done`) survive an edit. `backlog-md-py` is **not** a dependency; install it separately
only if you want a human kanban/TUI over the same files.

## Commands

| Command | Purpose |
|---|---|
| `plan-task list [--status S] [--json]` | list tasks |
| `plan-task new TITLE [-d DESC] [--ac …] [-l shard:sN] [--dep ID]` | create a task |
| `plan-task set ID [--status S] [--if-status EXPECTED] [--owner O] [--note …] [--check-ac N]` | edit, with CAS |
| `plan-task show ID [--json]` | details |
| `plan-status [--project PATH] [--json]` | statuses, readiness, acceptance, next task |
| `plan-check [--project PATH] [--json] [--strict]` | gate |
| `plan-import SOURCE --project PATH [--apply]` | import `## Phase N` roadmaps and numbered task files |
| `plan-scrape [--projects DIR] [--out DIR]` | copy local plans into `examples/local/` |

## Workflow

```bash
plan-status
plan-task set TASK-2 --status "In Progress" --if-status "To Do"
poetry run doit s2
plan-task set TASK-2 --status Done --check-ac 1 --note "doit s2 — passed"
plan-check
```

Wire `plan-check` into pre-commit; [`.pre-commit-config.yaml`](.pre-commit-config.yaml) has a hook.

## Layout

| Path | Role |
|---|---|
| `planlib/model.py` | task model: frontmatter, sections, acceptance, `Blocked`, `owner` |
| `planlib/acceptance.py` | reads `doit` state: `up-to-date` / `run` / `unknown` / `no-doit` |
| `planlib/cli/{task,status,gate,importer,scraper}.py` | CLI layer |
| `backlog/` | demo project: three shards with acceptance and one blocked-by-dependency task |
| `dodo.py` | acceptance jobs for the demo shards |
| `examples/` | anonymized plan formats and an import result (`examples/local/` is gitignored) |
| `skill/plan-ledger/SKILL.md` | agent protocol (resume / take / verify / gate / close) |
| `AGENTS.md` | the same protocol as a short repository snippet |
| `tests/` | model, CAS, acceptance, import adapters, legacy-file round-trip |

## Design notes

- Acceptance is a command, not a sentence: `doit` re-runs it when `file_dep` changes, so a stale
  `Done` becomes visible instead of staying green forever.
- Migration is not all-or-nothing: tasks imported from historical plans carry `migrated` and stay
  `unverified`; the gate ignores them unless `--strict`.
- No MCP server: the tracker's MCP surface was ~30 tools / ~35 KB of schemas per request, which is
  worse than a ~2 KB skill loaded on demand.

## Limits

- `.doit.db` is local, so on CI every acceptance reads `run`; gate only freshness there.
- Statuses are `To Do / In Progress / Blocked / Done`; a blocker's reason lives in notes.
- Task titles are transliterated into ASCII file names.
- CLI messages are currently in Russian.

## License

MIT — see [LICENSE](LICENSE).
