from __future__ import annotations

from typing import Any

DEMO_SERVICES: list[dict[str, Any]] = [
    {
        "id": "llm.chat",
        "modality": "text",
        "label": "文本对话",
        "provider": "llm",
        "workflow_id": "llm.chat",
        "exposed": True,
        "description": "llama.cpp / Mock 文本",
    },
    {
        "id": "t2i.demo",
        "modality": "image",
        "label": "文生图",
        "provider": "comfyui",
        "workflow_id": "t2i.demo",
        "exposed": True,
        "description": "ComfyUI / Mock 图片",
    },
    {
        "id": "t2v.u03",
        "modality": "video",
        "label": "文生视频 H3",
        "provider": "comfyui",
        "workflow_id": "t2v.u03",
        "exposed": True,
        "description": "MiniMax H3 / Mock 视频",
    },
]


def with_invoke(item: dict[str, Any]) -> dict[str, Any]:
    return {
        **item,
        "invoke": {
            "group": "job",
            "action": "submit",
            "args": {"modality": item.get("modality"), "workflow": item.get("workflow_id")},
        },
    }


def demo_items(*, exposed_only: bool = False, modality: str | None = None) -> list[dict[str, Any]]:
    rows = list(DEMO_SERVICES)
    if exposed_only:
        rows = [item for item in rows if item.get("exposed")]
    if modality:
        rows = [item for item in rows if item.get("modality") == modality]
    return [with_invoke(item) for item in rows]
