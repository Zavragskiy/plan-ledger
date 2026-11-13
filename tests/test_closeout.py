"""Closeout: конверт на Done, closed_date, замена блока и вердикт гейта."""

from __future__ import annotations

import json
import pathlib

import yaml

from planlib import model
from planlib.cli import gate, task as plan_task


def seed(tmp_path: pathlib.Path, **front: object) -> pathlib.Path:
    tasks_dir = tmp_path / "backlog" / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "id": "TASK-1",
        "title": "one",
        "status": "To Do",
        "labels": ["shard:s1"],
        "created_date": "2026-11-13 10:00",
        "updated_date": "2026-11-13 10:00",
    }
    data.update(front)
    (tasks_dir / "task-1.md").write_text(
        "---\n" + yaml.safe_dump(data, allow_unicode=True) + "---\n"
        "## Acceptance Criteria\n\n- [ ] #1 passes\n",
        encoding="utf-8",
    )
    return tasks_dir


def test_done_without_outcome_is_refused(tmp_path, capsys):
    seed(tmp_path)
    assert plan_task.main(
        ["set", "TASK-1", "--status", "Done", "--check-ac", "1", "--project", str(tmp_path)]
    ) == 1
    assert "closeout" in capsys.readouterr().out
    tasks = model.load_tasks(tmp_path / "backlog" / "tasks")
    assert tasks[0].status == "To Do"


def test_done_with_outcome_records_closeout_and_closed_date(tmp_path, monkeypatch, capsys):
    seed(tmp_path)
    monkeypatch.setattr(
        "planlib.cli.task.acceptance_state", lambda layout, shard: "up-to-date"
    )
    code = plan_task.main(
        [
            "set",
            "TASK-1",
            "--status",
            "Done",
            "--check-ac",
            "1",
            "--outcome",
            "split the parser",
            "--decision",
            "kept module-level for the harness",
            "--followup",
            "extend mypy scope",
            "--files",
            "src/parser.py",
            "--tests",
            "pytest tests/test_parser.py",
            "--project",
            str(tmp_path),
        ]
    )
    capsys.readouterr()
    assert code == 0
    task = model.load_tasks(tmp_path / "backlog" / "tasks")[0]
    assert task.status == "Done"
    assert task.closed
    assert task.closeout is not None
    assert task.closeout.outcome == "split the parser"
    assert task.closeout.decisions == ["kept module-level for the harness"]
    assert task.closeout.followups == ["extend mypy scope"]
    assert task.closeout.files == ["src/parser.py"]
    assert task.closeout.tests == ["pytest tests/test_parser.py"]
    assert task.closeout.evidence["shard"] == "s1"
    assert task.closeout.evidence["result"] == "up-to-date"
    # round-trip в файл
    reloaded = model.parse(task.path)
    assert reloaded.closeout is not None
    assert reloaded.closeout.outcome == "split the parser"
    assert reloaded.closed == task.closed


def test_reconfirm_replaces_instead_of_appending(tmp_path, monkeypatch, capsys):
    seed(tmp_path)
    monkeypatch.setattr("planlib.cli.task.acceptance_state", lambda layout, shard: "up-to-date")
    first = plan_task.main(
        ["set", "TASK-1", "--status", "Done", "--check-ac", "1",
         "--outcome", "first", "--decision", "old", "--project", str(tmp_path)]
    )
    assert first == 0
    closed = model.load_tasks(tmp_path / "backlog" / "tasks")[0].closed
    capsys.readouterr()
    second = plan_task.main(
        ["set", "TASK-1", "--outcome", "second", "--decision", "new", "--project", str(tmp_path)]
    )
    assert second == 0
    task = model.load_tasks(tmp_path / "backlog" / "tasks")[0]
    assert task.closeout is not None
    assert task.closeout.outcome == "second"
    assert task.closeout.decisions == ["new"], "блок заменяется, а не дописывается"
    assert task.closed == closed, "closed_date не двигается повторным подтверждением"


def test_closed_date_survives_notes_and_owner(tmp_path, monkeypatch, capsys):
    seed(tmp_path)
    monkeypatch.setattr("planlib.cli.task.acceptance_state", lambda layout, shard: "up-to-date")
    assert plan_task.main(
        ["set", "TASK-1", "--status", "Done", "--check-ac", "1",
         "--outcome", "x", "--project", str(tmp_path)]
    ) == 0
    closed = model.load_tasks(tmp_path / "backlog" / "tasks")[0].closed
    capsys.readouterr()
    assert plan_task.main(
        ["set", "TASK-1", "--note", "typo", "--owner", "session-1", "--project", str(tmp_path)]
    ) == 0
    assert model.load_tasks(tmp_path / "backlog" / "tasks")[0].closed == closed


def test_empty_decision_is_refused(tmp_path, capsys):
    seed(tmp_path)
    assert plan_task.main(
        ["set", "TASK-1", "--outcome", "x", "--decision", "  ", "--project", str(tmp_path)]
    ) == 1
    assert "empty" in capsys.readouterr().out


def test_force_allows_done_without_closeout_and_gate_reports_it(tmp_path, monkeypatch, capsys):
    seed(tmp_path)
    assert plan_task.main(
        ["set", "TASK-1", "--status", "Done", "--check-ac", "1", "--force", "--project", str(tmp_path)]
    ) == 0
    assert model.load_tasks(tmp_path / "backlog" / "tasks")[0].closeout is None

    monkeypatch.setattr("planlib.cli.gate.acceptance_state", lambda layout, shard: "up-to-date")
    monkeypatch.setattr("planlib.cli.gate.acceptance_detail", lambda layout, shard: "")
    assert gate.main(["--project", str(tmp_path)]) == 0, "no-closeout не блокирует без --strict"
    output = capsys.readouterr().out
    assert "NO CLOSEOUT" in output
    assert gate.main(["--project", str(tmp_path), "--strict"]) == 2


def test_closeout_is_ok_for_the_gate(tmp_path, monkeypatch, capsys):
    seed(tmp_path)
    monkeypatch.setattr("planlib.cli.task.acceptance_state", lambda layout, shard: "up-to-date")
    assert plan_task.main(
        ["set", "TASK-1", "--status", "Done", "--check-ac", "1",
         "--outcome", "x", "--project", str(tmp_path)]
    ) == 0
    capsys.readouterr()
    monkeypatch.setattr("planlib.cli.gate.acceptance_state", lambda layout, shard: "up-to-date")
    monkeypatch.setattr("planlib.cli.gate.acceptance_detail", lambda layout, shard: "")
    assert gate.main(["--project", str(tmp_path), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["summary"]["ok"] == 1
    assert data["summary"]["no_closeout"] == 0


def test_show_and_list_expose_the_closeout(tmp_path, monkeypatch, capsys):
    seed(tmp_path)
    monkeypatch.setattr("planlib.cli.task.acceptance_state", lambda layout, shard: "up-to-date")
    assert plan_task.main(
        ["set", "TASK-1", "--status", "Done", "--check-ac", "1",
         "--outcome", "visible outcome", "--project", str(tmp_path)]
    ) == 0
    capsys.readouterr()

    assert plan_task.main(["show", "TASK-1", "--json", "--project", str(tmp_path)]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["closeout"]["outcome"] == "visible outcome"
    assert shown["closed_date"]

    assert plan_task.main(["list", "--json", "--project", str(tmp_path)]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed[0]["outcome"] == "visible outcome"
    assert listed[0]["closed_date"]
