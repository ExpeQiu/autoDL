from __future__ import annotations

import logging
import re
import time

import httpx

from ..config import settings
from ..models import Job, JobCreate, utcnow

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
log = logging.getLogger("genlab")


def _base() -> str:
    return settings.llm_base_url.rstrip("/")


async def check_llm_health(timeout_s: float = 5.0) -> dict:
    if settings.ai_mock_text:
        return {
            "ok": True,
            "provider": "mock",
            "endpoint": _base(),
            "reason": "AI_MOCK_TEXT",
        }
    url = _base() + "/v1/models"
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.get(url)
        ok = resp.status_code == 200
        payload = resp.json() if ok else None
        ids = [m.get("id") for m in (payload or {}).get("data") or []] if isinstance(payload, dict) else []
        return {
            "ok": ok,
            "provider": "llamacpp",
            "endpoint": _base(),
            "http_status": resp.status_code,
            "models": ids,
            "model": settings.llm_model,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "provider": "llamacpp",
            "endpoint": _base(),
            "reason": str(exc),
        }


def generate_text(prompt: str) -> str:
    headers = {"Content-Type": "application/json"}
    if settings.llm_api_key:
        headers["Authorization"] = f"Bearer {settings.llm_api_key}"
    body = {
        "model": settings.llm_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 1024,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    started = time.monotonic()
    with httpx.Client(timeout=settings.llm_timeout_s) as client:
        resp = client.post(_base() + "/v1/chat/completions", headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
    log.info(
        "llm_chat_done",
        extra={
            "run_id": "llm",
            "provider": "llamacpp",
            "status": "ok",
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        },
    )
    msg = ((data.get("choices") or [{}])[0].get("message") or {})
    text = msg.get("content") or ""
    if not text.strip():
        text = msg.get("reasoning_content") or ""
    text = _THINK.sub("", text).strip()
    if not text:
        raise RuntimeError(f"empty llm reply: {data}")
    return text


def run_llm_job(job: Job, req: JobCreate) -> Job:
    job.status = "running"
    job.updated_at = utcnow()
    text = generate_text(req.prompt)
    settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
    path = settings.artifacts_dir / f"{job.id}.txt"
    path.write_text(text, encoding="utf-8")
    job.output_uri = str(path)
    job.status = "succeeded"
    job.updated_at = utcnow()
    return job
