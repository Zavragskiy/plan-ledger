"""plan-digest: компактный срез, счётчики, --limit/--active/--since/--task."""

from __future__ import annotations

import datetime as dt
import json
import pathlib

import yaml

from planlib.cli import digest


def now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


def seed(tmp_path: pathlib.Path) -> None:
    tasks_dir = tmp_path / "backlog" / "tasks"
    tasks_dir.mkdir(parents=True)
    tasks = [
        {"id": "TASK-1", "title": "open s1", "status": "To Do", "labels": ["shard:s1"]},
        {
            "id": "TASK-2",
            "title": "done s1",
            "status": "Done",
            "labels": ["shard:s1"],
            "closed_date": now(),
            "closeout": {"outcome": "did it", "files": ["src/a.py"]},
        },
        {
            "id": "TASK-3",
            "title": "done s2 without closeout",
            "status": "Done",
            "labels": ["shard:s2"],
            "closed_date": "2020-01-01 00:00",
        },
        {"id": "TASK-4", "title": "no shard", "status": "To Do"},
    ]
    for data in tasks:
        data.setdefault("created_date", "2026-11-13 10:00")
        data.setdefault("updated_date", "2026-11-13 10:00")
        (tasks_dir / f"{data['id'].lower()}.md").write_text(
            "---\n" + yaml.safe_dump(data, allow_unicode=True) + "---\n", encoding="utf-8"
        )


def patch(monkeypatch, *, detail: str = "changed: src/a.py") -> None:
    monkeypatch.setattr(
        "planlib.cli.digest.acceptance_state", lambda layout, shard: "up-to-date"
    )
    monkeypatch.setattr(
        "planlib.cli.digest.acceptance_states",
        lambda layout: {"s1": "up-to-date", "s2": "run"},
    )
    monkeypatch.setattr("planlib.cli.digest.declared", lambda layout: (["s1", "s2"], "ast"))
    monkeypatch.setattr(
        "planlib.cli.digest.acceptance_detail", lambda layout, shard: detail
    )


def run_json(tmp_path: pathlib.Path, monkeypatch, capsys, *args: str) -> dict:
    patch(monkeypatch)
    assert digest.main(["--project", str(tmp_path), "--json", *args]) == 0
    return json.loads(capsys.readouterr().out)


def test_totals_and_rows(tmp_path, monkeypatch, capsys):
    seed(tmp_path)
    data = run_json(tmp_path, monkeypatch, capsys)
    assert data["totals"]["total"] == 4
    assert data["totals"]["done"] == 2
    assert data["totals"]["open"] == 2
    assert data["totals"]["no_closeout"] == 1
    assert data["totals"]["shards"] == {"declared": 2, "proven": 1}
    rows = {row["id"]: row for row in data["tasks"]}
    assert rows["TASK-2"]["outcome"] == "did it"
    assert rows["TASK-2"]["closed"]
    assert rows["TASK-1"].get("outcome") is None
    assert data["next"] == "TASK-1"


def test_limit_keeps_totals(tmp_path, monkeypatch, capsys):
    seed(tmp_path)
    data = run_json(tmp_path, monkeypatch, capsys, "--limit", "2")
    assert data["shown"] == 2
    assert len(data["tasks"]) == 2
    assert data["hidden"]["limit"] == 2
    assert data["totals"]["total"] == 4


def test_active_hides_done_without_hiding_totals(tmp_path, monkeypatch, capsys):
    seed(tmp_path)
    data = run_json(tmp_path, monkeypatch, capsys, "--active")
    assert {row["status"] for row in data["tasks"]} == {"To Do"}
    assert data["hidden"]["active"] == 2
    assert data["totals"]["done"] == 2


def test_since_filters_done_by_closed_date(tmp_path, monkeypatch, capsys):
    seed(tmp_path)
    data = run_json(tmp_path, monkeypatch, capsys, "--since", "30d")
    ids = {row["id"] for row in data["tasks"]}
    assert "TASK-2" in ids, "свежий Done остаётся"
    assert "TASK-3" not in ids, "Done 2020 года скрыт"
    assert data["hidden"]["since"] == 1


def test_task_relation_uses_shard(tmp_path, monkeypatch, capsys):
    seed(tmp_path)
    data = run_json(tmp_path, monkeypatch, capsys, "--task", "TASK-1")
    ids = [row["id"] for row in data["tasks"]]
    assert ids == ["TASK-1", "TASK-2"], "цель и связанный Done по общему шарду"
    related = next(row for row in data["tasks"] if row["id"] == "TASK-2")
    assert related["why"] == ["same shard s1"]
    assert data["hidden"]["task"] == 2


def test_task_relation_uses_files(tmp_path, monkeypatch, capsys):
    tasks_dir = tmp_path / "backlog" / "tasks"
    tasks_dir.mkdir(parents=True)
    for task_id, shard in (("TASK-1", "s9"), ("TASK-2", "s1")):
        data = {
            "id": task_id,
            "title": task_id,
            "status": "Done",
            "labels": [f"shard:{shard}"],
            "created_date": "2026-11-13 10:00",
            "updated_date": "2026-11-13 10:00",
            "closed_date": now(),
            "closeout": {"outcome": "done", "files": ["src/a.py"]},
        }
        (tasks_dir / f"{task_id.lower()}.md").write_text(
            "---\n" + yaml.safe_dump(data, allow_unicode=True) + "---\n", encoding="utf-8"
        )
    data = run_json(tmp_path, monkeypatch, capsys, "--task", "TASK-1")
    related = [row for row in data["tasks"] if row["id"] == "TASK-2"]
    assert related and related[0]["why"] == ["files src/a.py"]


def test_with_detail_is_opt_in(tmp_path, monkeypatch, capsys):
    seed(tmp_path)
    data = run_json(tmp_path, monkeypatch, capsys)
    assert all("detail" not in row for row in data["tasks"])

    data = run_json(tmp_path, monkeypatch, capsys, "--with-detail")
    row = next(row for row in data["tasks"] if row["id"] == "TASK-1")
    assert row["detail"] == "changed: src/a.py"


def test_text_prints_totals_and_proven_shards(tmp_path, monkeypatch, capsys):
    seed(tmp_path)
    patch(monkeypatch)
    assert digest.main(["--project", str(tmp_path)]) == 0
    text = capsys.readouterr().out
    assert "total 4: done 2, open 2" in text
    assert "shards proven: 1/2" in text
    assert "did it" in text
    assert "NEXT: TASK-1" in text
