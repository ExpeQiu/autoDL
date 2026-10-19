from __future__ import annotations

import hashlib
import html
from pathlib import Path

from ..config import settings
from ..models import Job, JobCreate, utcnow


def _write_artifact(job: Job, body: str, suffix: str) -> str:
    settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
    path = settings.artifacts_dir / f"{job.id}{suffix}"
    path.write_text(body, encoding="utf-8")
    return str(path)


def run_mock_job(job: Job, req: JobCreate) -> Job:
    digest = hashlib.sha1(req.prompt.encode("utf-8")).hexdigest()[:10]
    now = utcnow()
    job.status = "running"
    job.started_at = now
    job.updated_at = now
    job.model = "mock"

    if req.modality == "text":
        body = f"[mock-text] {req.prompt}\nrun_id={job.run_id} job_id={job.id}"
        uri = _write_artifact(job, body, ".txt")
    elif req.modality == "image":
        label = (req.prompt[:42] + "…") if len(req.prompt) > 42 else req.prompt
        label = html.escape(label)
        width = max(64, min(2048, int(req.width or 768)))
        height = max(64, min(2048, int(req.height or 512)))
        svg = (
            f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}'>"
            "<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>"
            "<stop offset='0%' stop-color='#1c1917'/><stop offset='100%' stop-color='#431407'/>"
            "</linearGradient></defs>"
            "<rect width='100%' height='100%' fill='url(#g)'/>"
            "<text x='40' y='230' fill='#fdba74' font-size='22' font-family='sans-serif'>MOCK IMAGE</text>"
            f"<text x='40' y='270' fill='#ffedd5' font-size='18' font-family='sans-serif'>{label}</text>"
            f"<text x='40' y='460' fill='#a8a29e' font-size='13' font-family='sans-serif'>{digest}</text>"
            "</svg>"
        )
        uri = _write_artifact(job, svg, ".svg")
    else:
        body = f"[mock-video] {req.prompt}\ndigest={digest}"
        uri = _write_artifact(job, body, ".mp4.txt")

    job.status = "succeeded"
    job.output_uri = uri
    job.finished_at = utcnow()
    job.updated_at = job.finished_at
    job.elapsed_ms = max(0, int((job.finished_at - (job.started_at or job.created_at)).total_seconds() * 1000))
    path = Path(uri)
    if path.is_file():
        job.output_bytes = path.stat().st_size
        if path.suffix.lower() == ".txt" or req.modality == "text":
            job.output_chars = len(path.read_text(encoding="utf-8"))
            job.prompt_tokens = max(1, len(req.prompt) // 4)
            job.completion_tokens = max(1, (job.output_chars or 1) // 4)
            job.total_tokens = (job.prompt_tokens or 0) + (job.completion_tokens or 0)
    return job
