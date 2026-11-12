# plan-ledger

[![ci](https://github.com/Zavragskiy/plan-ledger/actions/workflows/ci.yml/badge.svg)](https://github.com/Zavragskiy/plan-ledger/actions/workflows/ci.yml)

Deterministic, file-first plan tracking for work that spans many sessions. No Jira, no database:
tasks are Markdown files with YAML frontmatter, and "done" is proven by an acceptance run instead of
a claim. A gate fails when a `Done` task's files changed after its acceptance.

```
plan-ledger.toml ─┐
task files      ─┼─ plan-status   → statuses, readiness, next task
doit acceptance ─┘   plan-check    → is every "Done" actually proven?
                     plan-task     → create / edit, with compare-and-set status changes
```

## Install

```bash
poetry add --editable /path/to/plan-ledger   # development
# or
poetry build && poetry add dist/plan_ledger-0.2.0-py3-none-any.whl
```

Python `>=3.10`; dependencies `pyyaml`, `doit`, and `tomli` on 3.10.

The tracker format is compatible with [Backlog.md](https://github.com/MrLesk/Backlog.md) files:
existing `backlog/tasks/*.md` are read as-is and unknown sections (`Implementation Notes`,
`Definition of Done`) survive an edit. `backlog-md-py` is **not** a dependency.

## Layouts

`plan-init` scaffolds one of these; everything is driven by config, so commands never need
`--project`.

| Layout | Config | Notes |
|---|---|---|
| root | `state = "."` | `backlog/tasks`, `.doit.db`, `dodo.py` in the repo root |
| state dir | `state = ".planlib"` | tasks and DB in `.planlib/`, `dodo.py` in the root |
| dodo in state | `state = ".planlib"`, `dodo = ".planlib/dodo.py"` | relative `file_dep` still resolve: we pass `-d <root>` |

Config is looked up upward from the current directory: `plan-ledger.toml` first, then
`pyproject.toml` with `[tool.plan-ledger]`. Paths are relative to the config's directory.

```toml
# plan-ledger.toml
[plan-ledger]
root  = "."            # code root: dodo.py and file_dep
state = ".planlib"     # tasks and doit database
tasks = "backlog/tasks"
dodo  = "dodo.py"
db    = ".doit.db"
```

`--project` (state), `--root` (code root) and `--config` override the config; flags are accepted
before or after a subcommand.

## Commands

| Command | Purpose |
|---|---|
| `plan-init [--state .planlib] [--config pyproject] [--dry-run]` | scaffold state, config, `dodo.py`, `.gitignore` |
| `plan-task list [--status S] [--json]` | list tasks |
| `plan-task new TITLE [-d DESC] [--ac …] [-l shard:sN] [--dep ID]` | create a task |
| `plan-task set ID [--status S] [--if-status EXPECTED] [--owner O] [--note …] [--check-ac N]` | edit, with compare-and-set |
| `plan-status [--json]` | statuses, readiness, acceptance, next task |
| `plan-run [SHARD …] [--quiet]` | run acceptance with the same `-f/-d/--db-file` that the gate uses |
| `plan-check [--json] [--strict] [--allow-empty]` | gate |
| `plan-import SOURCE [--apply]` | import `## Phase N` roadmaps and numbered task files |
| `plan-scrape [--projects DIR] [--out DIR]` | copy local plans into `examples/local/` (gitignored) |

Exit codes of `plan-check` and `plan-status`: `0` clean, `1` stale, `2` strict-unverified
(`plan-check` only), `3` bad config or empty plan. An empty plan is deliberately **not** a success:
that was the silent-green failure mode a root-relative layout produced.

## Workflow

```bash
plan-init                                   # once: .planlib + config + dodo.py
plan-status
plan-task set TASK-3 --status "In Progress" --if-status "To Do"
plan-run s3                                 # exactly what plan-check will verify
plan-task set TASK-3 --status Done --check-ac 1 --note "plan-run s3 — passed"
plan-check
```

Wire `plan-check` into pre-commit; [`.pre-commit-config.yaml`](.pre-commit-config.yaml) runs it with
`always_run: true`, so it is independent of where the state lives.

## doit: what matters

- Run acceptance through `plan-run`: it passes the same `-f <dodo> -d <root> --db-file <db>` that
  `plan-check` uses, so "I ran it" and "it is verified" cannot diverge. A bare
  `doit -f .planlib/dodo.py -d . s1` without `--db-file` writes `.doit.db` into the code root, and
  the gate then reports every source file as changed.
- `doit -d` is a **directory**, not the database. The database is `--db-file` or
  `DOIT_CONFIG["dep_file"]`; `plan-init` pins `dep_file` next to the state.
- doit changes its working directory to the dodo file's directory, so relative `file_dep` resolve
  against it. plan-ledger always passes `-d <root>`, which makes relative paths resolve against the
  code root even when `dodo.py` sits in `.planlib/`.
- Subprocess actions inherit doit's cwd; pin it explicitly: `CmdAction(..., cwd=str(ROOT))`.
- Stale dependency lists are truncated to 10 paths (`… и ещё N`); raise with
  `PLAN_LEDGER_MAX_LISTED`.

## Layout of this repository

| Path | Role |
|---|---|
| `planlib/config.py` | layout resolution: config search, overrides, errors |
| `planlib/model.py` | task model: frontmatter, sections, acceptance, `Blocked`, `owner` |
| `planlib/acceptance.py` | doit invocation and status: `up-to-date` / `run` / `error` / `unknown` |
| `planlib/cli/` | `task`, `status`, `gate`, `init`, `importer`, `scraper` |
| `backlog/` | demo project with three shards |
| `plan-ledger.toml` | this repository's layout (root) |
| `examples/` | anonymized plan formats and an import result (`examples/local/` is gitignored) |
| `skill/plan-ledger/SKILL.md`, `AGENTS.md` | agent protocol |
| `tests/` | config, gate, acceptance, init, CLI flags, real-doit layout integration |

## Limits

- `.doit.db` is local, so on CI every acceptance reads `run`; the gate checks freshness there.
- Statuses are `To Do / In Progress / Blocked / Done`; a blocker's reason lives in notes.
- Task titles are transliterated into ASCII file names.
- CLI messages are currently in Russian.

## License

MIT — see [LICENSE](LICENSE).
