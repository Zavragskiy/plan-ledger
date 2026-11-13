"""Приёмка: точный вызов doit, резолв путей, разбор состояний."""

from __future__ import annotations

import pathlib
import types

import pytest

from planlib import Layout
from planlib.acceptance import acceptance_status, doit_executable


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


def fake_run(monkeypatch, stdout: str = "", stderr: str = "", returncode: int = 0):
    calls: list[tuple[list[str], dict]] = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr("planlib.doit_cli.subprocess.run", runner)
    return calls


def test_invocation_is_explicit(tmp_path, monkeypatch):
    layout = layout_for(tmp_path)
    calls = fake_run(monkeypatch, stdout="status     : up-to-date")
    assert acceptance_status(layout, "s1")[0] == "up-to-date"
    command, kwargs = calls[0]
    assert command[command.index("-f") + 1] == str(layout.dodo)
    assert command[command.index("-d") + 1] == str(layout.root)
    assert command[command.index("--db-file") + 1] == str(layout.db)
    assert "info" in command
    assert command[-1] == "s1"
    assert kwargs["cwd"] == layout.root


def test_changed_paths_are_relative(tmp_path, monkeypatch):
    layout = layout_for(tmp_path)
    stdout = (
        "status     : run\n"
        " * The following file dependencies have changed:\n"
        f"    - {tmp_path / 'src' / 'app.py'}\n"
    )
    fake_run(monkeypatch, stdout=stdout)
    state, detail = acceptance_status(layout, "s1")
    assert state == "run"
    assert detail == "changed: src/app.py"


def test_missing_deps_are_error(tmp_path, monkeypatch):
    layout = layout_for(tmp_path)
    stdout = (
        "status     : error\n"
        " * The following file dependencies are missing:\n"
        "    - src/gone.py\n"
    )
    fake_run(monkeypatch, stdout=stdout)
    state, detail = acceptance_status(layout, "s1")
    assert state == "error"
    assert "src/gone.py" in detail


def test_unknown_task(tmp_path, monkeypatch):
    layout = layout_for(tmp_path)
    fake_run(monkeypatch, stdout="ERROR: Unknown task 's9'", returncode=3)
    assert acceptance_status(layout, "s9")[0] == "unknown"


def test_missing_shard_traceback_is_clean_unknown(tmp_path, monkeypatch):
    layout = layout_for(tmp_path)
    stderr = (
        "Traceback (most recent call last):\n"
        '  File "dodo.py", line 12, in <module>\n'
        "    task = loader[shard]\n"
        "KeyError: 'px'\n"
    )
    fake_run(monkeypatch, stderr=stderr, returncode=1)
    state, detail = acceptance_status(layout, "px")
    assert state == "unknown"
    assert "KeyError: 'px'" in detail
    assert "Traceback" not in detail
    assert "File " not in detail


def test_dodo_bug_traceback_is_clean_error(tmp_path, monkeypatch):
    layout = layout_for(tmp_path)
    stderr = (
        "Traceback (most recent call last):\n"
        '  File "dodo.py", line 3, in <module>\n'
        "ValueError: boom\n"
    )
    fake_run(monkeypatch, stderr=stderr, returncode=1)
    state, detail = acceptance_status(layout, "s1")
    assert state == "error"
    assert detail == "doit: ValueError: boom"


def test_doit_executable_prefers_project_venv(tmp_path):
    layout = layout_for(tmp_path)
    venv_doit = tmp_path / ".venv" / ("Scripts" if __import__("os").name == "nt" else "bin") / (
        "doit.exe" if __import__("os").name == "nt" else "doit"
    )
    venv_doit.parent.mkdir(parents=True)
    venv_doit.write_text("", encoding="utf-8")
    assert doit_executable(layout) == str(venv_doit)


def test_long_changed_list_is_truncated(tmp_path, monkeypatch):
    layout = layout_for(tmp_path)
    lines = "".join(f"    - src/f{index}.py\n" for index in range(250))
    stdout = (
        "status     : run\n"
        " * The following file dependencies have changed:\n" + lines
    )
    fake_run(monkeypatch, stdout=stdout)
    state, detail = acceptance_status(layout, "s1")
    assert state == "run"
    assert "src/f0.py" in detail
    assert "src/f10.py" not in detail
    assert "… and 240 more" in detail


def test_missing_list_is_truncated_too(tmp_path, monkeypatch):
    layout = layout_for(tmp_path)
    lines = "".join(f"    - src/g{index}.py\n" for index in range(20))
    stdout = (
        "status     : error\n"
        " * The following file dependencies are missing:\n" + lines
    )
    fake_run(monkeypatch, stdout=stdout)
    state, detail = acceptance_status(layout, "s1")
    assert state == "error"
    assert "… and 10 more" in detail
