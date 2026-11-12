"""Конфиг и раскладка: поиск, приоритет, override'ы, ошибки."""

from __future__ import annotations

import pathlib

import pytest

from planlib.config import LayoutError, resolve


def write_config(directory: pathlib.Path, **fields: str) -> pathlib.Path:
    lines = ["[plan-ledger]"] + [f'{key} = "{value}"' for key, value in fields.items()]
    path = directory / "plan-ledger.toml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_resolves_plan_ledger_toml(tmp_path):
    write_config(
        tmp_path, root=".", state=".planlib", tasks="backlog/tasks", dodo="dodo.py", db=".doit.db"
    )
    layout = resolve(start=tmp_path)
    assert layout.root == tmp_path
    assert layout.state == tmp_path / ".planlib"
    # tasks по умолчанию — от каталога конфига, а не от state: план не прячется
    assert layout.tasks == tmp_path / "backlog" / "tasks"
    assert layout.dodo == tmp_path / "dodo.py"
    assert layout.db == tmp_path / ".planlib" / ".doit.db"
    assert layout.config_file == tmp_path / "plan-ledger.toml"


def test_tasks_base_state_keeps_old_layout(tmp_path):
    write_config(tmp_path, state=".planlib", tasks="backlog/tasks", tasks_base="state")
    assert resolve(start=tmp_path).tasks == tmp_path / ".planlib" / "backlog" / "tasks"


def test_tasks_base_root_uses_code_root(tmp_path):
    (tmp_path / "app").mkdir()
    write_config(tmp_path, root="app", state=".planlib", tasks="backlog/tasks", tasks_base="root")
    assert resolve(start=tmp_path).tasks == tmp_path / "app" / "backlog" / "tasks"


def test_tasks_absolute_path(tmp_path):
    absolute = (tmp_path / "elsewhere").as_posix()
    write_config(tmp_path, state=".planlib", tasks=absolute)
    assert resolve(start=tmp_path).tasks == tmp_path / "elsewhere"


def test_unknown_tasks_base_is_error(tmp_path):
    write_config(tmp_path, tasks_base="somewhere")
    with pytest.raises(LayoutError, match="tasks_base"):
        resolve(start=tmp_path)


def test_resolves_pyproject_table(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n\n[tool.plan-ledger]\nstate = ".planlib"\n', encoding="utf-8"
    )
    layout = resolve(start=tmp_path)
    assert layout.state == tmp_path / ".planlib"
    assert layout.config_file == tmp_path / "pyproject.toml"


def test_plan_ledger_toml_wins_over_pyproject(tmp_path):
    write_config(tmp_path, state="from-toml")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.plan-ledger]\nstate = "from-pyproject"\n', encoding="utf-8"
    )
    assert resolve(start=tmp_path).state == tmp_path / "from-toml"


def test_search_walks_up(tmp_path):
    write_config(tmp_path, state=".planlib")
    nested = tmp_path / "src" / "deep"
    nested.mkdir(parents=True)
    layout = resolve(start=nested)
    assert layout.root == tmp_path
    assert layout.state == tmp_path / ".planlib"


def test_project_overrides_state_but_keeps_root(tmp_path):
    write_config(tmp_path, root=".", state=".planlib")
    layout = resolve(project=tmp_path / "alt", start=tmp_path)
    assert layout.root == tmp_path
    assert layout.state == tmp_path / "alt"


def test_legacy_layout_without_config(tmp_path):
    layout = resolve(project=tmp_path, start=tmp_path)
    assert layout.root == tmp_path
    assert layout.state == tmp_path
    assert layout.tasks == tmp_path / "backlog" / "tasks"
    assert layout.config_file is None


def test_unknown_key_is_error(tmp_path):
    (tmp_path / "plan-ledger.toml").write_text('[plan-ledger]\nfoo = "bar"\n', encoding="utf-8")
    with pytest.raises(LayoutError, match="неизвестные ключи"):
        resolve(start=tmp_path)


def test_broken_toml_is_error(tmp_path):
    (tmp_path / "plan-ledger.toml").write_text("[plan-ledger\n", encoding="utf-8")
    with pytest.raises(LayoutError, match="некорректный TOML"):
        resolve(start=tmp_path)


def test_explicit_config(tmp_path):
    config = write_config(tmp_path, state=".state")
    layout = resolve(config=config, start=tmp_path.parent)
    assert layout.config_file == config
    assert layout.state == tmp_path / ".state"


def test_missing_config_file_is_error(tmp_path):
    with pytest.raises(LayoutError, match="конфиг не найден"):
        resolve(config=tmp_path / "nope.toml", start=tmp_path)
