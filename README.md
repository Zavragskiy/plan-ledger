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
poetry build && poetry add dist/plan_ledger-0.4.2-py3-none-any.whl
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
| state dir | `state = ".planlib"` | DB in `.planlib/`, `dodo.py` in the root, tasks in `backlog/tasks` |
| dodo in state | `state = ".planlib"`, `dodo = ".planlib/dodo.py"` | relative `file_dep` still resolve: we pass `-d <root>` |
| tasks in state (legacy) | `tasks_base = "state"` | tasks live inside `state`, e.g. `.planlib/backlog/tasks` |

Config is looked up upward from the current directory: `plan-ledger.toml` first, then
`pyproject.toml` with `[tool.plan-ledger]`.

```toml
# plan-ledger.toml
[plan-ledger]
root       = "."            # code root: dodo.py and file_dep
state      = ".planlib"     # state dir and doit database
tasks      = "backlog/tasks"
tasks_base = "config"       # config | root | state
dodo       = "dodo.py"
db         = ".doit.db"
```

`tasks` is resolved from the **project root** (the config's directory) by default — that is the
0.3.0 fix for `plan-init --tasks backlog/tasks` silently creating `.planlib/backlog/tasks`. Use
`tasks_base = "root"` to resolve it from `root`, or `tasks_base = "state"` for the old
state-relative layout; an absolute `tasks` path also works. `dodo` is relative to `root`, `db` to
`state`.

`--project` (state), `--root` (code root) and `--config` override the config; flags are accepted
before or after a subcommand.

## Commands

| Command | Purpose |
|---|---|
| `plan-init [--state .planlib] [--tasks-base state] [--with-placeholder] [--config pyproject] [--dry-run]` | scaffold state, config, `dodo.py`, `.gitignore` |
| `plan-task list [--status S] [--json]` | list tasks |
| `plan-task new TITLE [-d DESC] [--ac …] [--shard gate] [--id ID] [--slug NAME] [--dep ID]` | create a task |
| `plan-task set ID [--status S] [--if-status EXPECTED] [--owner O] [--note …] [--shard NAME] [--slug NAME] [--check-ac N[,N…]] [--force]` | edit, with compare-and-set |
| `plan-status [--json] [--open] [--with-detail]` | statuses, readiness, acceptance, next task |
| `plan-run [SHARD …] [--all] [--quiet]` | run acceptance with the same `-f/-d/--db-file` that the gate uses; `--all` covers `dodo.py` |
| `plan-shard list [--strict] [--json]` | shards declared in `dodo.py`, the tasks that reference them, and plan-hygiene violations |
| `plan-check [--json] [--strict] [--allow-empty] [--with-detail]` | gate |
| `plan-import SOURCE [--apply]` | import `## Phase N` roadmaps and numbered task files |
| `plan-import --from-json FILE [--apply] [--group-by file\|rule\|none] [--shard NAME] [--slug-depth N]` | turn machine-readable gate findings into tasks |
| `plan-scrape [--projects DIR] [--out DIR]` | copy local plans into `examples/local/` (gitignored) |

Exit codes of `plan-check`: `0` clean, `1` stale or incomplete, `2` strict-unverified, `3` bad
config or empty plan. `plan-status` returns `0`, or `3` on a bad config or an empty plan. An empty
plan is deliberately **not** a success: that was the silent-green failure mode a root-relative
layout produced. The explicit escape hatches are `plan-check --allow-empty` and
`plan-init --with-placeholder`. `plan-shard list --strict` returns `1` on hygiene violations and
`3` when `dodo.py` cannot be read.

## Ordering, stale, and the detail budget

One ordering contract is shared by `plan-status`, `plan-task list` and (later) `plan-digest`:
`In Progress` first, then `priority` (`high` → `medium` → `low` → none), then a natural id — `TASK-8`
before `TASK-13`, and `TASK-13` before `TASK-1000`. String comparison of ids was a bug: it picked
`NEXT: TASK-13` over `TASK-8`.

`stale` has one definition: a `Done` task whose shard acceptance is not confirmed. An **open** task
with changed inputs was never proven, so it is reported as `not confirmed`, not stale —
`plan-status` and `plan-check` count it the same way. `plan-status --open` hides `Done` rows while
the totals still cover the whole plan (`N Done hidden` is printed; the JSON summary carries
`hidden_done`).

`plan-status` and `plan-check` show the first three changed paths plus a count
(`changed: a.py, b.py, c.py (+343 more)`) and keep `detail: null` for rows where the verdict needs
no diagnostic. `--with-detail` restores the full list; `PLAN_LEDGER_MAX_LISTED` still caps how much
`doit` output is captured.

## Acceptance criteria are enforced

A `Done` task must have every acceptance criterion ticked, and the gate checks that:

```text
TASK-1   Done   1/3   s1   up-to-date   incomplete
         └─ не отмечены критерии: 2, 3
```

- `--check-ac 1,2,3` and repeated `--check-ac 1 --check-ac 2` both work; an out-of-range index is a
  clean refusal (exit 1), not a traceback.
- `plan-task set <id> --status Done` refuses while criteria are unchecked; `--force` is the explicit
  escape hatch.
- `plan-check --json` rows carry `criteria: {checked, total}`; `plan-status` shows an `AC 2/3` column.
- Tasks without criteria (imported historical plans) keep working as before: `unverified` under
  `--strict` only.

## Task ids and file names

`TASK-N` is the default, but the file name is derived from the title, and Cyrillic titles
transliterate into long noise in git diffs. Two flags fix that:

```bash
plan-task new "Убрать файловые исключения из гейта сложности" \
    --id QUALITY-GATE --slug quality-gate --shard gate
# → backlog/tasks/quality-gate.md, frontmatter: id: QUALITY-GATE, slug: quality-gate
```

- `--slug` sets the whole file stem (`quality-gate.md`); it is stored in frontmatter and survives
  later edits. Without `--slug`, the legacy `<id> - <transliterated-title>.md` name is kept.
- `plan-task set <id> --slug <name>` renames the file; renaming onto an existing file is refused.
- A task can be addressed by id or by slug: `plan-task set quality-gate --status "In Progress"`.
- `--shard NAME` is the readable form of `-l shard:NAME` and works in both `new` and `set`
  (`set --shard` replaces the previous shard label instead of appending another one).

## Shards without manual lists

`plan-run` does not need a hand-maintained list of shard names:

```bash
plan-run --all               # every shard declared by dodo.py, plus any the plan references
plan-shard list              # shards declared in dodo.py + tasks pointing at them
plan-shard list --strict     # exit 1 on hygiene violations (CI gate)
```

Coverage comes from `dodo.py`, not from the task tree: `plan-run --all` runs a shard even when no
plan task references it, and it warns on stderr (`dodo.py shards without plan tasks: … — runs them
anyway`). Before 0.4.2 such a shard was skipped, so deleting the last task of a shard silently
removed the check from CI while the gate stayed green.

`plan-shard list` reads the shard list through `doit list` (so dynamically created tasks count)
and falls back to parsing `task_*` functions out of `dodo.py` when doit is unavailable. It marks
tasks that reference a shard missing from `dodo.py` (`(нет в dodo.py)`) and tasks with no
`shard:` label at all. `--strict` turns three hygiene problems into exit 1: a shard without
tasks, a task without a shard, and a task whose shard is absent from `dodo.py`. `--json` output
is meant for agents and carries a `violations` list.

## Bootstrap: an empty plan is not green

`plan-check` treats "no tasks" as exit 3, so a fresh repository with the pre-commit hook already
installed cannot make its first commit. Two explicit ways out:

```bash
plan-init --with-placeholder   # one open bootstrap task (gate passes)
plan-check --allow-empty       # accept an empty plan once; warns on stderr
```

`--with-placeholder` is idempotent: if the plan already has tasks, it does nothing.

## Importing gate findings

Machine-readable findings (lizard/xenon and friends) can become tasks instead of being copied by
hand:

```bash
plan-import --from-json findings.json --shard gate            # dry-run
plan-import --from-json findings.json --shard gate --apply
plan-import --from-json findings.json --group-by file --apply # one task per file
plan-import --from-json findings.json --group-by file --slug-depth 2 --apply
```

The report is a list of findings or `{"shard": "gate", "labels": ["audit"], "findings": [...]}`
(see [`examples/findings.json`](examples/findings.json));
each finding may carry `title`, `message`, `rule`, `file`, `line`, `description`, `acceptance`
(list), `labels`, `priority`, `id`, `slug`, `reference`. `--group-by file|rule` creates one task
per file/rule with every finding as an acceptance criterion. Grouped file tasks get an auto slug
from the file path (`gate-src-app`); `--slug-depth 2` keeps only the last two path segments
(`gate-mover-bases-mover-mixins`), `--slug-depth 1` keeps the file name. Re-running the same
report is idempotent: a finding whose `reference` (default `file:line`) is already in a task's
`references` is skipped.

## Workflow

```bash
plan-init --with-placeholder                # once: .planlib + config + dodo.py
plan-status
plan-task set TASK-3 --status "In Progress" --if-status "To Do"
plan-run --all                              # exactly what plan-check will verify
plan-task set TASK-3 --status Done --check-ac 1 --note "plan-run --all — passed"
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
- Stale dependency lists are truncated to 3 paths in the default view (`… (+N more)`); the raw
  list is capped at 10 paths and raised with `PLAN_LEDGER_MAX_LISTED`, and `--with-detail` prints
  it in full.
- A failing acceptance prints one error line (`ValueError: …`, `ERROR: …`) instead of a traceback
  tail; a shard missing from `dodo.py` is reported as `unknown`, not as a crash.

## Layout of this repository

| Path | Role |
|---|---|
| `planlib/config.py` | layout resolution: config search, overrides, errors |
| `planlib/model.py` | task model: frontmatter, sections, acceptance, `Blocked`, `owner` |
| `planlib/acceptance.py` | doit invocation and status: `up-to-date` / `run` / `error` / `unknown` |
| `planlib/shards.py` | shard discovery: `doit list` with a `task_*` AST fallback |
| `planlib/cli/` | `task`, `status`, `gate`, `run`, `shard`, `init`, `importer`, `scraper` |
| `backlog/` | demo project with three shards |
| `plan-ledger.toml` | this repository's layout (root) |
| `examples/` | anonymized plan formats and an import result (`examples/local/` is gitignored) |
| `skill/plan-ledger/SKILL.md`, `AGENTS.md` | agent protocol |
| `tests/` | config, gate, acceptance, init, CLI flags, real-doit layout integration |

## Limits

- `.doit.db` is local, so on CI every acceptance reads `run`; the gate checks freshness there.
- Acceptance status is memoised per `(db, shard)` within one command, so a 100-task plan on two
  shards costs two `doit info` calls, not 100. The cache is reset per command, so file edits and
  `plan-run` are always visible.
- 0.4.2 behaviour change: `plan-run --all` also runs `dodo.py` shards that no task references
  (previously skipped with a warning), and `plan-status --json` gained `verdict`, `unconfirmed`
  and `hidden_done` keys.
- Statuses are `To Do / In Progress / Blocked / Done`; a blocker's reason lives in notes.
- CLI output is English by design: there is no localization layer. Task titles, paths and
  imported text stay whatever UTF-8 they are (Cyrillic included); use `--json` for machine
  parsing instead of localized human text.
- Without `--slug`, task titles are transliterated into ASCII file names; `--slug` opts out.
- 0.4.0 translated the CLI to English (a breaking change for scripts that matched Russian
  strings); JSON output was already English-keyed and is the stable interface.
- Upgrading from 0.2: `tasks` is now resolved from the config's directory. A config that kept
  tasks inside `state` (`.planlib/backlog/tasks`) needs `tasks_base = "state"` or a `tasks` path
  that includes the state dir.

## License

MIT — see [LICENSE](LICENSE).
