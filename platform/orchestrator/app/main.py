from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from .adapters.comfyui import ComfyUIError, check_comfyui_health, run_video_job
from .adapters.llm import check_llm_health, generate_text
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
        if job.elapsed_ms is None and job.status in ("succeeded", "failed"):
            start = job.started_at or job.created_at
            end = job.finished_at or job.updated_at
            job.elapsed_ms = max(0, int((end - start).total_seconds() * 1000))
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


def _fill_output_metrics(job: Job) -> None:
    if not job.output_uri:
        return
    path = Path(job.output_uri)
    if not path.is_file():
        path = settings.artifacts_dir / path.name
    if not path.is_file():
        return
    job.output_bytes = path.stat().st_size
    if path.suffix.lower() in {".txt", ".md"}:
        try:
            job.output_chars = len(path.read_text(encoding="utf-8"))
        except OSError:
            pass


def _mark_running(job: Job) -> None:
    now = utcnow()
    job.status = "running"
    job.started_at = job.started_at or now
    job.updated_at = now
    JOBS[job.id] = job
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


def _finish_job(job: Job, *, ok: bool, error: str | None = None) -> None:
    if job.id not in JOBS:
        return
    stored = JOBS[job.id]
    now = utcnow()
    stored.status = "succeeded" if ok else "failed"
    stored.error = error
    stored.output_uri = job.output_uri
    stored.output_url = _public_url(stored.id)
    stored.model = job.model or stored.model
    stored.prompt_tokens = job.prompt_tokens if job.prompt_tokens is not None else stored.prompt_tokens
    stored.completion_tokens = job.completion_tokens if job.completion_tokens is not None else stored.completion_tokens
    stored.total_tokens = job.total_tokens if job.total_tokens is not None else stored.total_tokens
    stored.started_at = stored.started_at or job.started_at
    stored.finished_at = now
    stored.updated_at = now
    if job.elapsed_ms is not None:
        stored.elapsed_ms = job.elapsed_ms
    else:
        start = stored.started_at or stored.created_at
        stored.elapsed_ms = max(0, int((now - start).total_seconds() * 1000))
    _fill_output_metrics(stored)
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
            "elapsed_ms": stored.elapsed_ms,
        },
    )


def _run_llm_background(job_id: str, prompt: str) -> None:
    job = JOBS.get(job_id)
    if job is None:
        return
    _mark_running(job)
    try:
        settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
        result = generate_text(prompt)
        if job_id not in JOBS:
            return
        path = settings.artifacts_dir / f"{job.id}.txt"
        path.write_text(result["text"], encoding="utf-8")
        job.output_uri = str(path)
        job.model = result.get("model")
        job.prompt_tokens = result.get("prompt_tokens")
        job.completion_tokens = result.get("completion_tokens")
        job.total_tokens = result.get("total_tokens")
        job.elapsed_ms = result.get("elapsed_ms")
        _finish_job(job, ok=True)
    except Exception as exc:  # noqa: BLE001
        _finish_job(job, ok=False, error=str(exc))
        log.warning(
            "job_llm_failed",
            extra={
                "run_id": job.run_id,
                "job_id": job.id,
                "modality": job.modality,
                "provider": job.provider,
                "status": "failed",
            },
        )


def _run_comfyui_background(job_id: str, prompt: str, workflow_id: str | None, modality: str) -> None:
    job = JOBS.get(job_id)
    if job is None:
        return
    _mark_running(job)
    try:
        if modality != "video":
            raise ComfyUIError("本实例无文生图权重，图片请保持 AI_MOCK_IMAGE=true")
        settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
        dest = settings.artifacts_dir / job.id
        out = run_video_job(prompt, workflow_id, dest)
        if job_id not in JOBS:
            return
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
        model=settings.llm_model if provider == "llm" else ("minimax-h3" if provider == "comfyui" else "mock"),
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
        JOBS[job.id] = job
        job.output_url = _public_url(job.id)
        _save_jobs()
        background_tasks.add_task(_run_llm_background, job.id, req.prompt)
        return job
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
            "elapsed_ms": job.elapsed_ms,
        },
    )
    return job


def _filter_jobs(
    *,
    modality: str | None = None,
    provider: str | None = None,
    exclude_provider: str | None = None,
) -> list[Job]:
    items = list(JOBS.values())
    if modality:
        items = [j for j in items if j.modality == modality]
    if provider:
        items = [j for j in items if j.provider == provider]
    if exclude_provider:
        items = [j for j in items if j.provider != exclude_provider]
    return items


