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
        assert "СЛЕДУЮЩАЯ: TASK-1" in result.stdout


def test_check_project_flag(tmp_path):
    write_task(tmp_path)
    result = run("planlib.cli.gate", ["--project", str(tmp_path)])
    assert result.returncode == 0, result.stderr
