from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

Modality = Literal["text", "image", "video"]
JobStatus = Literal["queued", "running", "succeeded", "failed"]
Provider = Literal["mock", "comfyui", "llm"]


class JobCreate(BaseModel):
    modality: Modality
    prompt: str = Field(min_length=1, max_length=8000)
    suite_id: str | None = None
    case_id: str | None = None
    workflow_id: str | None = None
    run_id: str | None = None


class Job(BaseModel):
    id: str
    run_id: str
    modality: Modality
    prompt: str
    suite_id: str | None = None
    case_id: str | None = None
    workflow_id: str | None = None
    status: JobStatus
    provider: Provider
    output_uri: str | None = None
    output_url: str | None = None
    error: str | None = None
    score: int | None = Field(default=None, ge=1, le=5)
    created_at: datetime
    updated_at: datetime


class ScoreUpdate(BaseModel):
    score: int = Field(ge=1, le=5)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
