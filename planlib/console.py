"""Консольный вывод: UTF-8 независимо от локали Windows (cp1251/cp1252)."""

from __future__ import annotations

import sys


def enable_utf8() -> None:
    """Переключает stdout/stderr на UTF-8, чтобы кириллица не падала на cp1252."""
    for stream in (sys.stdout, sys.stderr):
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            continue
