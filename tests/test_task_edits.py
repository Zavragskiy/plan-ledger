"""plan-task set: evidence (head_at_close) и правка текста acceptance."""

from __future__ import annotations

import pathlib

import yaml

from planlib import model
from planlib.cli import task as plan_task


def write_task(tmp_path: pathlib.Path, *, status: str = "To Do", extra: dict | None = None) -> pathlib.Path:
    tasks_dir = tmp_path / "backlog" / "tasks"
    tasks_dir.mkdir(parents=True)
    meta = {
        "id": "TASK-1",
        "title": "one",
        "status": status,
        "labels": ["shard:s1"],
        "created_date": "2026-11-13 10:00",
        "updated_date": "2026-11-13 10:00",
    }
    meta.update(extra or {})
    path = tasks_dir / "task-1.md"
    path.write_text(
        "---\n" + yaml.safe_dump(meta, allow_unicode=True) + "---\n"
        "## Acceptance Criteria\n\n- [x] #1 old path\n- [ ] #2 old path\n",
        encoding="utf-8",
    )
    return path


def test_legacy_evidence_commit_is_renamed_on_read(tmp_path):
    write_task(
        tmp_path,
        status="Done",
        extra={
            "closed_date": "2026-11-13 11:00",
            "closeout": {
                "outcome": "x",
                "evidence": {"shard": "s1", "result": "up-to-date", "commit": "abc1234"},
            },
        },
    )
    task = model.load_tasks(tmp_path / "backlog" / "tasks")[0]
    assert task.closeout is not None
    assert task.closeout.evidence["head_at_close"] == "abc1234"
    assert "commit" not in task.closeout.evidence


def test_evidence_records_head_at_close(tmp_path, monkeypatch, capsys):
    write_task(tmp_path)
    monkeypatch.setattr("planlib.cli.task.acceptance_state", lambda layout, shard: "up-to-date")
    monkeypatch.setattr("planlib.cli.task._git_commit", lambda layout: "aaa1111")
    assert plan_task.main(
        ["set", "TASK-1", "--status", "Done", "--check-ac", "1,2", "--outcome", "x",
         "--project", str(tmp_path)]
    ) == 0
    capsys.readouterr()
    task = model.load_tasks(tmp_path / "backlog" / "tasks")[0]
    assert task.closeout.evidence["head_at_close"] == "aaa1111"
    assert "commit" not in task.closeout.evidence


def test_refresh_evidence_updates_the_pointer(tmp_path, monkeypatch, capsys):
    write_task(tmp_path)
    monkeypatch.setattr("planlib.cli.task.acceptance_state", lambda layout, shard: "up-to-date")
    monkeypatch.setattr("planlib.cli.task._git_commit", lambda layout: "aaa1111")
    assert plan_task.main(
        ["set", "TASK-1", "--status", "Done", "--check-ac", "1,2", "--outcome", "x",
         "--project", str(tmp_path)]
    ) == 0
    capsys.readouterr()
    monkeypatch.setattr("planlib.cli.task._git_commit", lambda layout: "bbb2222")
    assert plan_task.main(
        ["set", "TASK-1", "--refresh-evidence", "--project", str(tmp_path)]
    ) == 0
    task = model.load_tasks(tmp_path / "backlog" / "tasks")[0]
    assert task.closeout.evidence["head_at_close"] == "bbb2222"
    assert task.closeout.outcome == "x", "closeout не переписывается"
    assert task.status == "Done"


def test_refresh_without_closeout_is_refused(tmp_path, capsys):
    write_task(tmp_path)
    assert plan_task.main(
        ["set", "TASK-1", "--refresh-evidence", "--project", str(tmp_path)]
    ) == 1
    assert "no closeout" in capsys.readouterr().out


def test_ac_text_replaces_text_and_keeps_check_state(tmp_path, capsys):
    path = write_task(tmp_path)
    assert plan_task.main(
        ["set", "TASK-1", "--ac-text", "2", "new criterion", "--project", str(tmp_path)]
    ) == 0
    capsys.readouterr()
    task = model.load_tasks(tmp_path / "backlog" / "tasks")[0]
    assert task.acceptance[0] == (True, "old path"), "первый критерий не тронут"
    assert task.acceptance[1] == (False, "new criterion"), "отметка [ ] сохранена"
    assert "- [ ] #2 new criterion" in path.read_text(encoding="utf-8")


def test_ac_text_rejects_unknown_index(tmp_path, capsys):
    write_task(tmp_path)
    assert plan_task.main(
        ["set", "TASK-1", "--ac-text", "9", "x", "--project", str(tmp_path)]
    ) == 1
    assert "does not exist" in capsys.readouterr().out


def test_ac_replace_counts_and_keeps_states(tmp_path, capsys):
    write_task(tmp_path)
    assert plan_task.main(
        ["set", "TASK-1", "--ac-replace", "old path", "new path", "--project", str(tmp_path)]
    ) == 0
    output = capsys.readouterr().out
    assert "replaced 2 occurrence(s)" in output
    task = model.load_tasks(tmp_path / "backlog" / "tasks")[0]
    assert task.acceptance == [(True, "new path"), (False, "new path")]


def test_ac_replace_zero_is_printed_not_an_error(tmp_path, capsys):
    write_task(tmp_path)
    assert plan_task.main(
        ["set", "TASK-1", "--ac-replace", "absent", "x", "--project", str(tmp_path)]
    ) == 0
    assert "replaced 0 occurrence(s)" in capsys.readouterr().out

