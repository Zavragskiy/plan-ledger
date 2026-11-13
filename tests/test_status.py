"""plan-status: единый stale, --open, priority и бюджет диагностики."""

from __future__ import annotations

import json
import pathlib

import yaml

from planlib.cli import gate as plan_gate
from planlib.cli import status as plan_status


def write_tasks(tmp_path: pathlib.Path, tasks: list[dict]) -> pathlib.Path:
    tasks_dir = tmp_path / "backlog" / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    for task in tasks:
        body = task.pop("_body", "")
        (tasks_dir / f"{task['id'].lower()}.md").write_text(
            "---\n" + yaml.safe_dump(task, allow_unicode=True) + "---\n" + body,
            encoding="utf-8",
        )
    return tasks_dir


def done_task(task_id: str, shard: str = "s1") -> dict:
    return {
        "id": task_id,
        "title": task_id,
        "status": "Done",
        "labels": [f"shard:{shard}"],
        "_body": "\n## Acceptance Criteria\n\n- [x] #1 passes\n",
    }


def test_stale_means_the_same_in_status_and_gate(tmp_path, monkeypatch, capsys):
    write_tasks(tmp_path, [done_task("TASK-1"), {"id": "TASK-2", "title": "open", "status": "To Do", "labels": ["shard:s2"]}])
    monkeypatch.setattr(
        "planlib.cli.status.acceptance_status", lambda layout, shard: ("run", "changed: a.py")
    )
    monkeypatch.setattr(
        "planlib.cli.gate.acceptance_status", lambda layout, shard: ("run", "changed: a.py")
    )

    assert plan_status.main(["--project", str(tmp_path), "--json"]) == 0
    status_data = json.loads(capsys.readouterr().out)
    assert plan_gate.main(["--project", str(tmp_path), "--json"]) == 1
    gate_data = json.loads(capsys.readouterr().out)

    assert status_data["summary"]["stale"] == gate_data["summary"]["stale"] == 1
    assert status_data["summary"]["unconfirmed"] == 1, "открытая задача не stale, а not confirmed"
    rows = {row["id"]: row for row in status_data["tasks"]}
    assert rows["TASK-2"]["verdict"] == "open"


def test_open_hides_done_but_keeps_totals(tmp_path, monkeypatch, capsys):
    write_tasks(
        tmp_path,
        [
            done_task("TASK-1"),
            {"id": "TASK-2", "title": "open one", "status": "To Do", "labels": ["shard:s2"]},
        ],
    )
    monkeypatch.setattr(
        "planlib.cli.status.acceptance_status", lambda layout, shard: ("up-to-date", "")
    )
    assert plan_status.main(["--project", str(tmp_path), "--json", "--open"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert [row["id"] for row in data["tasks"]] == ["TASK-2"]
    assert data["summary"]["total"] == 2
    assert data["summary"]["hidden_done"] == 1
    assert data["summary"]["done"] == 1

    assert plan_status.main(["--project", str(tmp_path), "--open"]) == 0
    text = capsys.readouterr().out
    assert "TASK-1" not in text
    assert "1 Done hidden" in text


def test_priority_column(tmp_path, monkeypatch, capsys):
    write_tasks(
        tmp_path,
        [
            {
                "id": "TASK-1",
                "title": "urgent",
                "status": "To Do",
                "priority": "high",
                "labels": ["shard:s1"],
            }
        ],
    )
    monkeypatch.setattr(
        "planlib.cli.status.acceptance_status", lambda layout, shard: ("up-to-date", "")
    )
    assert plan_status.main(["--project", str(tmp_path)]) == 0
    text = capsys.readouterr().out
    assert "prio" in text.splitlines()[1]
    assert "high" in text


def test_detail_is_bounded_by_default(tmp_path, monkeypatch, capsys):
    write_tasks(tmp_path, [done_task("TASK-1")])
    long_detail = "changed: " + ", ".join(f"src/f{index}.py" for index in range(346))
    monkeypatch.setattr(
        "planlib.cli.status.acceptance_status", lambda layout, shard: ("run", long_detail)
    )
    assert plan_status.main(["--project", str(tmp_path), "--json"]) == 0
    row = json.loads(capsys.readouterr().out)["tasks"][0]
    assert "src/f0.py" in row["detail"]
    assert "src/f4.py" not in row["detail"]
    assert "(+343 more)" in row["detail"]


def test_with_detail_restores_the_full_list(tmp_path, monkeypatch, capsys):
    write_tasks(tmp_path, [done_task("TASK-1")])
    long_detail = "changed: " + ", ".join(f"src/f{index}.py" for index in range(346))
    monkeypatch.setattr(
        "planlib.cli.status.acceptance_status", lambda layout, shard: ("run", long_detail)
    )
    assert plan_status.main(["--project", str(tmp_path), "--json", "--with-detail"]) == 0
    row = json.loads(capsys.readouterr().out)["tasks"][0]
    assert "src/f345.py" in row["detail"]


def test_open_task_detail_is_noise_but_errors_are_kept(tmp_path, monkeypatch, capsys):
    write_tasks(
        tmp_path,
        [
            {"id": "TASK-1", "title": "open", "status": "To Do", "labels": ["shard:s1"]},
            {"id": "TASK-2", "title": "broken", "status": "To Do", "labels": ["shard:s2"]},
        ],
    )

    def fake(layout, shard):
        return ("run", "changed: a.py") if shard == "s1" else ("error", "doit: ValueError: boom")

    monkeypatch.setattr("planlib.cli.status.acceptance_status", fake)
    assert plan_status.main(["--project", str(tmp_path), "--json"]) == 0
    rows = {row["id"]: row for row in json.loads(capsys.readouterr().out)["tasks"]}
    assert rows["TASK-1"]["detail"] is None
    assert rows["TASK-2"]["detail"] == "doit: ValueError: boom"
