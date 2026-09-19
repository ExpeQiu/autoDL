from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .config import settings

Modality = Literal["text", "image", "video"]
Provider = Literal["mock", "comfyui", "llm"]


class ExposedService(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    modality: Modality
    label: str = Field(min_length=1, max_length=80)
    provider: Provider
    workflow_id: str = Field(min_length=1, max_length=64)
    exposed: bool = True
    description: str = ""


DEFAULT_SERVICES: list[ExposedService] = [
    ExposedService(
        id="llm.chat",
        modality="text",
        label="文本对话",
        provider="llm",
        workflow_id="llm.chat",
        exposed=True,
        description="llama.cpp / Mock 文本",
    ),
    ExposedService(
        id="t2i.demo",
        modality="image",
        label="文生图",
        provider="comfyui",
        workflow_id="t2i.demo",
        exposed=True,
        description="ComfyUI / Mock 图片",
    ),
    ExposedService(
        id="t2v.u03",
        modality="video",
        label="文生视频 H3",
        provider="comfyui",
        workflow_id="t2v.u03",
        exposed=True,
        description="MiniMax H3 / Mock 视频",
    ),
]


def catalog_path() -> Path:
    return settings.sqlite_path.parent / "services.json"


def _defaults_by_id() -> dict[str, ExposedService]:
    return {item.id: item for item in DEFAULT_SERVICES}


def hydrate_services(raw: Any) -> list[ExposedService]:
    """已写出的条目（含 exposed=false）保留；仅缺 id 时补目录默认。"""
    saved_items: list[dict[str, Any]] = []
    if isinstance(raw, dict) and isinstance(raw.get("items"), list):
        saved_items = [x for x in raw["items"] if isinstance(x, dict)]
    elif isinstance(raw, list):
        saved_items = [x for x in raw if isinstance(x, dict)]

    saved_by_id: dict[str, ExposedService] = {}
    extras: list[ExposedService] = []
    defaults = _defaults_by_id()
    for item in saved_items:
        try:
            parsed = ExposedService.model_validate(item)
        except Exception:  # noqa: BLE001
            continue
        if parsed.id in defaults:
            saved_by_id[parsed.id] = parsed
        else:
            extras.append(parsed)

    merged: list[ExposedService] = []
    for default in DEFAULT_SERVICES:
        merged.append(saved_by_id.get(default.id, deepcopy(default)))
    merged.extend(extras)
    return merged


def load_services() -> list[ExposedService]:
    path = catalog_path()
    if not path.is_file():
        return [deepcopy(item) for item in DEFAULT_SERVICES]
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [deepcopy(item) for item in DEFAULT_SERVICES]
    return hydrate_services(raw)


def save_services(items: list[ExposedService]) -> list[ExposedService]:
    ids = [item.id for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("服务 id 不能重复")
    path = catalog_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"items": [item.model_dump() for item in items]}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return items


class ServicePut(BaseModel):
    items: list[ExposedService] = Field(default_factory=list)


class ServicePatch(BaseModel):
    exposed: bool | None = None
    label: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=400)


def patch_service(service_id: str, patch: ServicePatch) -> ExposedService:
    items = load_services()
    idx = next((i for i, item in enumerate(items) if item.id == service_id), None)
    if idx is None:
        raise KeyError(service_id)
    data = items[idx].model_dump()
    updates = patch.model_dump(exclude_unset=True)
    if not updates:
        return items[idx]
    data.update(updates)
    items[idx] = ExposedService.model_validate(data)
    save_services(items)
    return items[idx]


def public_items(items: list[ExposedService], *, exposed_only: bool) -> list[dict[str, Any]]:
    rows = items if not exposed_only else [item for item in items if item.exposed]
    return [
        {
            **item.model_dump(),
            "invoke": {
                "group": "job",
                "action": "submit",
                "args": {"modality": item.modality, "workflow": item.workflow_id},
            },
        }
        for item in rows
    ]
