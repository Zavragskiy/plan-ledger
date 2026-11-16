"""Notes: рукописное тело секции переживает правку задачи без нормализации."""

from __future__ import annotations

import pathlib

import yaml

from planlib import model
from planlib.cli import task as plan_task

BODY = (
    "**What moved.** `domains/tool` is born with four modules.\n"
    "The second line of the same paragraph.\n"
    "\n"
    "**What stayed.** The viser nodes and their names."
)


def write_task(tmp_path: pathlib.Path, body: str) -> pathlib.Path:
    tasks_dir = tmp_path / "backlog" / "tasks"
    tasks_dir.mkdir(parents=True)
    meta = {
        "id": "TASK-1",
        "title": "notes",
        "status": "To Do",
        "labels": ["shard:s1"],
        "created_date": "2026-11-13 10:00",
        "updated_date": "2026-11-13 10:00",
    }
    path = tasks_dir / "task-1.md"
    path.write_text(
        "---\n" + yaml.safe_dump(meta, allow_unicode=True) + "---\n"
        "## Acceptance Criteria\n\n- [ ] #1 passes\n\n## Notes\n\n" + body + "\n",
        encoding="utf-8",
    )
    return path


def test_parse_keeps_the_notes_body_verbatim(tmp_path):
    path = write_task(tmp_path, BODY)
    task = model.parse(path)
    assert task.notes_body == BODY
    assert task.notes == [], "строки больше не режутся на буллеты"
    assert "**What moved.**" in task.to_markdown()
    assert BODY in task.to_markdown()


def test_set_preserves_hand_written_notes(tmp_path, monkeypatch, capsys):
    path = write_task(tmp_path, BODY)
    monkeypatch.setattr("planlib.cli.task.acceptance_state", lambda layout, shard: "up-to-date")
    assert plan_task.main(
        [
            "set",
            "TASK-1",
            "--status",
            "Done",
            "--check-ac",
            "1",
            "--outcome",
            "closed",
            "--project",
            str(tmp_path),
        ]
    ) == 0
    capsys.readouterr()
    text = path.read_text(encoding="utf-8")
    assert "**What moved.** `domains/tool` is born with four modules." in text
    assert "**What stayed.** The viser nodes and their names." in text
    assert "\n\n**What stayed.**" in text, "пустая строка между абзацами сохранена"
    assert "- What moved" not in text, "абзац не превратился в буллет"
    assert "- **What moved" not in text, "ведущий ** не съеден"


def test_note_flag_appends_bullets_after_the_body(tmp_path, capsys):
    path = write_task(tmp_path, BODY)
    assert plan_task.main(
        ["set", "TASK-1", "--note", "session 7d23: plan-run --all", "--project", str(tmp_path)]
    ) == 0
    capsys.readouterr()
    text = path.read_text(encoding="utf-8")
    assert text.rstrip().endswith("- session 7d23: plan-run --all")
    assert BODY in text
    assert "\n\n- session 7d23" in text
