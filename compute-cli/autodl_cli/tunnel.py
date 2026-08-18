from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from autodl_cli.config import (
    CLI_ROOT,
    comfyui_endpoint,
    llm_base_url,
    ssh_host,
    ssh_password,
    ssh_port,
    ssh_user,
)
from autodl_cli.utils.errors import EXIT_ERROR, EXIT_NOT_READY

PID_FILE = CLI_ROOT / "logs" / "tunnel.pid"
LOG_FILE = CLI_ROOT / "logs" / "tunnel.log"


class TunnelError(Exception):
    def __init__(self, message: str, code: int = EXIT_ERROR) -> None:
        super().__init__(message)
        self.code = code


def _local_bind(url: str, fallback_port: int) -> tuple[str, int]:
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or fallback_port
    return host, port


def comfy_bind() -> tuple[str, int]:
    raw = os.getenv("COMFYUI_LOCAL_PORT", "").strip()
    host, port = _local_bind(comfyui_endpoint(), 8188)
    if raw:
        port = int(raw)
    return host, port


def llm_bind() -> tuple[str, int]:
    raw = os.getenv("LLM_LOCAL_PORT", "").strip()
    host, port = _local_bind(llm_base_url(), 8088)
    if raw:
        port = int(raw)
    return host, port


def remote_comfy_port() -> int:
    return int(os.getenv("COMFYUI_REMOTE_PORT", "8188"))


def remote_llm_port() -> int:
    return int(os.getenv("LLM_REMOTE_PORT", "8088"))


def port_listening(host: str, port: int, timeout_s: float = 0.3) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def _pid() -> int | None:
    if not PID_FILE.is_file():
        return None
    raw = PID_FILE.read_text(encoding="utf-8").strip()
    if not raw.isdigit():
        return None
    pid = int(raw)
    try:
        os.kill(pid, 0)
    except OSError:
        PID_FILE.unlink(missing_ok=True)
        return None
    return pid


def _write_pid(pid: int) -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(pid), encoding="utf-8")


def snapshot() -> dict[str, Any]:
    ch, cp = comfy_bind()
    lh, lp = llm_bind()
    pid = _pid()
    comfy_ok = port_listening(ch, cp)
    llm_ok = port_listening(lh, lp)
    return {
        "pid": pid,
        "ssh_host": ssh_host(),
        "ssh_port": ssh_port() or None,
        "comfyui": {
            "endpoint": comfyui_endpoint(),
            "host": ch,
            "port": cp,
            "listening": comfy_ok,
        },
        "llm": {
            "endpoint": llm_base_url(),
            "host": lh,
            "port": lp,
            "listening": llm_ok,
        },
        "listening": comfy_ok or llm_ok,
    }


def status() -> dict[str, Any]:
    return snapshot()


def _ssh_cmd() -> tuple[list[str], dict[str, str]]:
    port = ssh_port()
    if not port:
        raise TunnelError("未设置 COMFYUI_SSH_PORT（开机后看 AutoDL 控制台）", EXIT_ERROR)
    ch, cp = comfy_bind()
    lh, lp = llm_bind()
    ssh_args = [
        "ssh",
        "-N",
        "-o",
        "ServerAliveInterval=30",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "StrictHostKeyChecking=no",
        "-L",
        f"{cp}:127.0.0.1:{remote_comfy_port()}",
        "-L",
        f"{lp}:127.0.0.1:{remote_llm_port()}",
        "-p",
        port,
        f"{ssh_user()}@{ssh_host()}",
    ]
    env = os.environ.copy()
    password = ssh_password()
    if password:
        if not shutil.which("sshpass"):
            raise TunnelError("已配置 SSH 密码但未安装 sshpass", EXIT_ERROR)
        env["SSHPASS"] = password
        return ["sshpass", "-e", *ssh_args], env
    ssh_args[2:2] = ["-o", "BatchMode=yes"]
    return ssh_args, env


def start(*, wait_s: float = 3.0) -> dict[str, Any]:
    current = snapshot()
    if current.get("pid"):
        current["already"] = True
        return current

    cmd, env = _ssh_cmd()
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log_fh = LOG_FILE.open("a", encoding="utf-8")
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=log_fh,
            stderr=log_fh,
            env=env,
            start_new_session=True,
        )
    finally:
        log_fh.close()
    _write_pid(proc.pid)

    deadline = time.time() + wait_s
    while time.time() < deadline:
        if proc.poll() is not None:
            PID_FILE.unlink(missing_ok=True)
            raise TunnelError(f"ssh 退出 code={proc.returncode}，见 {LOG_FILE}", EXIT_NOT_READY)
        snap = snapshot()
        if snap.get("listening"):
            snap["started"] = True
            return snap
        time.sleep(0.3)

    snap = snapshot()
    snap["started"] = True
    snap["hint"] = "进程已拉起，端口尚未就绪；稍后再 tunnel status"
    return snap


def stop() -> dict[str, Any]:
    pid = _pid()
    if pid is None:
        return {"stopped": True, "pid": None, "already": True, **snapshot()}
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        PID_FILE.unlink(missing_ok=True)
        return {"stopped": True, "pid": pid, **snapshot()}
    deadline = time.time() + 3
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            break
        time.sleep(0.1)
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    PID_FILE.unlink(missing_ok=True)
    return {"stopped": True, "pid": pid, **snapshot()}
