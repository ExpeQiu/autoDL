from __future__ import annotations

import base64
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
    "t2v.flf2v": "minimax_h3_flf2vid.json",
    "minimax_h3_flf2vid": "minimax_h3_flf2vid.json",
    "t2v.r2v": "minimax_h3_ref2vid.json",
    "minimax_h3_ref2vid": "minimax_h3_ref2vid.json",
}
I2V_WORKFLOWS = {"t2v.i2v", "minimax_h3_img2vid"}
FLF_WORKFLOWS = {"t2v.flf2v", "minimax_h3_flf2vid"}
R2V_WORKFLOWS = {"t2v.r2v", "minimax_h3_ref2vid"}
MAX_IMAGE_BYTES = 20 * 1024 * 1024


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


def fit_h3_side(value: int | None, default: int) -> int:
    raw = default if value is None else int(value)
    snapped = max(256, min(1344, raw))
    snapped -= snapped % 16
    return snapped if snapped >= 256 else 256


def fit_h3_length(duration: float | None, fps: int | None, default: int) -> int:
    """H3 帧数须为 17k+5。本卡 Turbo 工作流上限 124 帧（约 5 秒 / 24fps）。"""
    if duration is not None and float(duration) > 0:
        rate = int(fps) if fps and int(fps) > 0 else 24
        raw = int(round(float(duration) * rate))
    else:
        raw = int(default)
    aligned = align_minimax_h3_frames(raw)
    return 124 if aligned > 124 else aligned


def plan_video_workflow(
    play_mode: str | None,
    workflow_id: str | None,
    *,
    has_image: bool,
    has_end_image: bool = False,
    image_count: int = 0,
) -> tuple[str, bool]:
    """把 cyberspace playMode 落到本卡实际工作流。返回 (workflow_id, 是否使用参考图)。"""
    mode = (play_mode or "").strip()
    if mode == "text":
        return "t2v.u03", False
    if mode == "first_frame":
        if not has_image:
            raise ComfyUIError("首帧图生视频需要参考图")
        return "t2v.i2v", True
    if mode == "first_last_frame":
        if not has_image or not has_end_image:
            raise ComfyUIError("首尾帧需要首帧和尾帧两张图")
        return "t2v.flf2v", True
    if mode == "multi":
        if image_count < 2 or image_count > 9:
            raise ComfyUIError("多图视频需要 2 到 9 张参考图")
        return "t2v.r2v", True
    if mode == "omni":
        raise ComfyUIError("全能参考含视频/音频，请改用 multi 只传参考图，或走云端")
    if mode:
        raise ComfyUIError(f"不支持的视频模式: {mode}")
    chosen = choose_video_workflow(
        workflow_id, has_image=has_image, has_end_image=has_end_image, ref_count=image_count
    )
    return chosen, bool(has_image and chosen in I2V_WORKFLOWS | FLF_WORKFLOWS | R2V_WORKFLOWS)


def choose_video_workflow(
    workflow_id: str | None,
    *,
    has_image: bool,
    has_end_image: bool = False,
    ref_count: int = 0,
) -> str:
    key = (workflow_id or "").strip()
    if key in R2V_WORKFLOWS:
        if ref_count < 2 or ref_count > 9:
            raise ComfyUIError("多图视频需要 2 到 9 张参考图")
        return key
    if key in FLF_WORKFLOWS:
        if not has_image or not has_end_image:
            raise ComfyUIError("首尾帧需要首帧和尾帧两张图")
        return key
    if has_image:
        if key in I2V_WORKFLOWS:
            return key
        return "t2v.i2v"
    if key in I2V_WORKFLOWS:
        raise ComfyUIError("图生视频需要参考图")
    return key or "t2v.u03"


