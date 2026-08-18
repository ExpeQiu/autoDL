from __future__ import annotations

import json
import logging
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from autodl_cli.config import CLI_ROOT
from autodl_cli.utils.errors import EXIT_ERROR

log = logging.getLogger("autodl")

MANIFEST_PATH = CLI_ROOT / "agent" / "manifest.json"
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


class McpAdapterError(Exception):
    def __init__(self, message: str, code: int = EXIT_ERROR) -> None:
        super().__init__(message)
        self.code = code


def load_manifest(path: Path | None = None) -> dict[str, Any]:
    target = path or MANIFEST_PATH
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise McpAdapterError("manifest 不是对象")
    return data


def is_agent_safe(cmd: dict[str, Any]) -> bool:
    return cmd.get("agent_safe") is True


def safe_commands(manifest: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    data = manifest or load_manifest()
    return [c for c in (data.get("commands") or []) if isinstance(c, dict) and is_agent_safe(c)]


def tool_name(cli_name: str, command_name: str) -> str:
    return f"{cli_name}_{command_name}".replace("-", "_")


def params_schema(cmd: dict[str, Any]) -> dict[str, Any]:
    params = cmd.get("params") or {}
    properties: dict[str, Any] = {}
    required: list[str] = []
    if isinstance(params, dict):
        for key, spec in params.items():
            if not isinstance(spec, dict):
                spec = {"type": "string", "description": str(spec)}
            prop = {k: v for k, v in spec.items() if k != "default"}
            prop.setdefault("type", "string")
            properties[key] = prop
            if "default" not in spec:
                required.append(key)
    schema: dict[str, Any] = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema


def list_tools(manifest: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    data = manifest or load_manifest()
    cli_name = str((data.get("cli") or {}).get("command") or data.get("name") or "autodl")
    tools = []
    for cmd in safe_commands(data):
        name = str(cmd.get("name") or "")
        tools.append(
            {
                "name": tool_name(cli_name, name),
                "command_name": name,
                "description": str(cmd.get("description") or name),
                "inputSchema": params_schema(cmd),
                "timeout_sec": int(cmd.get("timeout_sec") or 30),
                "cli_template": str(cmd.get("cli_template") or ""),
            }
        )
    return tools


def _fill_template(template: str, params: dict[str, Any], allowed: set[str]) -> str:
    extra = set(params) - allowed
    if extra:
        raise McpAdapterError(f"未知参数: {sorted(extra)}")

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in params:
            raise McpAdapterError(f"缺少参数 {key}")
        return shlex.quote(str(params[key]))

    filled = _PLACEHOLDER.sub(repl, template)
    if _PLACEHOLDER.search(filled):
        raise McpAdapterError("模板仍有未替换占位符")
    return filled


def _resolve_argv(argv: list[str]) -> list[str]:
    if not argv:
        raise McpAdapterError("空命令")
    resolved = shutil.which(argv[0])
    if resolved:
        argv[0] = resolved
        return argv
    if argv[0] in {"autodl", "autodl-mcp"}:
        return [sys.executable, "-m", "autodl_cli", *argv[1:]]
    return argv


def render_argv(cmd: dict[str, Any], params: dict[str, Any] | None = None) -> list[str]:
    template = str(cmd.get("cli_template") or "")
    spec = cmd.get("params") or {}
    allowed = set(spec) if isinstance(spec, dict) else set()
    values = dict(params or {})
    if isinstance(spec, dict):
        for key, item in spec.items():
            if key not in values and isinstance(item, dict) and "default" in item:
                values[key] = item["default"]
    filled = _fill_template(template, values, allowed)
    return _resolve_argv(shlex.split(filled))


def find_command(name: str, manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    data = manifest or load_manifest()
    cli_name = str((data.get("cli") or {}).get("command") or data.get("name") or "autodl")
    for cmd in data.get("commands") or []:
        if not isinstance(cmd, dict):
            continue
        raw = str(cmd.get("name") or "")
        if raw == name or tool_name(cli_name, raw) == name:
            return cmd
    raise McpAdapterError(f"未知命令 {name}")


def call_tool(name: str, params: dict[str, Any] | None = None, manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    cmd = find_command(name, manifest)
    if not is_agent_safe(cmd):
        raise McpAdapterError(f"拒绝非 A 级命令: {cmd.get('name')}")
    argv = render_argv(cmd, params)
    timeout = int(cmd.get("timeout_sec") or 30) or 30
    tool = tool_name("autodl", str(cmd.get("name")))
    log.info("mcp call %s", tool, extra={"cmd": "mcp.call"})
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        log.error("mcp timeout %s", tool, extra={"cmd": "mcp.call"})
        raise McpAdapterError(f"超时 {timeout}s: {tool}") from exc
    stdout = completed.stdout.strip()
    envelope: Any = stdout
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                envelope = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    return {
        "ok": completed.returncode == 0,
        "exit_code": completed.returncode,
        "tool": tool,
        "result": envelope,
        "stderr": completed.stderr.strip()[-2000:] if completed.stderr else "",
    }
