"""Приёмка шардов: детерминированное состояние через doit (.doit.db)."""

import pathlib
import sys

ROOT = pathlib.Path(__file__).parent

SHARDS = {
    "s1": ["tools/emulator/generator.py", "tests/test_generator.py"],
    "s2": ["src/message_parser.py", "tests/test_parser.py"],
    "s3": ["src/transport.py", "tests/test_transport.py"],
}

TESTS = {
    "s1": "tests/test_generator.py",
    "s2": "tests/test_parser.py",
    "s3": "tests/test_transport.py",
}


def _accept(name: str) -> dict:
    return {
        "actions": [[sys.executable, "-m", "pytest", TESTS[name], "-q"]],
        "file_dep": [str(ROOT / path) for path in SHARDS[name]],
        "verbosity": 2,
    }


def task_s1():
    """приёмка s1: генератор"""
    return _accept("s1")


def task_s2():
    """приёмка s2: парсер"""
    return _accept("s2")


def task_s3():
    """приёмка s3: транспорт"""
    return _accept("s3")
