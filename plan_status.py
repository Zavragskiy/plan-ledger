"""Совместимость: `python plan_status.py` → `plan-status`. Логика в planlib.cli.status."""

from planlib.cli.status import main

if __name__ == "__main__":
    raise SystemExit(main())
