from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import httpx

from autodl_cli.config import CLI_ROOT, orch_base
from autodl_cli.utils.errors import EXIT_COMPUTE_FAIL, EXIT_ERROR, EXIT_NOT_READY

ARTIFACTS = CLI_ROOT / "artifacts"


class OrchError(Exception):
    def __init__(self, message: str, code: int = EXIT_NOT_READY, payload: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.payload = payload


def _timeout(seconds: float) -> httpx.Timeout:
    return httpx.Timeout(seconds)


def request(
    method: str,
    path: str,
    *,
    timeout_s: float = 15.0,
    json: Any = None,
    params: dict[str, Any] | None = None,
) -> httpx.Response:
    url = orch_base() + path
    try:
        with httpx.Client(timeout=_timeout(timeout_s)) as client:
            resp = client.request(method, url, json=json, params=params)
    except httpx.ConnectError as exc:
        raise OrchError(f"编排不可达 {url}", EXIT_NOT_READY) from exc
    except httpx.TimeoutException as exc:
        raise OrchError(f"编排超时 {url}", EXIT_NOT_READY) from exc

    if resp.status_code == 404:
        raise OrchError("not found", EXIT_NOT_READY)
    if resp.status_code in (501, 502):
        detail = _detail(resp) or resp.text[:300]
        raise OrchError(detail, EXIT_COMPUTE_FAIL)
    if resp.status_code >= 400:
        detail = _detail(resp) or resp.text[:300]
        raise OrchError(detail, EXIT_ERROR)
    return resp


def _detail(resp: httpx.Response) -> str:
    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        return ""
    if isinstance(data, dict):
        err = data.get("detail") or data.get("error")
        if isinstance(err, str):
            return err
    return ""


def ping() -> dict[str, Any]:
    return request("GET", "/health", timeout_s=5.0).json()


def compute_health() -> dict[str, Any]:
    return request("GET", "/v1/compute/health", timeout_s=8.0).json()


def create_job(
    *,
    modality: str,
    prompt: str,
    workflow_id: str | None = None,
    run_id: str | None = None,
    timeout_s: float = 180.0,
) -> dict[str, Any]:
    body: dict[str, Any] = {"modality": modality, "prompt": prompt}
    if workflow_id:
        body["workflow_id"] = workflow_id
    if run_id:
        body["run_id"] = run_id
    return request("POST", "/v1/jobs", json=body, timeout_s=timeout_s).json()


def get_job(job_id: str) -> dict[str, Any]:
    return request("GET", f"/v1/jobs/{job_id}", timeout_s=10.0).json()


def list_jobs(modality: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"limit": limit}
    if modality:
        params["modality"] = modality
    data = request("GET", "/v1/jobs", params=params, timeout_s=10.0).json()
    if isinstance(data, dict):
        items = data.get("items") or []
        return list(items)
    return []


def wait_job(job_id: str, *, timeout_s: float = 180.0, interval_s: float = 1.0) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    last: dict[str, Any] | None = None
    while time.time() < deadline:
        last = get_job(job_id)
        if last.get("status") in ("succeeded", "failed"):
            return last
        time.sleep(interval_s)
    raise OrchError("wait timeout", EXIT_NOT_READY, last)


def download_file(job_id: str, dest: Path | None = None) -> Path:
    resp = request("GET", f"/v1/jobs/{job_id}/file", timeout_s=60.0)
    name = job_id
    cd = resp.headers.get("content-disposition") or ""
    if "filename=" in cd:
        name = cd.split("filename=")[-1].strip().strip('"')
    elif resp.headers.get("content-type", "").startswith("image/svg"):
        name = f"{job_id}.svg"
    elif "text/plain" in (resp.headers.get("content-type") or ""):
        name = f"{job_id}.txt"
    path = dest or (ARTIFACTS / name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(resp.content)
    return path