def _percentile(values: list[int], p: float) -> int | None:
    if not values:
        return None
    xs = sorted(values)
    idx = min(len(xs) - 1, max(0, round((p / 100.0) * (len(xs) - 1))))
    return xs[idx]


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _unlink_artifact(job: Job) -> None:
    if not job.output_uri:
        return
    path = Path(job.output_uri)
    if not path.is_file():
        path = settings.artifacts_dir / path.name
    try:
        artifacts = settings.artifacts_dir.resolve()
        resolved = path.resolve()
        if artifacts in resolved.parents or resolved.parent == artifacts:
            path.unlink(missing_ok=True)
    except OSError:
        pass


@app.get("/v1/jobs/stats")
def job_stats(
    modality: str | None = Query(default=None),
    provider: str | None = Query(default=None),
    exclude_provider: str | None = Query(default=None),
) -> dict:
    items = _filter_jobs(modality=modality, provider=provider, exclude_provider=exclude_provider)
    by_status = {"queued": 0, "running": 0, "succeeded": 0, "failed": 0}
    by_modality: dict[str, int] = {}
    by_provider: dict[str, int] = {}
    score_hist = {str(n): 0 for n in range(1, 6)}
    elapsed: list[int] = []
    scores: list[float] = []
    prompt_tokens: list[float] = []
    completion_tokens: list[float] = []
    for job in items:
        by_status[job.status] = by_status.get(job.status, 0) + 1
        by_modality[job.modality] = by_modality.get(job.modality, 0) + 1
        by_provider[job.provider] = by_provider.get(job.provider, 0) + 1
        if job.elapsed_ms is not None:
            elapsed.append(job.elapsed_ms)
        if job.score is not None:
            scores.append(float(job.score))
            score_hist[str(job.score)] += 1
        if job.prompt_tokens is not None:
            prompt_tokens.append(float(job.prompt_tokens))
        if job.completion_tokens is not None:
            completion_tokens.append(float(job.completion_tokens))
    done = by_status["succeeded"] + by_status["failed"]
    success_rate = round(by_status["succeeded"] / done, 4) if done else None
    log.info(
        "job_stats",
        extra={
            "run_id": "stats",
            "provider": provider or exclude_provider or "all",
            "status": "ok",
            "elapsed_ms": _avg([float(x) for x in elapsed]),
        },
    )
    return {
        "total": len(items),
        "by_status": by_status,
        "by_modality": by_modality,
        "by_provider": by_provider,
        "success_rate": success_rate,
        "scored_count": len(scores),
        "avg_score": _avg(scores),
        "score_hist": score_hist,
        "avg_elapsed_ms": int(_avg([float(x) for x in elapsed]) or 0) if elapsed else None,
        "p50_elapsed_ms": _percentile(elapsed, 50),
        "p95_elapsed_ms": _percentile(elapsed, 95),
        "avg_prompt_tokens": _avg(prompt_tokens),
        "avg_completion_tokens": _avg(completion_tokens),
    }


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


@app.delete("/v1/jobs/{job_id}")
def delete_job(job_id: str) -> dict:
    job = JOBS.pop(job_id, None)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    _unlink_artifact(job)
    _save_jobs()
    log.info(
        "job_deleted",
        extra={
            "run_id": job.run_id,
            "job_id": job.id,
            "modality": job.modality,
            "provider": job.provider,
            "status": job.status,
        },
    )
    return {"ok": True, "removed": job_id}


@app.delete("/v1/jobs")
def clear_jobs(provider: str | None = Query(default=None)) -> dict:
    removed: list[str] = []
    kept: dict[str, Job] = {}
    for job_id, job in JOBS.items():
        if provider and job.provider != provider:
            kept[job_id] = job
            continue
        removed.append(job_id)
        _unlink_artifact(job)
    JOBS.clear()
    JOBS.update(kept)
    _save_jobs()
    log.info(
        "jobs_cleared",
        extra={"run_id": "ops", "provider": provider or "all", "status": "ok"},
    )
    return {"ok": True, "removed": len(removed), "remaining": len(JOBS)}


@app.get("/v1/jobs")
def list_jobs(
    modality: str | None = Query(default=None),
    provider: str | None = Query(default=None),
    exclude_provider: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    items = _filter_jobs(modality=modality, provider=provider, exclude_provider=exclude_provider)
    items.sort(key=lambda j: j.created_at, reverse=True)
    return {"items": items[:limit], "total": len(items)}
