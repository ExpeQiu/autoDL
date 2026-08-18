from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from .adapters.comfyui import ComfyUIError, check_comfyui_health, run_video_job
from .adapters.llm import check_llm_health, run_llm_job
from .adapters.mock import run_mock_job
from .config import settings, setup_logging
from .models import Job, JobCreate, ScoreUpdate, utcnow

log = setup_logging()
JOBS: dict[str, Job] = {}
STORE = settings.sqlite_path.parent / "jobs.json"
MEDIA = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".txt": "text/plain; charset=utf-8",
}


def _public_url(job_id: str) -> str:
    return f"/v1/jobs/{job_id}/file"


def _save_jobs() -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    payload = [j.model_dump(mode="json") for j in JOBS.values()]
    STORE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _load_jobs() -> None:
    if not STORE.is_file():
        return
    try:
        raw = json.loads(STORE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    for item in raw:
        try:
            job = Job.model_validate(item)
        except Exception:  # noqa: BLE001
            continue
        if job.output_url is None:
            job.output_url = _public_url(job.id)
        JOBS[job.id] = job


_load_jobs()

app = FastAPI(title="gen-test-platform", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _new_ids(req: JobCreate) -> tuple[str, str]:
    run_id = req.run_id or f"run_{uuid.uuid4().hex[:12]}"
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    return run_id, job_id


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    mock = "Mock 开" if settings.ai_mock_mode else "真算力"
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>生成测试平台 API</title>
<meta http-equiv="refresh" content="0;url=http://127.0.0.1:3190/">
<style>
body{{font-family:ui-sans-serif,system-ui;margin:48px;color:#0f172a}}
a{{color:#2563eb}}
</style></head><body>
<p>编排已启动 · {mock}。交互页：<a href="http://127.0.0.1:3190/">http://127.0.0.1:3190/</a></p>
<p><a href="/docs">API 文档</a></p>
</body></html>
"""


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "service": "orchestrator",
        "mock": settings.ai_mock_mode,
        "mock_text": settings.ai_mock_text,
        "mock_image": settings.ai_mock_image,
        "port": settings.orch_port,
    }


@app.get("/v1/compute/health")
async def compute_health() -> dict:
    comfy = check_comfyui_health()
    llm = await check_llm_health()
    extra = {
        "run_id": "health",
        "provider": "mixed",
        "status": "ok" if (comfy.get("ok") or llm.get("ok")) else "down",
    }
    log.info("compute_health", extra=extra)
    return {
        "ok": bool(comfy.get("ok") or llm.get("ok")),
        "comfyui": comfy,
        "llm": llm,
        "provider": "mixed",
        "endpoint": settings.comfyui_endpoint,
    }


@app.get("/v1/llm/health")
async def llm_health() -> dict:
    return await check_llm_health()


def _pick_provider(req: JobCreate) -> Literal["mock", "comfyui", "llm"]:
    if req.modality == "text":
        return "mock" if settings.ai_mock_text else "llm"
    if req.modality == "image":
        return "mock" if (settings.ai_mock_mode or settings.ai_mock_image) else "comfyui"
    return "mock" if settings.ai_mock_mode else "comfyui"


def _finish_job(job: Job, *, ok: bool, error: str | None = None) -> None:
    stored = JOBS.get(job.id) or job
    stored.status = "succeeded" if ok else "failed"
    stored.error = error
    stored.output_uri = job.output_uri
    stored.output_url = _public_url(stored.id)
    stored.updated_at = utcnow()
    JOBS[stored.id] = stored
    _save_jobs()
    log.info(
        "job_succeeded" if ok else "job_failed",
        extra={
            "run_id": stored.run_id,
            "job_id": stored.id,
            "modality": stored.modality,
            "provider": stored.provider,
            "status": stored.status,
        },
    )


def _run_comfyui_background(job_id: str, prompt: str, workflow_id: str | None, modality: str) -> None:
    job = JOBS.get(job_id)
    if job is None:
        return
    job.status = "running"
    job.updated_at = utcnow()
    JOBS[job_id] = job
    _save_jobs()
    log.info(
        "job_running",
        extra={
            "run_id": job.run_id,
            "job_id": job.id,
            "modality": job.modality,
            "provider": job.provider,
            "status": "running",
        },
    )
    try:
        if modality != "video":
            raise ComfyUIError("本实例无文生图权重，图片请保持 AI_MOCK_IMAGE=true")
        settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
        dest = settings.artifacts_dir / job.id
        out = run_video_job(prompt, workflow_id, dest)
        job.output_uri = str(out)
        _finish_job(job, ok=True)
    except Exception as exc:  # noqa: BLE001
        job.error = str(exc)
        _finish_job(job, ok=False, error=str(exc))
        log.warning(
            "job_comfyui_failed",
            extra={
                "run_id": job.run_id,
                "job_id": job.id,
                "modality": job.modality,
                "provider": job.provider,
                "status": "failed",
            },
        )


@app.post("/v1/jobs", status_code=201)
def create_job(req: JobCreate, background_tasks: BackgroundTasks) -> Job:
    run_id, job_id = _new_ids(req)
    now = utcnow()
    provider = _pick_provider(req)

    job = Job(
        id=job_id,
        run_id=run_id,
        modality=req.modality,
        prompt=req.prompt,
        suite_id=req.suite_id,
        case_id=req.case_id,
        workflow_id=req.workflow_id,
        status="queued",
        provider=provider,
        created_at=now,
        updated_at=now,
    )
    log.info(
        "job_queued",
        extra={
            "run_id": run_id,
            "job_id": job_id,
            "modality": req.modality,
            "provider": provider,
            "status": "queued",
        },
    )

    if provider == "mock":
        job = run_mock_job(job, req)
    elif provider == "llm":
        try:
            job = run_llm_job(job, req)
        except Exception as exc:  # noqa: BLE001
            job.status = "failed"
            job.error = str(exc)
            JOBS[job.id] = job
            _save_jobs()
            log.warning(
                "job_llm_failed",
                extra={"run_id": run_id, "job_id": job_id, "provider": provider, "status": "failed"},
            )
            raise HTTPException(status_code=502, detail=job.error) from exc
    else:
        if req.modality == "image":
            raise HTTPException(status_code=501, detail="本实例无文生图权重，请设 AI_MOCK_IMAGE=true")
        health = check_comfyui_health()
        if not health.get("ok"):
            raise HTTPException(
                status_code=503,
                detail=f"ComfyUI 不可达: {health.get('reason') or health.get('endpoint')}",
            )
        JOBS[job.id] = job
        _save_jobs()
        background_tasks.add_task(
            _run_comfyui_background,
            job.id,
            req.prompt,
            req.workflow_id,
            req.modality,
        )
        job.output_url = _public_url(job.id)
        return job

    job.output_url = _public_url(job.id)
    JOBS[job.id] = job
    _save_jobs()
    log.info(
        "job_succeeded",
        extra={
            "run_id": job.run_id,
            "job_id": job.id,
            "modality": job.modality,
            "provider": job.provider,
            "status": job.status,
        },
    )
    return job


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str) -> Job:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.get("/v1/jobs/{job_id}/file")
def job_file(job_id: str) -> FileResponse:
    job = JOBS.get(job_id)
    if job is None or not job.output_uri:
        raise HTTPException(status_code=404, detail="artifact not found")
    path = Path(job.output_uri)
    if not path.is_file():
        path = settings.artifacts_dir / path.name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="artifact missing")
    media = MEDIA.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media, filename=path.name)


@app.patch("/v1/jobs/{job_id}/score")
def set_score(job_id: str, body: ScoreUpdate) -> Job:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    job.score = body.score
    job.updated_at = utcnow()
    JOBS[job.id] = job
    _save_jobs()
    log.info(
        "job_scored",
        extra={"run_id": job.run_id, "job_id": job.id, "status": job.status, "provider": job.provider},
    )
    return job


@app.get("/v1/jobs")
def list_jobs(
    modality: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    items = list(JOBS.values())
    if modality:
        items = [j for j in items if j.modality == modality]
    items.sort(key=lambda j: j.created_at, reverse=True)
    return {"items": items[:limit], "total": len(items)}
