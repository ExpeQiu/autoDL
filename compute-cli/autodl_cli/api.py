from __future__ import annotations

import os
import time
from typing import Any

import httpx

from autodl_cli.config import instance_uuid, token_set
from autodl_cli.utils.errors import EXIT_AUTH, EXIT_ERROR, EXIT_NOT_READY

_SECRET_KEYS = ("root_password", "jupyter_token", "password", "token")


class ApiError(Exception):
    def __init__(self, message: str, code: int = EXIT_ERROR) -> None:
        super().__init__(message)
        self.code = code


def api_base() -> str:
    return os.getenv("AUTODL_API_BASE", "https://api.autodl.com").rstrip("/")


def _token() -> str:
    token = os.getenv("AUTODL_TOKEN", "").strip()
    if not token:
        raise ApiError("未设置 AUTODL_TOKEN", EXIT_AUTH)
    return token


def _headers() -> dict[str, str]:
    return {"Authorization": _token(), "Content-Type": "application/json"}


def call(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    url = api_base() + path
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.request(method, url, headers=_headers(), json=body)
    except httpx.ConnectError as exc:
        raise ApiError(f"AutoDL API 不可达 {url}", EXIT_NOT_READY) from exc
    except httpx.TimeoutException as exc:
        raise ApiError(f"AutoDL API 超时 {url}", EXIT_NOT_READY) from exc

    if resp.status_code in (401, 403):
        raise ApiError("Token 无效或无权限", EXIT_AUTH)
    try:
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise ApiError(f"非 JSON 响应 HTTP {resp.status_code}", EXIT_ERROR) from exc
    if not isinstance(payload, dict):
        raise ApiError("响应格式错误", EXIT_ERROR)
    code = str(payload.get("code") or "")
    if code != "Success":
        msg = str(payload.get("msg") or code or f"HTTP {resp.status_code}")
        lowered = msg.lower()
        if "token" in lowered or "auth" in lowered or "登录" in msg:
            raise ApiError(msg, EXIT_AUTH)
        raise ApiError(msg, EXIT_ERROR)
    return payload.get("data")


def _scrub(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _scrub(v) for k, v in obj.items() if k not in _SECRET_KEYS}
    if isinstance(obj, list):
        return [_scrub(i) for i in obj]
    return obj


def _require_uuid(uuid: str | None) -> str:
    value = (uuid or instance_uuid()).strip()
    if not value:
        raise ApiError("未指定实例，设 AUTODL_INSTANCE_UUID 或 --uuid", EXIT_ERROR)
    return value


def list_instances(page_size: int = 50) -> list[dict[str, Any]]:
    data = call("POST", "/api/v1/dev/instance/pro/list", {"page_index": 1, "page_size": page_size}) or {}
    rows = data.get("list") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return []
    return [_normalize(row) for row in rows if isinstance(row, dict)]


def get_status(uuid: str | None = None) -> str:
    uid = _require_uuid(uuid)
    data = call("GET", "/api/v1/dev/instance/pro/status", {"instance_uuid": uid})
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        return str(data.get("status") or "")
    return str(data or "")


def get_snapshot(uuid: str | None = None) -> dict[str, Any]:
    uid = _require_uuid(uuid)
    data = call("GET", "/api/v1/dev/instance/pro/snapshot", {"instance_uuid": uid}) or {}
    if not isinstance(data, dict):
        return {}
    return _scrub(data)


def describe(uuid: str | None = None) -> dict[str, Any]:
    uid = _require_uuid(uuid)
    status = get_status(uid)
    item: dict[str, Any] = {
        "uuid": uid,
        "name": None,
        "status": status,
        "ssh_host": None,
        "ssh_port": None,
        "gpu": None,
    }
    if status == "running":
        snap = get_snapshot(uid)
        item["ssh_host"] = snap.get("proxy_host")
        item["ssh_port"] = snap.get("ssh_port")
        item["gpu"] = snap.get("snapshot_gpu_alias_name")
        item["region"] = snap.get("region_sign")
    try:
        for row in list_instances():
            if row.get("uuid") == uid:
                item["name"] = row.get("name") or item["name"]
                item["gpu"] = item["gpu"] or row.get("gpu")
                break
    except ApiError:
        pass
    return item


def power_on(uuid: str | None = None, *, wait: bool = False, timeout_s: float = 180.0) -> dict[str, Any]:
    uid = _require_uuid(uuid)
    call("POST", "/api/v1/dev/instance/pro/power_on", {"instance_uuid": uid, "payload": "gpu"})
    if wait:
        deadline = time.time() + timeout_s
        last = ""
        while time.time() < deadline:
            last = get_status(uid)
            if last == "running":
                break
            time.sleep(2)
        else:
            raise ApiError(f"开机等待超时 status={last}", EXIT_NOT_READY)
    return describe(uid)


def power_off(uuid: str | None = None) -> dict[str, Any]:
    uid = _require_uuid(uuid)
    call("POST", "/api/v1/dev/instance/pro/power_off", {"instance_uuid": uid})
    return {
        "uuid": uid,
        "status": "shutdown",
        "ssh_host": None,
        "ssh_port": None,
    }


def wallet_balance() -> dict[str, Any]:
    data = call("POST", "/api/v1/dev/wallet/balance") or {}
    if not isinstance(data, dict):
        data = {}
    assets = int(data.get("assets") or 0)
    return {
        "assets": assets,
        "accumulate": int(data.get("accumulate") or 0),
        "voucher_balance": int(data.get("voucher_balance") or 0),
        "yuan": assets / 1000.0,
    }


def _normalize(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "uuid": row.get("uuid"),
        "name": row.get("name"),
        "status": row.get("status"),
        "ssh_host": None,
        "ssh_port": None,
        "gpu": row.get("gpu_spec_uuid"),
        "region": row.get("region_name"),
        "start_mode": row.get("start_mode"),
    }


def token_ready() -> bool:
    return token_set()
