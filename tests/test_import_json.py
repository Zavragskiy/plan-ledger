"""plan-import --from-json: находки гейта → задачи (группировка, dedupe, ошибки)."""

from __future__ import annotations

import json
import pathlib

from planlib import model
from planlib.cli import importer

FINDINGS = [
    {"file": "src/app.py", "line": 12, "rule": "C901", "message": "complexity 14 > 10"},
    {
        "file": "src/app.py",
        "line": 40,
        "rule": "C901",
        "message": "complexity 12 > 10",
        "acceptance": ["app.py разбит на модули"],
    },
    {"file": "src/util.py", "line": 3, "rule": "xenon", "message": "block too complex"},
]


def report(tmp_path: pathlib.Path, payload) -> pathlib.Path:
    path = tmp_path / "findings.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def tasks(tmp_path: pathlib.Path) -> list[model.Task]:
    return model.load_tasks(tmp_path / "backlog" / "tasks")


def test_dry_run_creates_nothing(tmp_path, capsys):
    path = report(tmp_path, FINDINGS)
    assert importer.main(["--from-json", str(path), "--project", str(tmp_path)]) == 0
    assert not (tmp_path / "backlog" / "tasks").exists()
    assert "к созданию: 3" in capsys.readouterr().out


def test_apply_creates_tasks_with_shard_and_references(tmp_path):
    path = report(tmp_path, FINDINGS)
    assert (
        importer.main(
            ["--from-json", str(path), "--project", str(tmp_path), "--apply", "--shard", "gate"]
        )
        == 0
    )
    created = tasks(tmp_path)
    assert len(created) == 3
    first = created[0]
    assert first.shard == "gate"
    assert "gate" in first.labels
    assert "rule:C901" in first.labels
    assert first.references == ["src/app.py:12"]
    assert first.title == "C901: complexity 14 > 10"
    assert first.acceptance == [(False, "находка устранена: C901 src/app.py:12")]
    second = created[1]
    assert second.acceptance == [(False, "app.py разбит на модули")]


def test_second_apply_is_idempotent(tmp_path, capsys):
    path = report(tmp_path, FINDINGS)
    args = ["--from-json", str(path), "--project", str(tmp_path), "--apply"]
    assert importer.main(args) == 0
    capsys.readouterr()
    assert importer.main(args) == 0
    output = capsys.readouterr().out
    assert "пропущено: 3" in output
    assert len(tasks(tmp_path)) == 3


def test_group_by_file_creates_one_task_per_file(tmp_path):
    path = report(tmp_path, FINDINGS)
    assert (
        importer.main(
            [
                "--from-json",
                str(path),
                "--project",
                str(tmp_path),
                "--apply",
                "--group-by",
                "file",
                "--shard",
                "gate",
            ]
        )
        == 0
    )
    created = tasks(tmp_path)
    assert len(created) == 2
    app_task = next(task for task in created if "app.py" in task.title)
    assert len(app_task.acceptance) == 2
    assert app_task.shard == "gate"
    assert [task.slug for task in created] == ["gate-src-app", "gate-src-util"]
    assert "src/app.py:12" in app_task.references


NESTED = [
    {
        "file": "app/mover_modules/mover_bases/mover_mixins.py",
        "line": 1,
        "rule": "C901",
        "message": "a",
    },
    {
        "file": "app/other/mover_mixins.py",
        "line": 2,
        "rule": "C901",
        "message": "b",
    },
]


def test_slug_depth_takes_last_segments(tmp_path):
    path = report(tmp_path, NESTED)
    assert (
        importer.main(
            [
                "--from-json",
                str(path),
                "--project",
                str(tmp_path),
                "--apply",
                "--group-by",
                "file",
                "--slug-depth",
                "2",
            ]
        )
        == 0
    )
    assert [task.slug for task in tasks(tmp_path)] == [
        "gate-mover-bases-mover-mixins",
        "gate-other-mover-mixins",
    ]


def test_slug_depth_one_uses_basename_and_dedupes(tmp_path):
    path = report(tmp_path, NESTED)
    assert (
        importer.main(
            [
                "--from-json",
                str(path),
                "--project",
                str(tmp_path),
                "--apply",
                "--group-by",
                "file",
                "--slug-depth",
                "1",
            ]
        )
        == 0
    )
    assert sorted(task.slug for task in tasks(tmp_path)) == [
        "gate-mover-mixins",
        "gate-mover-mixins-2",
    ]


def test_slug_depth_requires_file_grouping(tmp_path, capsys):
    path = report(tmp_path, NESTED)
    assert (
        importer.main(
            ["--from-json", str(path), "--project", str(tmp_path), "--slug-depth", "2"]
        )
        == 2
    )
    assert "--group-by file" in capsys.readouterr().out


def test_json_only_flags_need_from_json(tmp_path, capsys):
    roadmap = tmp_path / "roadmap.md"
    roadmap.write_text("## Phase 1: Setup\n", encoding="utf-8")
    assert importer.main([str(roadmap), "--project", str(tmp_path), "--group-by", "file"]) == 2
    assert "--from-json" in capsys.readouterr().out


def test_negative_slug_depth_is_refused(tmp_path, capsys):
    path = report(tmp_path, NESTED)
    assert (
        importer.main(["--from-json", str(path), "--project", str(tmp_path), "--slug-depth", "-1"])
        == 2
    )
    assert "--slug-depth" in capsys.readouterr().out


def test_wrapper_object_sets_shard_and_labels(tmp_path):
    path = report(tmp_path, {"shard": "gate", "labels": ["audit"], "findings": FINDINGS[:1]})
    assert importer.main(["--from-json", str(path), "--project", str(tmp_path), "--apply"]) == 0
    task = tasks(tmp_path)[0]
    assert task.shard == "gate"
    assert "audit" in task.labels


def test_explicit_id_slug_and_title(tmp_path):
    payload = [
        {
            "title": "Убрать файловые исключения из гейта сложности",
            "id": "QUALITY-GATE",
            "slug": "quality-gate",
            "acceptance": ["исключений в xenon.ini нет"],
        }
    ]
    path = report(tmp_path, payload)
    assert importer.main(["--from-json", str(path), "--project", str(tmp_path), "--apply"]) == 0
    task = tasks(tmp_path)[0]
    assert (task.id, task.slug) == ("QUALITY-GATE", "quality-gate")
    assert (tmp_path / "backlog" / "tasks" / "quality-gate.md").is_file()


def test_invalid_json_is_exit_3(tmp_path, capsys):
    path = tmp_path / "broken.json"
    path.write_text("{nope", encoding="utf-8")
    assert importer.main(["--from-json", str(path), "--project", str(tmp_path)]) == 3
    assert "некорректный JSON" in capsys.readouterr().out


def test_both_sources_is_refused(tmp_path, capsys):
    path = report(tmp_path, FINDINGS)
    assert (
        importer.main(
            ["--from-json", str(path), str(tmp_path / "roadmap.md"), "--project", str(tmp_path)]
        )
        == 2
    )
    assert "ровно один источник" in capsys.readouterr().out


def test_no_source_is_refused(tmp_path, capsys):
    assert importer.main(["--project", str(tmp_path)]) == 2
    assert "ровно один источник" in capsys.readouterr().out
