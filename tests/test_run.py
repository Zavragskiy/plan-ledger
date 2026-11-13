"""plan-run: та же команда, что у гейта, и проброс кода возврата."""

from __future__ import annotations

import pathlib
import types

import pytest

from planlib import Layout
from planlib.cli import run as plan_run
from planlib.doit_cli import command


def layout_for(tmp_path: pathlib.Path) -> Layout:
    layout = Layout(
        root=tmp_path,
        state=tmp_path,
        tasks=tmp_path / "backlog" / "tasks",
        dodo=tmp_path / "dodo.py",
        db=tmp_path / ".doit.db",
    )
    layout.dodo.write_text("def task_s1():\n    return {}\n", encoding="utf-8")
    return layout


def test_command_has_explicit_layout_flags(tmp_path):
    layout = layout_for(tmp_path)
    argv = command(layout, "doit", "run", "s1", "s2")
    assert argv[:1] == ["doit"]
    assert argv[argv.index("-f") + 1] == str(layout.dodo)
    assert argv[argv.index("-d") + 1] == str(layout.root)
    assert argv[argv.index("run") + 1] == "--db-file"
    assert argv[argv.index("--db-file") + 1] == str(layout.db)
    assert argv[-2:] == ["s1", "s2"]


def test_run_passes_exit_code_and_prints_command(tmp_path, monkeypatch, capsys):
    layout = layout_for(tmp_path)
    seen = {}

    def fake_run(layout_arg, action, *tasks):
        seen["action"] = action
        seen["tasks"] = tasks
        return types.SimpleNamespace(returncode=1, stdout="-- s1\n", stderr="")

    monkeypatch.setattr("planlib.cli.run.doit_executable", lambda layout: "doit")
    monkeypatch.setattr("planlib.cli.run.run", fake_run)
    monkeypatch.setattr("planlib.cli.run.layout_from_args", lambda args: layout)

    assert plan_run.main(["s1"]) == 1
    assert seen == {"action": "run", "tasks": ("s1",)}
    output = capsys.readouterr().out
    assert "$ doit -f" in output
    assert "--db-file" in output


def test_missing_dodo_is_exit_3(tmp_path, monkeypatch, capsys):
    layout = Layout(
        root=tmp_path,
        state=tmp_path,
        tasks=tmp_path / "backlog" / "tasks",
        dodo=tmp_path / "nope.py",
        db=tmp_path / ".doit.db",
    )
    monkeypatch.setattr("planlib.cli.run.layout_from_args", lambda args: layout)
    assert plan_run.main([]) == 3
    assert "no dodo file" in capsys.readouterr().out


def test_all_runs_dodo_shards_then_plan_extras(tmp_path, monkeypatch):
    from planlib import model

    layout = layout_for(tmp_path)
    model.create(layout.tasks, title="one", labels=["shard:s2"])
    model.create(layout.tasks, title="two", labels=["shard:s1"])
    model.create(layout.tasks, title="three", labels=["shard:s2"])
    seen: dict[str, tuple[str, ...]] = {}

    def fake_run(layout_arg, action, *tasks):
        seen["tasks"] = tasks
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("planlib.cli.run.layout_from_args", lambda args: layout)
    monkeypatch.setattr("planlib.cli.run.doit_executable", lambda layout: "doit")
    monkeypatch.setattr("planlib.cli.run.run", fake_run)

    assert plan_run.main(["--all"]) == 0
    assert seen["tasks"] == ("s1", "s2"), (
        "сначала шарды dodo.py, затем шарды только из плана; без повторов"
    )


def test_all_with_explicit_shard_is_refused(tmp_path, monkeypatch, capsys):
    layout = layout_for(tmp_path)
    monkeypatch.setattr("planlib.cli.run.layout_from_args", lambda args: layout)
    assert plan_run.main(["--all", "s1"]) == 2
    assert "--all" in capsys.readouterr().out


