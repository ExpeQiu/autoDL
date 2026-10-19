from __future__ import annotations

import hashlib
import html
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from autodl_cli.config import CLI_ROOT

STORE_PATH = CLI_ROOT / "data" / "jobs.json"
ARTIFACTS = CLI_ROOT / "artifacts"

Modality = Literal["text", "image", "video"]
DEFAULT_WORKFLOW = {
    "text": "llm.chat",
    "image": "t2i.demo",
    "video": "t2v.u03",
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> dict[str, dict[str, Any]]:
    if not STORE_PATH.is_file():
        return {}
    try:
        raw = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(raw, list):
        return {item["id"]: item for item in raw if isinstance(item, dict) and item.get("id")}
    if isinstance(raw, dict):
        return {str(k): v for k, v in raw.items() if isinstance(v, dict)}
    return {}


def _save(jobs: dict[str, dict[str, Any]]) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = list(jobs.values())
    STORE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_artifact(job_id: str, prompt: str, modality: Modality) -> str:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:10]
    if modality == "text":
        path = ARTIFACTS / f"{job_id}.txt"
        path.write_text(f"[mock-text] {prompt}\njob_id={job_id}\n", encoding="utf-8")
    elif modality == "image":
        path = ARTIFACTS / f"{job_id}.svg"
        label = html.escape(prompt[:42] + ("…" if len(prompt) > 42 else ""))
        path.write_text(
            "<svg xmlns='http://www.w3.org/2000/svg' width='768' height='512'>"
            "<rect width='100%' height='100%' fill='#1c1917'/>"
            "<text x='40' y='230' fill='#fdba74' font-size='22'>MOCK IMAGE</text>"
            f"<text x='40' y='270' fill='#ffedd5' font-size='18'>{label}</text>"
            f"<text x='40' y='460' fill='#a8a29e' font-size='13'>{digest}</text>"
            "</svg>",
            encoding="utf-8",
        )
    else:
        path = ARTIFACTS / f"{job_id}.mp4.txt"
        path.write_text(f"[mock-video] {prompt}\ndigest={digest}\n", encoding="utf-8")
    return str(path)


def create_demo_job(
    *,
    modality: Modality,
    prompt: str,
    workflow_id: str | None = None,
    run_id: str | None = None,
    suite_id: str | None = None,
    case_id: str | None = None,
    play_mode: str | None = None,
) -> dict[str, Any]:
    jobs = _load()
    run_id = run_id or f"run_{uuid.uuid4().hex[:12]}"
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    now = utcnow()
    workflow = workflow_id or DEFAULT_WORKFLOW[modality]
    job: dict[str, Any] = {
        "id": job_id,
        "run_id": run_id,
        "modality": modality,
        "prompt": prompt,
        "suite_id": suite_id,
        "case_id": case_id,
        "workflow_id": workflow,
        "play_mode": play_mode,
        "status": "succeeded",
        "provider": "mock",
        "output_uri": _write_artifact(job_id, prompt, modality),
        "error": None,
        "created_at": now,
        "updated_at": now,
    }
    jobs[job_id] = job
    _save(jobs)
    return job


def get_job(job_id: str) -> dict[str, Any] | None:
    return _load().get(job_id)


def list_jobs(modality: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    items = list(_load().values())
    if modality:
        items = [j for j in items if j.get("modality") == modality]
    items.sort(key=lambda j: str(j.get("created_at") or ""), reverse=True)
    return items[:limit]
