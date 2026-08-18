from __future__ import annotations

import json
import sys
from typing import Any

from autodl_cli.mcp_adapter import McpAdapterError, call_tool, list_tools
from autodl_cli.utils.logger import setup_logger


def _text_result(payload: Any, is_error: bool = False) -> dict[str, Any]:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }


def handle_list_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": t["name"],
            "description": t["description"],
            "inputSchema": t["inputSchema"],
        }
        for t in list_tools()
    ]


def handle_call_tool(name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    try:
        result = call_tool(name, arguments or {})
    except McpAdapterError as exc:
        return _text_result({"ok": False, "error": str(exc)}, is_error=True)
    except Exception as exc:  # noqa: BLE001 — stdio 必须把异常收成 isError
        return _text_result({"ok": False, "error": str(exc)}, is_error=True)
    return _text_result(result, is_error=not result.get("ok"))


def _write(msg: dict[str, Any]) -> None:
    raw = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw)
    sys.stdout.buffer.flush()


def _read() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        key, _, value = line.decode("utf-8").partition(":")
        headers[key.strip().lower()] = value.strip()
    length = int(headers.get("content-length") or "0")
    body = sys.stdin.buffer.read(length) if length else b"{}"
    return json.loads(body.decode("utf-8"))


def _dispatch(req: dict[str, Any]) -> dict[str, Any] | None:
    method = req.get("method")
    req_id = req.get("id")
    params = req.get("params") or {}
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "autodl", "version": "0.1.0"},
            },
        }
    if method == "notifications/initialized" or method == "initialized":
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": handle_list_tools()}}
    if method == "tools/call":
        name = str(params.get("name") or "")
        args = params.get("arguments") or {}
        result = handle_call_tool(name, args if isinstance(args, dict) else {})
        return {"jsonrpc": "2.0", "id": req_id, "result": result}
    if req_id is None:
        return None
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def serve_stdio() -> None:
    """MCP stdio（Content-Length 帧）。仅 A 级工具。日志走 stderr。"""
    setup_logger()
    while True:
        req = _read()
        if req is None:
            return
        resp = _dispatch(req)
        if resp is not None:
            _write(resp)


def main() -> None:
    serve_stdio()


if __name__ == "__main__":
    main()
