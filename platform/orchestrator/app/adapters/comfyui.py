from __future__ import annotations

import json
import random
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from ..config import ROOT, settings

WORKFLOW_DIR = ROOT / "workflows"
WORKFLOW_MAP = {
    "t2v.u03": "minimax_h3_txt2vid.json",
    "t2v.h3": "minimax_h3_txt2vid.json",
    "minimax_h3_txt2vid": "minimax_h3_txt2vid.json",
    "t2v.i2v": "minimax_h3_img2vid.json",
    "minimax_h3_img2vid": "minimax_h3_img2vid.json",
}


class ComfyUIError(Exception):
    """ComfyUI 调用失败。"""


def check_comfyui_health(timeout_s: float = 5.0) -> dict:
    if settings.ai_mock_mode and settings.ai_mock_image:
        return {
            "ok": True,
            "provider": "mock",
            "endpoint": settings.comfyui_endpoint,
            "reason": "AI_MOCK_MODE",
        }

    url = settings.comfyui_endpoint.rstrip("/") + "/system_stats"
    try:
        with httpx.Client(timeout=timeout_s) as client:
            resp = client.get(url)
        ok = resp.status_code == 200
        payload = resp.json() if ok else None
        return {
            "ok": ok,
            "provider": "comfyui",
            "endpoint": settings.comfyui_endpoint,
            "http_status": resp.status_code,
            "system": (payload or {}).get("system") if isinstance(payload, dict) else None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "provider": "comfyui",
            "endpoint": settings.comfyui_endpoint,
            "reason": str(exc),
        }


def align_minimax_h3_frames(length: int) -> int:
    n = max(5, int(length))
    while n % 17 != 5:
        n += 1
    return n


def resolve_workflow_path(workflow_id: str | None, modality: str) -> Path:
    key = (workflow_id or "").strip() or ("t2v.u03" if modality == "video" else "")
    name = WORKFLOW_MAP.get(key)
    if name is None and modality == "video":
        name = WORKFLOW_MAP["t2v.u03"]
    if not name:
        raise ComfyUIError(f"无工作流: modality={modality} workflow_id={workflow_id}")
    path = WORKFLOW_DIR / name
    if not path.is_file():
        raise ComfyUIError(f"工作流文件缺失: {path}")
    return path


def load_workflow(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_prompt(workflow_data: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    prompt = json.loads(json.dumps(workflow_data["prompt"]))
    inject_map: dict[str, list] = workflow_data.get("inject") or {}
    resolved = dict(params)
    if resolved.get("seed", -1) in (-1, None):
        resolved["seed"] = random.randint(0, 2**63 - 1)
    for key, node_path in inject_map.items():
        if key not in resolved:
            continue
        target: Any = prompt
        for part in node_path[:-1]:
            target = target[part]
        target[node_path[-1]] = resolved[key]
    return prompt


def _request(method: str, path: str, timeout: float, *, endpoint: str | None = None, **kwargs: Any) -> httpx.Response:
    base = (endpoint or settings.comfyui_endpoint).rstrip("/")
    url = base + "/" + path.lstrip("/")
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.request(method, url, **kwargs)
    except httpx.HTTPError as exc:
        raise ComfyUIError(f"无法连接 ComfyUI: {base}") from exc
    if resp.status_code >= 400:
        raise ComfyUIError(f"ComfyUI 返回错误 {resp.status_code}: {resp.text[:500]}")
    return resp


def submit_prompt(prompt: dict[str, Any], client_id: str, *, endpoint: str | None = None) -> str:
    data = _request(
        "POST",
        "/prompt",
        timeout=30,
        endpoint=endpoint,
        json={"prompt": prompt, "client_id": client_id},
    ).json()
    if data.get("error"):
        raise ComfyUIError(f"工作流提交失败: {data['error']}")
    if data.get("node_errors"):
        raise ComfyUIError(f"节点错误: {json.dumps(data['node_errors'], ensure_ascii=False)}")
    prompt_id = data.get("prompt_id")
    if not prompt_id:
        raise ComfyUIError(f"未返回 prompt_id: {data}")
    return str(prompt_id)


def wait_for_outputs(
    prompt_id: str, timeout_s: float, poll_s: float, *, endpoint: str | None = None
) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        history = _request("GET", f"/history/{prompt_id}", timeout=30, endpoint=endpoint).json()
        item = history.get(prompt_id)
        if item:
            status = item.get("status") or {}
            if status.get("status_str") == "error":
                raise ComfyUIError(f"生成失败: {status.get('messages')}")
            if item.get("outputs"):
                return item
        time.sleep(poll_s)
    raise ComfyUIError(f"任务超时 ({timeout_s:.0f}s): prompt_id={prompt_id}")


def _iter_output_files(history: dict[str, Any]) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for node_id, node_output in (history.get("outputs") or {}).items():
        if not isinstance(node_output, dict):
            continue
        for key, items in node_output.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict) and item.get("filename"):
                    files.append(
                        {
                            "node_id": node_id,
                            "bucket": key,
                            "filename": item["filename"],
                            "subfolder": item.get("subfolder") or "",
                            "type": item.get("type") or "output",
                        }
                    )
    return files


def download_file(file_info: dict[str, Any], dest: Path, *, endpoint: str | None = None) -> Path:
    resp = _request(
        "GET",
        "/view",
        timeout=120,
        endpoint=endpoint,
        params={
            "filename": file_info["filename"],
            "subfolder": file_info.get("subfolder") or "",
            "type": file_info.get("type") or "output",
        },
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    return dest


def run_video_job(prompt_text: str, workflow_id: str | None, dest: Path) -> Path:
    wf_path = resolve_workflow_path(workflow_id, "video")
    workflow = load_workflow(wf_path)
    length = align_minimax_h3_frames(settings.comfyui_video_length)
    params = {
        "positive_prompt": prompt_text,
        "width": settings.comfyui_video_width,
        "height": settings.comfyui_video_height,
        "length": length,
        "steps": settings.comfyui_video_steps,
        "seed": -1,
    }
    graph = build_prompt(workflow, params)
    client_id = str(uuid.uuid4())
    prompt_id = submit_prompt(graph, client_id, endpoint=settings.comfyui_video_endpoint or settings.comfyui_endpoint)
    from ..config import setup_logging

    setup_logging().info(
        "comfyui_submitted prompt_id=%s length=%s steps=%s",
        prompt_id,
        length,
        params["steps"],
    )
    timeout_s = settings.comfyui_timeout_ms / 1000.0
    poll_s = settings.comfyui_poll_interval_ms / 1000.0
    comfy = settings.comfyui_video_endpoint or settings.comfyui_endpoint
    history = wait_for_outputs(prompt_id, timeout_s, poll_s, endpoint=comfy)
    files = _iter_output_files(history)
    if not files:
        raise ComfyUIError(f"未找到输出文件 prompt_id={prompt_id}")
    preferred = next(
        (f for f in files if str(f.get("filename", "")).lower().endswith((".mp4", ".webm"))),
        files[0],
    )
    suffix = Path(preferred["filename"]).suffix or ".mp4"
    return download_file(preferred, dest.with_suffix(suffix), endpoint=comfy)
