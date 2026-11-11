"""Интеграция с реальным doit: state в .planlib, относительные file_dep, stale."""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

from planlib import model, resolve
from planlib.acceptance import doit_executable
from planlib.cli import gate

DODO = '''"""acceptance for layout test"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent{parent_suffix}
DB = pathlib.Path(__file__).resolve().parent / {db_rel!r}
DOIT_CONFIG = {{"verbosity": 0, "dep_file": str(DB)}}


def task_s1():
    return {{
        "actions": [[sys.executable, "-c", "print('ok')"]],
        "file_dep": ["src/app.py"],
    }}
'''


def build(tmp_path: pathlib.Path, nested: bool) -> pathlib.Path:
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    state = root / ".planlib"
    tasks = state / "backlog" / "tasks"
    tasks.mkdir(parents=True)
    (root / "plan-ledger.toml").write_text(
        "\n".join(
            [
                "[plan-ledger]",
                'root = "."',
                'state = ".planlib"',
                'tasks = "backlog/tasks"',
                f'dodo = "{".planlib/dodo.py" if nested else "dodo.py"}"',
                'db = ".doit.db"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    dodo_dir = state if nested else root
    dodo = dodo_dir / "dodo.py"
    dodo.write_text(
        DODO.format(
            parent_suffix=".parent" if nested else "",
            db_rel=".doit.db" if nested else ".planlib/.doit.db",
        ),
        encoding="utf-8",
    )
    model.create(
        tasks,
        title="s1: acceptance sample",
        labels=["shard:s1"],
        acceptance=["acceptance passes"],
        status="Done",
    )
    return root


def run_acceptance(root: pathlib.Path) -> None:
    layout = resolve(start=root)
    executable = doit_executable(layout)
    assert executable, "doit должен быть установлен в тестовом окружении"
    result = subprocess.run(
        [executable, "-f", str(layout.dodo), "-d", str(layout.root), "s1"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("nested", [False, True], ids=["dodo-in-root", "dodo-in-state"])
def test_gate_uses_config_and_relative_paths(tmp_path, monkeypatch, capsys, nested):
    root = build(tmp_path, nested)
    monkeypatch.chdir(root)

    assert gate.main([]) == 1, "до прогона приёмки Done-задача обязана быть stale"

    run_acceptance(root)
    capsys.readouterr()
    assert gate.main([]) == 0

    (root / "src" / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
    capsys.readouterr()
    assert gate.main([]) == 1
    output = capsys.readouterr().out
    assert "src/app.py" in output
    assert str(root / "src" / "app.py") not in output, "пути в отчёте должны быть относительными"
