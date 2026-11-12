"""Совместимость: `python plan_shard.py` → `plan-shard`. Логика в planlib.cli.shard."""

from planlib.cli.shard import main

if __name__ == "__main__":
    raise SystemExit(main())
