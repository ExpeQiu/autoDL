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
    # 对齐 cyberspace：text | first_frame | first_last_frame | omni | i2i
    play_mode: str | None = Field(default=None, max_length=32)
    width: int | None = Field(default=None, ge=64, le=4096)
    height: int | None = Field(default=None, ge=64, le=4096)
    steps: int | None = Field(default=None, ge=1, le=8)
    seed: int | None = None
    duration: float | None = Field(default=None, ge=0, le=60)
    fps: int | None = Field(default=None, ge=1, le=60)
    # data URL、http(s) 或纯 base64。首帧 / 首尾帧的首帧。
    image_ref: str | None = Field(default=None, max_length=16_000_000)
    # 首尾帧的尾帧，编码同 image_ref。
    end_image_ref: str | None = Field(default=None, max_length=16_000_000)
    # 多图参考，2 到 9 张，编码同 image_ref。
    image_refs: list[str] | None = None


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
    model: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    elapsed_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    output_bytes: int | None = None
    output_chars: int | None = None
    created_at: datetime
    updated_at: datetime


class ScoreUpdate(BaseModel):
    score: int = Field(ge=1, le=5)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
