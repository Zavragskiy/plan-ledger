"""plan-init: скаффолд, идемпотентность, pyproject, dry-run."""

from __future__ import annotations

import pathlib

from planlib.cli import init as plan_init


def test_scaffolds_state_dodo_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert plan_init.main([]) == 0
    assert (tmp_path / "plan-ledger.toml").is_file()
    # задачи видны в корне проекта, а не спрятаны в .planlib/backlog/tasks
    assert (tmp_path / "backlog" / "tasks" / ".gitkeep").is_file()
    assert (tmp_path / "dodo.py").is_file()
    text = (tmp_path / "plan-ledger.toml").read_text(encoding="utf-8")
    assert 'state = ".planlib"' in text
    assert 'tasks_base = "config"' in text
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
    assert "already exists" in capsys.readouterr().out


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


def test_with_placeholder_creates_bootstrap_task(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert plan_init.main(["--with-placeholder"]) == 0
    from planlib import model

    tasks = model.load_tasks(tmp_path / "backlog" / "tasks")
    assert [task.id for task in tasks] == ["TASK-1"]
    assert tasks[0].slug == "bootstrap-placeholder"
    assert "plan-init --with-placeholder" in tasks[0].description


def test_placeholder_does_not_duplicate_existing_tasks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    plan_init.main([])
    from planlib import model

    model.create(tmp_path / "backlog" / "tasks", title="настоящая задача")
    assert plan_init.main(["--with-placeholder"]) == 0
    assert len(model.load_tasks(tmp_path / "backlog" / "tasks")) == 1


def test_placeholder_lets_first_commit_pass_gate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert plan_init.main(["--with-placeholder"]) == 0
    from planlib.cli import gate

    assert gate.main([]) == 0


def test_dry_run_with_placeholder_writes_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert plan_init.main(["--dry-run", "--with-placeholder"]) == 0
    assert not (tmp_path / "backlog" / "tasks").exists()
    assert "placeholder" in capsys.readouterr().out


def test_tasks_flag_is_root_relative_not_state_relative(tmp_path, monkeypatch):
    """Та самая ловушка: --tasks backlog/tasks не должен уходить в .planlib/."""
    monkeypatch.chdir(tmp_path)
    assert plan_init.main(["--state", ".planlib", "--tasks", "plan/tasks"]) == 0
    assert (tmp_path / "plan" / "tasks" / ".gitkeep").is_file()
    assert not (tmp_path / ".planlib" / "plan").exists()


def test_tasks_base_state_restores_hidden_layout(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert plan_init.main(["--tasks-base", "state"]) == 0
    assert (tmp_path / ".planlib" / "backlog" / "tasks" / ".gitkeep").is_file()
    text = (tmp_path / "plan-ledger.toml").read_text(encoding="utf-8")
    assert 'tasks_base = "state"' in text


def test_state_dir_is_created_for_doit_db(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    plan_init.main([])
    # задачи вынесены в корень, но БД doit живёт в state — каталог обязан существовать
    assert (tmp_path / ".planlib").is_dir()
    # пустой каталог не переживает clone: keep-file делает state отслеживаемым
    assert (tmp_path / ".planlib" / ".gitkeep").is_file()


def test_existing_glob_cache_ignore_is_not_duplicated(tmp_path, monkeypatch):
    (tmp_path / ".gitignore").write_text("**/__pycache__\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert plan_init.main([]) == 0
    text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert text.count("__pycache__") == 1
    assert ".planlib/.doit.db*" in text


def test_acceptance_runs_right_after_init(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    plan_init.main([])
    from planlib.cli import run as plan_run

    assert plan_run.main(["--quiet"]) == 0


def test_acceptance_recreates_missing_state_dir(tmp_path, monkeypatch):
    """A fresh clone has no empty state dir; the first doit call must recreate it."""
    monkeypatch.chdir(tmp_path)
    plan_init.main([])
    import shutil

    shutil.rmtree(tmp_path / ".planlib")
    from planlib.cli import run as plan_run

    assert plan_run.main(["--quiet"]) == 0
    assert (tmp_path / ".planlib").is_dir()


def test_state_outside_root_is_error(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sub").mkdir()
    assert plan_init.main(["--root", "sub", "--state", "state"]) == 3
    assert "must be inside" in capsys.readouterr().out
