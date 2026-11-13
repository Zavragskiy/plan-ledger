"""plan-task: явный id, slug (стабильное имя файла) и --shard в new/set."""

from __future__ import annotations

import pathlib

from planlib import model
from planlib.cli import task as plan_task


def tasks_dir(root: pathlib.Path) -> pathlib.Path:
    return root / "backlog" / "tasks"


def test_new_with_id_slug_and_shard(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert (
        plan_task.main(
            [
                "new",
                "Убрать файловые исключения из гейта сложности",
                "--id",
                "QUALITY-GATE",
                "--slug",
                "quality-gate",
                "--shard",
                "gate",
                "--ac",
                "гейт сложности проходит",
            ]
        )
        == 0
    )
    files = sorted(path.name for path in tasks_dir(tmp_path).glob("*.md"))
    assert files == ["quality-gate.md"], "явный slug задаёт имя файла целиком"
    task = model.load_tasks(tasks_dir(tmp_path))[0]
    assert task.id == "QUALITY-GATE"
    assert task.slug == "quality-gate"
    assert task.shard == "gate"
    assert "slug: quality-gate" in (tasks_dir(tmp_path) / "quality-gate.md").read_text(
        encoding="utf-8"
    )


def test_shard_alias_is_same_as_label(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    plan_task.main(["new", "one", "-l", "shard:s1", "-l", "extra"])
    plan_task.main(["new", "two", "--shard", "s2"])
    tasks = model.load_tasks(tasks_dir(tmp_path))
    assert tasks[0].shard == "s1"
    assert tasks[0].labels == ["shard:s1", "extra"]
    assert tasks[1].labels == ["shard:s2"]


def test_duplicate_id_is_refused(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert plan_task.main(["new", "one", "--id", "QUALITY-GATE"]) == 0
    capsys.readouterr()
    assert plan_task.main(["new", "two", "--id", "QUALITY-GATE"]) == 1
    assert "already exists" in capsys.readouterr().out
    assert len(model.load_tasks(tasks_dir(tmp_path))) == 1


def test_invalid_slug_and_shard_are_refused(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert plan_task.main(["new", "one", "--slug", "Плохой Slug"]) == 1
    assert plan_task.main(["new", "two", "--shard", "два слова"]) == 1
    assert not tasks_dir(tmp_path).exists()
    assert "slug" in capsys.readouterr().out


def test_set_shard_replaces_previous(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    plan_task.main(["new", "one", "-l", "shard:s1", "-l", "keep"])
    assert plan_task.main(["set", "TASK-1", "--shard", "gate"]) == 0
    task = model.load_tasks(tasks_dir(tmp_path))[0]
    assert task.shard == "gate"
    assert "keep" in task.labels
    assert "shard:s1" not in task.labels


def test_set_slug_renames_file_without_losing_content(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    plan_task.main(["new", "Длинный заголовок задачи", "--ac", "first"])
    old = next(tasks_dir(tmp_path).glob("*.md"))
    assert plan_task.main(["set", "TASK-1", "--slug", "short-name"]) == 0
    assert not old.exists()
    renamed = tasks_dir(tmp_path) / "short-name.md"
    assert renamed.is_file()
    task = model.load_tasks(tasks_dir(tmp_path))[0]
    assert task.slug == "short-name"
    assert task.acceptance == [(False, "first")]


def test_task_can_be_addressed_by_slug(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    plan_task.main(["new", "one", "--slug", "quality-gate"])
    assert plan_task.main(["set", "quality-gate", "--status", "In Progress"]) == 0
    assert model.load_tasks(tasks_dir(tmp_path))[0].status == "In Progress"


def test_rename_into_existing_file_is_refused(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    plan_task.main(["new", "one", "--slug", "taken"])
    plan_task.main(["new", "two"])
    capsys.readouterr()
    assert plan_task.main(["set", "TASK-2", "--slug", "taken"]) == 1
    assert "already used" in capsys.readouterr().out
    assert len(list(tasks_dir(tmp_path).glob("*.md"))) == 2
