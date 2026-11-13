"""Probe the backlog-py-mcp MCP server: which tools it exposes to an agent."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

BIN = pathlib.Path(r"C:\Tools\uv\bin\backlog-py-mcp.exe")


def send(process: subprocess.Popen, payload: dict) -> None:
    assert process.stdin is not None
    process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
    process.stdin.flush()


def read_until(process: subprocess.Popen, wanted_id: int, limit: int = 50) -> dict:
    assert process.stdout is not None
    for _ in range(limit):
        line = process.stdout.readline()
        if not line:
            raise SystemExit("the server closed stdout")
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if message.get("id") == wanted_id:
            return message
    raise SystemExit(f"no response for id={wanted_id}")


def main() -> int:
    from planlib.console import enable_utf8

    enable_utf8()
    if not BIN.exists():
        raise SystemExit(f"{BIN} not found; install it: uv tool install backlog-md-py==2.2.0")
    process = subprocess.Popen(
        [str(BIN)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )
    try:
        send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "plan-pilot-probe", "version": "0.1"},
                },
            },
        )
        print("initialize:", json.dumps(read_until(process, 1).get("result", {}), ensure_ascii=False)[:300])
        send(process, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        send(process, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tools = read_until(process, 2).get("result", {}).get("tools", [])
        print(f"\ntools: {len(tools)}")
        for tool in tools:
            description = (tool.get("description") or "").splitlines()[0][:90]
            print(f"  {tool['name']:24} {description}")
        schema_bytes = len(json.dumps(tools, ensure_ascii=False).encode("utf-8"))
        print(
            f"\nschemas take ~{schema_bytes / 1024:.1f} KB in every request (with MCP enabled)"
        )
    finally:
        process.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