def test_all_warns_about_dodo_shards_without_tasks(tmp_path, monkeypatch, capsys):
    from planlib import model

    layout = layout_for(tmp_path)
    model.create(layout.tasks, title="one", labels=["shard:s1"])
    monkeypatch.setattr("planlib.cli.run.layout_from_args", lambda args: layout)
    monkeypatch.setattr("planlib.cli.run.declared", lambda layout: (["s1", "unit"], "ast"))
    monkeypatch.setattr("planlib.cli.run.doit_executable", lambda layout: "doit")
    monkeypatch.setattr(
        "planlib.cli.run.run",
        lambda layout, action, *tasks: types.SimpleNamespace(
            returncode=0, stdout="", stderr=""
        ),
    )

    assert plan_run.main(["--all"]) == 0
    captured = capsys.readouterr()
    assert "unit" in captured.err
    assert "plan-run --all" in captured.err


def test_all_runs_dodo_shards_even_without_plan_tasks(tmp_path, monkeypatch, capsys):
    """Покрытие из dodo.py: шард без задач всё равно прогоняется."""
    from planlib import model

    layout = layout_for(tmp_path)
    model.create(layout.tasks, title="without shard")
    seen: dict[str, tuple[str, ...]] = {}

    def fake_run(layout_arg, action, *tasks):
        seen["tasks"] = tasks
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("planlib.cli.run.layout_from_args", lambda args: layout)
    monkeypatch.setattr("planlib.cli.run.doit_executable", lambda layout: "doit")
    monkeypatch.setattr("planlib.cli.run.run", fake_run)

    assert plan_run.main(["--all"]) == 0
    assert seen["tasks"] == ("s1",), "шард dodo.py без задач всё равно в прогоне"
    assert "runs them anyway" in capsys.readouterr().err


def test_all_without_any_shards_is_exit_1(tmp_path, monkeypatch, capsys):
    from planlib import model

    layout = layout_for(tmp_path)
    layout.dodo.write_text("VALUE = 1\n", encoding="utf-8")
    model.create(layout.tasks, title="without shard")
    monkeypatch.setattr("planlib.cli.run.layout_from_args", lambda args: layout)
    assert plan_run.main(["--all"]) == 1
    assert "no shards to run" in capsys.readouterr().out


def test_done_runs_only_done_shards_and_prints_skipped(tmp_path, monkeypatch, capsys):
    from planlib import model

    layout = layout_for(tmp_path)
    model.create(layout.tasks, title="done one", labels=["shard:s1"], status="Done")
    model.create(layout.tasks, title="done two", labels=["shard:s2"], status="Done")
    model.create(layout.tasks, title="open one", labels=["shard:s3"])
    seen: dict[str, tuple[str, ...]] = {}

    def fake_run(layout_arg, action, *tasks):
        seen["tasks"] = tasks
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("planlib.cli.run.layout_from_args", lambda args: layout)
    monkeypatch.setattr("planlib.cli.run.doit_executable", lambda layout: "doit")
    monkeypatch.setattr("planlib.cli.run.run", fake_run)

    assert plan_run.main(["--done"]) == 0
    assert seen["tasks"] == ("s1", "s2"), "только шарды Done-задач"
    captured = capsys.readouterr()
    assert "s1" in captured.out and "s2" in captured.out
    assert "skipped (not Done): s3" in captured.err, "пропущенные шарды не молчат"


def test_done_without_done_tasks_is_exit_1(tmp_path, monkeypatch, capsys):
    from planlib import model

    layout = layout_for(tmp_path)
    model.create(layout.tasks, title="open", labels=["shard:s1"])
    monkeypatch.setattr("planlib.cli.run.layout_from_args", lambda args: layout)
    assert plan_run.main(["--done"]) == 1
    assert "no Done tasks" in capsys.readouterr().out


def test_done_cannot_be_combined_with_all_or_list(tmp_path, monkeypatch, capsys):
    layout = layout_for(tmp_path)
    monkeypatch.setattr("planlib.cli.run.layout_from_args", lambda args: layout)
    assert plan_run.main(["--done", "--all"]) == 2
    assert "--done" in capsys.readouterr().out


def test_missing_doit_is_exit_3(tmp_path, monkeypatch, capsys):
    layout = layout_for(tmp_path)
    monkeypatch.setattr("planlib.cli.run.layout_from_args", lambda args: layout)
    monkeypatch.setattr("planlib.cli.run.doit_executable", lambda layout: None)
    assert plan_run.main(["s1"]) == 3
    assert "doit not found" in capsys.readouterr().out
