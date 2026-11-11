"""plan-init: скаффолд, идемпотентность, pyproject, dry-run."""

from __future__ import annotations

import pathlib

from planlib.cli import init as plan_init


def test_scaffolds_state_dodo_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert plan_init.main([]) == 0
    assert (tmp_path / "plan-ledger.toml").is_file()
    assert (tmp_path / ".planlib" / "backlog" / "tasks" / ".gitkeep").is_file()
    assert (tmp_path / "dodo.py").is_file()
    text = (tmp_path / "plan-ledger.toml").read_text(encoding="utf-8")
    assert 'state = ".planlib"' in text
    dodo = (tmp_path / "dodo.py").read_text(encoding="utf-8")
    assert "dep_file" in dodo and ".doit.db" in dodo
    gitignore = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert ".planlib/.doit.db*" in gitignore


def test_second_run_is_idempotent(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    plan_init.main([])
    before = (tmp_path / "dodo.py").read_text(encoding="utf-8")
    capsys.readouterr()
    assert plan_init.main([]) == 0
    assert (tmp_path / "dodo.py").read_text(encoding="utf-8") == before
    assert "уже есть" in capsys.readouterr().out


def test_pyproject_mode_appends_table(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\n', encoding="utf-8")
    assert plan_init.main(["--config", "pyproject"]) == 0
    text = (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert '[project]\nname = "demo"' in text
    assert "[tool.plan-ledger]" in text


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert plan_init.main(["--dry-run"]) == 0
    assert not (tmp_path / "plan-ledger.toml").exists()
    assert not (tmp_path / ".planlib").exists()
    assert not (tmp_path / "dodo.py").exists()


def test_state_outside_root_is_error(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sub").mkdir()
    assert plan_init.main(["--root", "sub", "--state", "state"]) == 3
    assert "внутри" in capsys.readouterr().out
