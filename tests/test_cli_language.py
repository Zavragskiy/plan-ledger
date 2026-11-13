"""CLI output is English; task data keeps any UTF-8, including Cyrillic."""

from __future__ import annotations

import pytest

from planlib import model
from planlib.cli import gate, status


def seed(tmp_path):
    return model.create(
        tmp_path / "backlog" / "tasks",
        title="Кэш спектров — обработка",
        labels=["shard:s1"],
        acceptance=["acceptance passes"],
    )


def test_status_is_english_and_preserves_cyrillic_title(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    seed(tmp_path)
    assert status.main([]) == 0
    out = capsys.readouterr().out
    assert "Кэш спектров — обработка" in out
    assert "NEXT: TASK-1" in out
    for word in ("План", "СЛЕДУЮЩАЯ", "приёмка", "задач"):
        assert word not in out


def test_gate_stale_section_is_english(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    created = seed(tmp_path)
    created.status = "Done"
    created.check(1)
    model.save(created, tmp_path / "backlog" / "tasks")
    monkeypatch.setattr(gate, "acceptance_state", lambda layout, shard: "run")
    monkeypatch.setattr(
        gate, "acceptance_detail", lambda layout, shard: "changed: src/app.py"
    )

    assert gate.main([]) == 1
    out = capsys.readouterr().out
    assert "STALE" in out
    assert "ПРОТУХЛО" not in out


def test_help_is_english(capsys):
    with pytest.raises(SystemExit):
        gate.main(["--help"])
    out = capsys.readouterr().out
    assert "Plan gate" in out
    assert "ПРОТУХЛО" not in out
