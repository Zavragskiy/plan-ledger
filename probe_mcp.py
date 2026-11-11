"""Совместимость: `python probe_mcp.py` → `plan-mcp-probe`. Логика в planlib.cli.mcp_probe."""

from planlib.cli.mcp_probe import main

if __name__ == "__main__":
    raise SystemExit(main())
