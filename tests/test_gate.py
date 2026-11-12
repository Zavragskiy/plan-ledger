"""Гейт: пустой план — ошибка, stale/ok/error и JSON."""

from __future__ import annotations

import json
import pathlib

import pytest
import yaml

from planlib.cli import gate


def write_tasks(tmp_path: pathlib.Path, tasks: list[dict]) -> pathlib.Path:
    tasks_dir = tmp_path / "backlog" / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    for task in tasks:
        (tasks_dir / f"{task['id'].lower()}.md").write_text(
            "---\n" + yaml.safe_dump(task, allow_unicode=True) + "---\n", encoding="utf-8"
        )
    return tasks_dir


def test_empty_plan_is_error(tmp_path, capsys):
    (tmp_path / "backlog" / "tasks").mkdir(parents=True)
    assert gate.main(["--project", str(tmp_path)]) == 3
    assert "нет задач" in capsys.readouterr().out


def test_missing_tasks_dir_is_error(tmp_path, capsys):
    assert gate.main(["--project", str(tmp_path)]) == 3
    assert "нет каталога задач" in capsys.readouterr().out


def test_allow_empty(tmp_path):
    (tmp_path / "backlog" / "tasks").mkdir(parents=True)
    assert gate.main(["--project", str(tmp_path), "--allow-empty"]) == 0


def test_allow_empty_warns_on_stderr(tmp_path, capsys):
    (tmp_path / "backlog" / "tasks").mkdir(parents=True)
    assert gate.main(["--project", str(tmp_path), "--allow-empty"]) == 0
    assert "--allow-empty" in capsys.readouterr().err


def test_stale_done_task(tmp_path, monkeypatch, capsys):
    write_tasks(
        tmp_path,
        [{"id": "TASK-1", "title": "one", "status": "Done", "labels": ["shard:s1"]}],
    )
    monkeypatch.setattr(gate, "acceptance_status", lambda layout, shard: ("run", "изменились: src/a.py"))
    assert gate.main(["--project", str(tmp_path)]) == 1
    output = capsys.readouterr().out
    assert "ПРОТУХЛО" in output
    assert "src/a.py" in output


def test_error_acceptance_counts_as_stale(tmp_path, monkeypatch):
    write_tasks(
        tmp_path,
        [{"id": "TASK-1", "title": "one", "status": "Done", "labels": ["shard:s1"]}],
    )
    monkeypatch.setattr(gate, "acceptance_status", lambda layout, shard: ("error", "нет файлов"))
    assert gate.main(["--project", str(tmp_path)]) == 1


def test_ok_when_up_to_date(tmp_path, monkeypatch):
    write_tasks(
        tmp_path,
        [{"id": "TASK-1", "title": "one", "status": "Done", "labels": ["shard:s1"]}],
    )
    monkeypatch.setattr(gate, "acceptance_status", lambda layout, shard: ("up-to-date", ""))
    assert gate.main(["--project", str(tmp_path)]) == 0


def test_json_includes_layout(tmp_path, monkeypatch, capsys):
    write_tasks(
        tmp_path,
        [{"id": "TASK-1", "title": "one", "status": "Done", "labels": ["shard:s1"]}],
    )
    monkeypatch.setattr(gate, "acceptance_status", lambda layout, shard: ("up-to-date", ""))
    assert gate.main(["--project", str(tmp_path), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["layout"]["root"] == str(tmp_path)
    assert data["summary"]["ok"] == 1


def test_bad_config_is_exit_3(tmp_path, capsys):
    (tmp_path / "plan-ledger.toml").write_text("[plan-ledger\n", encoding="utf-8")
    assert gate.main(["--project", str(tmp_path)]) == 3
    assert "ошибка конфига" in capsys.readouterr().out


def test_done_with_unchecked_criteria_is_incomplete(tmp_path, monkeypatch, capsys):
    write_tasks(
        tmp_path,
        [
            {
                "id": "TASK-1",
                "title": "one",
                "status": "Done",
                "labels": ["shard:s1"],
            }
        ],
    )
    task_file = next((tmp_path / "backlog" / "tasks").glob("*.md"))
    task_file.write_text(
        task_file.read_text(encoding="utf-8")
        + "\n## Acceptance Criteria\n\n- [x] #1 first\n- [ ] #2 second\n- [ ] #3 third\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(gate, "acceptance_status", lambda layout, shard: ("up-to-date", ""))
    assert gate.main(["--project", str(tmp_path)]) == 1
    output = capsys.readouterr().out
    assert "НЕПОЛНЫЕ" in output
    assert "2, 3" in output


def test_json_reports_criteria_counts(tmp_path, monkeypatch, capsys):
    write_tasks(
        tmp_path,
        [{"id": "TASK-1", "title": "one", "status": "Done", "labels": ["shard:s1"]}],
    )
    task_file = next((tmp_path / "backlog" / "tasks").glob("*.md"))
    task_file.write_text(
        task_file.read_text(encoding="utf-8")
        + "\n## Acceptance Criteria\n\n- [x] #1 first\n- [ ] #2 second\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(gate, "acceptance_status", lambda layout, shard: ("up-to-date", ""))
    assert gate.main(["--project", str(tmp_path), "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["rows"][0]["criteria"] == {"checked": 1, "total": 2}
    assert data["summary"]["incomplete"] == 1


def test_done_without_criteria_is_unchanged(tmp_path, monkeypatch):
    write_tasks(
        tmp_path,
        [{"id": "TASK-1", "title": "legacy", "status": "Done", "labels": ["shard:s1"]}],
    )
    monkeypatch.setattr(gate, "acceptance_status", lambda layout, shard: ("up-to-date", ""))
    assert gate.main(["--project", str(tmp_path)]) == 0
