"""plan-shard: шарды из dodo.py и задачи, которые на них ссылаются."""

from __future__ import annotations

import json
import pathlib

import pytest

from planlib import Layout, model, shards
from planlib.cli import shard as plan_shard

DODO = '''"""acceptance"""


def task_s1():
    """первый"""
    return {}


def task_s2():
    """второй"""
    return {}


def helper():
    return {}
'''


def layout_for(tmp_path: pathlib.Path) -> Layout:
    dodo = tmp_path / "dodo.py"
    dodo.write_text(DODO, encoding="utf-8")
    return Layout(
        root=tmp_path,
        state=tmp_path,
        tasks=tmp_path / "backlog" / "tasks",
        dodo=dodo,
        db=tmp_path / ".doit.db",
    )


def seed(layout: Layout) -> None:
    model.create(layout.tasks, title="one", labels=["shard:s1"])
    model.create(layout.tasks, title="two", labels=["shard:s1"])
    model.create(layout.tasks, title="orphan", labels=["shard:nosuch"])
    model.create(layout.tasks, title="unlinked")


def offline(monkeypatch) -> None:
    monkeypatch.setattr(shards, "declared_from_doit", lambda layout: None)
    monkeypatch.setattr(
        plan_shard,
        "acceptance_status",
        lambda layout, shard: ("up-to-date", "") if shard == "s1" else ("run", ""),
    )


def test_declared_from_source_reads_task_functions(tmp_path):
    layout = layout_for(tmp_path)
    assert shards.declared_from_source(layout) == ["s1", "s2"]


def test_build_links_tasks_and_flags_unknown_shards(tmp_path, monkeypatch):
    layout = layout_for(tmp_path)
    seed(layout)
    offline(monkeypatch)

    data = plan_shard.build(layout)
    rows = {row["name"]: row for row in data["shards"]}
    assert set(rows) == {"s1", "s2", "nosuch"}
    assert rows["s1"]["tasks"] == ["TASK-1", "TASK-2"]
    assert rows["s1"]["acceptance"] == "up-to-date"
    assert rows["s2"]["tasks"] == []
    assert rows["nosuch"]["in_dodo"] is False
    assert rows["nosuch"]["acceptance"] == "unknown"
    assert [item["id"] for item in data["unlinked_tasks"]] == ["TASK-4"]


def test_main_prints_missing_shard_note(tmp_path, monkeypatch, capsys):
    layout = layout_for(tmp_path)
    seed(layout)
    offline(monkeypatch)
    monkeypatch.setattr(plan_shard, "layout_from_args", lambda args: layout)

    assert plan_shard.main(["list"]) == 0
    output = capsys.readouterr().out
    assert "s1" in output and "TASK-1" in output
    assert "нет в dodo.py" in output
    assert "без метки shard" in output


def test_main_json(tmp_path, monkeypatch, capsys):
    layout = layout_for(tmp_path)
    seed(layout)
    offline(monkeypatch)
    monkeypatch.setattr(plan_shard, "layout_from_args", lambda args: layout)

    assert plan_shard.main(["list", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["source"] == "ast"
    assert {row["name"] for row in data["shards"]} == {"s1", "s2", "nosuch"}
    assert data["unlinked_tasks"][0]["id"] == "TASK-4"


def test_broken_dodo_is_exit_3(tmp_path, monkeypatch, capsys):
    layout = layout_for(tmp_path)
    layout.dodo.write_text("def task_s1(:\n", encoding="utf-8")
    monkeypatch.setattr(plan_shard, "layout_from_args", lambda args: layout)
    monkeypatch.setattr(shards, "declared_from_doit", lambda layout: None)
    assert plan_shard.main(["list"]) == 3
    assert "dodo.py" in capsys.readouterr().out


def test_strict_lists_hygiene_violations(tmp_path, monkeypatch, capsys):
    layout = layout_for(tmp_path)
    seed(layout)
    offline(monkeypatch)
    monkeypatch.setattr(plan_shard, "layout_from_args", lambda args: layout)

    assert plan_shard.main(["list", "--strict"]) == 1
    output = capsys.readouterr().out
    assert "НАРУШЕНИЯ ГИГИЕНЫ" in output
    assert "шард s2: нет ни одной задачи" in output
    assert "шард nosuch" in output
    assert "TASK-4: нет метки shard" in output


def test_strict_clean_plan_is_zero(tmp_path, monkeypatch):
    layout = layout_for(tmp_path)
    model.create(layout.tasks, title="one", labels=["shard:s1"])
    model.create(layout.tasks, title="two", labels=["shard:s2"])
    offline(monkeypatch)
    monkeypatch.setattr(plan_shard, "layout_from_args", lambda args: layout)

    assert plan_shard.main(["list", "--strict"]) == 0


def test_strict_json_returns_exit_1_and_reports_violations(tmp_path, monkeypatch, capsys):
    layout = layout_for(tmp_path)
    seed(layout)
    offline(monkeypatch)
    monkeypatch.setattr(plan_shard, "layout_from_args", lambda args: layout)

    assert plan_shard.main(["list", "--strict", "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    kinds = {violation["kind"] for violation in data["violations"]}
    assert kinds == {"empty-shard", "unknown-shard", "unlinked-task"}


def test_missing_dodo_is_exit_3(tmp_path, monkeypatch, capsys):
    layout = layout_for(tmp_path)
    layout.dodo.unlink()
    monkeypatch.setattr(plan_shard, "layout_from_args", lambda args: layout)
    assert plan_shard.main(["list"]) == 3
    assert "нет dodo-файла" in capsys.readouterr().out
