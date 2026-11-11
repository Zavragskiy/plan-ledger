"""Совместимость: `python import_plan.py` → `plan-import`. Логика в planlib.cli.importer."""

from planlib.cli.importer import main, parse

__all__ = ["main", "parse"]

if __name__ == "__main__":
    raise SystemExit(main())
