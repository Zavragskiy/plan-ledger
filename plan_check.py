"""Совместимость: `python plan_check.py` → `plan-check`. Логика в planlib.cli.gate."""

from planlib.cli.gate import main

if __name__ == "__main__":
    raise SystemExit(main())
