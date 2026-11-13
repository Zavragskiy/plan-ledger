"""Флаги раскладки в любой позиции: plan-task list --project и --project ... list."""

from __future__ import annotations

import pathlib
import subprocess
import sys

import yaml


def write_task(project: pathlib.Path) -> None:
    tasks = project / "backlog" / "tasks"
    tasks.mkdir(parents=True, exist_ok=True)
    (tasks / "task-1.md").write_text(
        "---\n" + yaml.safe_dump({"id": "TASK-1", "title": "one", "status": "To Do"}) + "---\n",
        encoding="utf-8",
    )


def run(module: str, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", module, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_project_flag_after_subcommand(tmp_path):
    write_task(tmp_path)
    result = run("planlib.cli.task", ["list", "--project", str(tmp_path)])
    assert result.returncode == 0, result.stderr
    assert "TASK-1" in result.stdout


def test_project_flag_before_subcommand(tmp_path):
    write_task(tmp_path)
    result = run("planlib.cli.task", ["--project", str(tmp_path), "list"])
    assert result.returncode == 0, result.stderr
    assert "TASK-1" in result.stdout


def test_status_project_flag_anywhere(tmp_path):
    write_task(tmp_path)
    for args in (["--project", str(tmp_path)], ["--project=" + str(tmp_path)]):
        result = run("planlib.cli.status", args)
        assert result.returncode == 0, result.stderr
        assert "NEXT: TASK-1" in result.stdout


def test_check_project_flag(tmp_path):
    write_task(tmp_path)
    result = run("planlib.cli.gate", ["--project", str(tmp_path)])
    assert result.returncode == 0, result.stderr


def make_criteria_project(tmp_path) -> None:
    from planlib import model

    model.create(
        tmp_path / "backlog" / "tasks",
        title="probe: three criteria",
        labels=["shard:px"],
        acceptance=["first", "second", "third"],
    )


def criteria_state(tmp_path) -> list[bool]:
    from planlib import model

    task = model.load_tasks(tmp_path / "backlog" / "tasks")[0]
    return [done for done, _ in task.acceptance]


def test_repeated_check_ac_ticks_every_index(tmp_path):
    make_criteria_project(tmp_path)
    result = run(
        "planlib.cli.task",
        ["set", "TASK-1", "--check-ac", "1", "--check-ac", "2", "--check-ac", "3", "--project", str(tmp_path)],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert criteria_state(tmp_path) == [True, True, True]


def test_comma_form_ticks_indices(tmp_path):
    make_criteria_project(tmp_path)
    result = run("planlib.cli.task", ["set", "TASK-1", "--check-ac", "1,2", "--project", str(tmp_path)])
    assert result.returncode == 0, result.stdout + result.stderr
    assert criteria_state(tmp_path) == [True, True, False]


def test_out_of_range_is_clean_error_and_file_unchanged(tmp_path):
    make_criteria_project(tmp_path)
    result = run("planlib.cli.task", ["set", "TASK-1", "--check-ac", "9", "--project", str(tmp_path)])
    assert result.returncode == 1
    assert "acceptance criterion #9" in result.stdout
    assert criteria_state(tmp_path) == [False, False, False]


def test_done_refused_while_criteria_unchecked(tmp_path):
    make_criteria_project(tmp_path)
    result = run("planlib.cli.task", ["set", "TASK-1", "--status", "Done", "--project", str(tmp_path)])
    assert result.returncode == 1
    assert "--force" in result.stdout
    from planlib import model

    assert model.load_tasks(tmp_path / "backlog" / "tasks")[0].status == "To Do"


def test_done_allowed_when_all_criteria_checked(tmp_path):
    make_criteria_project(tmp_path)
    result = run(
        "planlib.cli.task",
        [
            "set",
            "TASK-1",
            "--status",
            "Done",
            "--check-ac",
            "1,2,3",
            "--outcome",
            "done in test",
            "--project",
            str(tmp_path),
        ],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    from planlib import model

    task = model.load_tasks(tmp_path / "backlog" / "tasks")[0]
    assert task.status == "Done"
    assert task.criteria == {"checked": 3, "total": 3}
    assert task.closeout is not None and task.closeout.outcome == "done in test"
    assert task.closed, "closed_date фиксируется на переходе в Done"


def test_force_allows_done_with_unchecked_criteria(tmp_path):
    make_criteria_project(tmp_path)
    result = run(
        "planlib.cli.task",
        ["set", "TASK-1", "--status", "Done", "--force", "--project", str(tmp_path)],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    from planlib import model

    assert model.load_tasks(tmp_path / "backlog" / "tasks")[0].status == "Done"


def test_note_does_not_rewrite_criteria(tmp_path):
    make_criteria_project(tmp_path)
    run("planlib.cli.task", ["set", "TASK-1", "--check-ac", "2", "--project", str(tmp_path)])
    result = run(
        "planlib.cli.task",
        ["set", "TASK-1", "--note", "session: checked", "--project", str(tmp_path)],
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert criteria_state(tmp_path) == [False, True, False]
