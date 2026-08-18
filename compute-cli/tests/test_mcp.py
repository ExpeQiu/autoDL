from __future__ import annotations

import json
import subprocess
import sys

import pytest

from autodl_cli.mcp_adapter import McpAdapterError, call_tool, list_tools, render_argv, find_command
from autodl_cli.mcp_server import _dispatch, handle_call_tool, handle_list_tools


BLOCKED = ("instance-power-on", "instance-power-off", "job-submit-live", "tunnel-start")


def test_list_tools_only_agent_safe() -> None:
    tools = list_tools()
    names = {t["name"] for t in tools}
    assert "autodl_job_submit_demo" in names
    assert "autodl_config_check" in names
    assert "autodl_tunnel_status" in names
    for blocked in BLOCKED:
        assert f"autodl_{blocked.replace('-', '_')}" not in names
    mcp_names = {t["name"] for t in handle_list_tools()}
    assert mcp_names == names


def test_reject_power_on() -> None:
    with pytest.raises(McpAdapterError, match="非 A 级"):
        call_tool("instance-power-on")
    with pytest.raises(McpAdapterError, match="非 A 级"):
        call_tool("autodl_instance_power_on")


def test_reject_unknown_param() -> None:
    with pytest.raises(McpAdapterError, match="未知参数"):
        render_argv(find_command("job-submit-demo"), {"prompt": "x", "rm": "-rf"})


def test_job_submit_demo_via_adapter() -> None:
    result = call_tool("autodl_job_submit_demo", {"prompt": "mcp 一只猫"})
    assert result["ok"] is True
    assert result["exit_code"] == 0
    envelope = result["result"]
    assert isinstance(envelope, dict)
    assert envelope.get("module") == "job.submit"
    assert envelope.get("data_source") == "demo"
    assert envelope.get("ok") is True
    assert str(envelope.get("job_id", "")).startswith("job_")
    assert envelope["items"][0]["status"] == "succeeded"


def test_handle_call_tool_error_flag() -> None:
    payload = handle_call_tool("autodl_instance_power_on", {})
    assert payload["isError"] is True
    body = json.loads(payload["content"][0]["text"])
    assert body["ok"] is False


def test_stdio_tools_list() -> None:
    resp = _dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    assert resp is not None
    names = {t["name"] for t in resp["result"]["tools"]}
    assert "autodl_job_submit_demo" in names
    assert "autodl_instance_power_on" not in names


def _frame(msg: dict) -> bytes:
    raw = json.dumps(msg).encode("utf-8")
    return f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw


def _read_framed(buf: bytes) -> dict:
    header, _, rest = buf.partition(b"\r\n\r\n")
    length = int(header.decode("ascii").split(":")[1].strip())
    return json.loads(rest[:length].decode("utf-8"))


def test_stdio_subprocess_list() -> None:
    proc = subprocess.Popen(
        [sys.executable, "-m", "autodl_cli.mcp_server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdin and proc.stdout
    try:
        proc.stdin.write(_frame({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}))
        proc.stdin.write(_frame({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        proc.stdin.write(_frame({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}))
        proc.stdin.close()
        out = proc.stdout.read()
        assert proc.wait(timeout=10) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
    assert b"autodl_job_submit_demo" in out
    assert b"instance_power_on" not in out
    first = _read_framed(out)
    assert first["result"]["serverInfo"]["name"] == "autodl"