def load_image_ref(raw: str, *, stem: str = "input") -> tuple[bytes, str]:
    text = (raw or "").strip()
    if not text:
        raise ComfyUIError("参考图为空")
    if text.startswith("data:"):
        header, _, payload = text.partition(",")
        if not payload:
            raise ComfyUIError("参考图 data URL 无效")
        mime = header.split(";")[0].removeprefix("data:").lower()
        ext = {"": ".png", "image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/webp": ".webp"}.get(mime)
        if ext is None:
            raise ComfyUIError(f"不支持的参考图类型: {mime or 'unknown'}")
        try:
            data = base64.b64decode(payload, validate=False)
        except Exception as exc:  # noqa: BLE001
            raise ComfyUIError("参考图 base64 无法解码") from exc
    elif text.startswith("http://") or text.startswith("https://"):
        try:
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                resp = client.get(text)
        except httpx.HTTPError as exc:
            raise ComfyUIError("无法下载参考图") from exc
        if resp.status_code >= 400:
            raise ComfyUIError(f"参考图下载失败 {resp.status_code}")
        data = resp.content
        ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
        ext = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/webp": ".webp", "image/png": ".png"}.get(ctype, ".png")
    else:
        try:
            data = base64.b64decode(text, validate=False)
        except Exception as exc:  # noqa: BLE001
            raise ComfyUIError("参考图不是 data URL、http(s) 或 base64") from exc
        ext = ".png"
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ComfyUIError("参考图为空或超过 20MB")
    safe_stem = "".join(ch for ch in stem if ch.isalnum() or ch in "-_") or "input"
    return data, f"{safe_stem}{ext}"


def upload_input_image(data: bytes, filename: str, *, endpoint: str | None = None) -> str:
    resp = _request(
        "POST",
        "/upload/image",
        timeout=60,
        endpoint=endpoint,
        files={"image": (filename, data, "application/octet-stream")},
        data={"type": "input", "overwrite": "true"},
    )
    body = resp.json()
    name = body.get("name") if isinstance(body, dict) else None
    if not name:
        raise ComfyUIError(f"上传参考图失败: {body}")
    subfolder = (body.get("subfolder") or "") if isinstance(body, dict) else ""
    return f"{subfolder}/{name}" if subfolder else str(name)


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


def attach_ref_images(prompt: dict[str, Any], names: list[str]) -> None:
    """把参考图接到 MiniMaxH3ReferenceToVideo 的 ref_images.ref_image_N。"""
    node = prompt["8"]["inputs"]
    for index, name in enumerate(names):
        node_id = str(30 + index)
        prompt[node_id] = {"class_type": "LoadImage", "inputs": {"image": name}}
        node[f"ref_images.ref_image_{index}"] = [node_id, 0]


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


def run_video_job(
    prompt_text: str,
    workflow_id: str | None,
    dest: Path,
    *,
    image: bytes | None = None,
    image_filename: str = "input.png",
    last_image: bytes | None = None,
    last_image_filename: str = "last.png",
    ref_images: list[tuple[bytes, str]] | None = None,
    width: int | None = None,
    height: int | None = None,
    length: int | None = None,
    steps: int | None = None,
    seed: int | None = None,
) -> Path:
    refs = list(ref_images or [])
    chosen = choose_video_workflow(
        workflow_id,
        has_image=image is not None,
        has_end_image=last_image is not None,
        ref_count=len(refs),
    )
    wf_path = resolve_workflow_path(chosen, "video")
    workflow = load_workflow(wf_path)
    length_n = fit_h3_length(None, None, length if length is not None else settings.comfyui_video_length)
    step_n = settings.comfyui_video_steps if steps is None else max(1, min(8, int(steps)))
    comfy = settings.comfyui_video_endpoint or settings.comfyui_endpoint
    params: dict[str, Any] = {
        "positive_prompt": prompt_text,
        "width": fit_h3_side(width, settings.comfyui_video_width),
        "height": fit_h3_side(height, settings.comfyui_video_height),
        "length": length_n,
        "steps": step_n,
        "seed": -1 if seed is None or int(seed) < 0 else int(seed),
    }
    if image is not None:
        params["image_name"] = upload_input_image(image, image_filename, endpoint=comfy)
    if last_image is not None:
        params["last_image_name"] = upload_input_image(last_image, last_image_filename, endpoint=comfy)
    uploaded_refs: list[str] = []
    for data, filename in refs:
        uploaded_refs.append(upload_input_image(data, filename, endpoint=comfy))
    graph = build_prompt(workflow, params)
    if uploaded_refs:
        attach_ref_images(graph, uploaded_refs)
    client_id = str(uuid.uuid4())
    prompt_id = submit_prompt(graph, client_id, endpoint=settings.comfyui_video_endpoint or settings.comfyui_endpoint)
    from ..config import setup_logging

    setup_logging().info(
        "comfyui_submitted prompt_id=%s workflow=%s length=%s steps=%s has_image=%s has_last=%s",
        prompt_id,
        chosen,
        length_n,
        params["steps"],
        image is not None,
        last_image is not None or bool(uploaded_refs),
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
