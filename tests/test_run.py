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
    assert "нет dodo-файла" in capsys.readouterr().out


def test_missing_doit_is_exit_3(tmp_path, monkeypatch, capsys):
    layout = layout_for(tmp_path)
    monkeypatch.setattr("planlib.cli.run.layout_from_args", lambda args: layout)
    monkeypatch.setattr("planlib.cli.run.doit_executable", lambda layout: None)
    assert plan_run.main(["s1"]) == 3
    assert "doit не найден" in capsys.readouterr().out
