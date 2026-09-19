from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from .config import settings

Profile = Literal["local", "autodl"]
SshAuth = Literal["password", "key"]
ModalityName = Literal["text", "image", "video"]
SECRET_KEEP_EMPTY = {"autodl_ssh_password"}
LANE_KEYS = (
    "local_text",
    "local_image",
    "local_video",
    "autodl_text",
    "autodl_image",
    "autodl_video",
)


class ModalityLane(BaseModel):
    enabled: bool = True
    mock: bool = False
    endpoint: str = Field(default="http://127.0.0.1:8088", min_length=1, max_length=200)
    model: str = Field(default="", max_length=80)
    tunnel_local: int = Field(default=0, ge=0, le=65535)
    tunnel_remote: int = Field(default=0, ge=0, le=65535)


class AccessConfig(BaseModel):
    profile: Profile = "autodl"
    mock_text: bool
    mock_image: bool
    mock_video: bool
    comfyui_endpoint: str = Field(min_length=1, max_length=200)
    llm_base_url: str = Field(min_length=1, max_length=200)
    llm_model: str = Field(min_length=1, max_length=80)
    local_comfyui_endpoint: str = Field(default="http://127.0.0.1:8188", min_length=1, max_length=200)
    local_llm_base_url: str = Field(default="http://127.0.0.1:8088", min_length=1, max_length=200)
    local_llm_model: str = Field(default="qwen3-8b", min_length=1, max_length=80)
    autodl_comfyui_endpoint: str = Field(default="http://127.0.0.1:8188", min_length=1, max_length=200)
    autodl_llm_base_url: str = Field(default="http://127.0.0.1:8088", min_length=1, max_length=200)
    autodl_llm_model: str = Field(default="qwen3.8-27b", min_length=1, max_length=80)
    autodl_ssh_host: str = Field(default="", max_length=200)
    autodl_ssh_port: int = Field(default=0, ge=0, le=65535)
    autodl_ssh_user: str = Field(default="root", max_length=80)
    autodl_ssh_auth: SshAuth = "password"
    autodl_ssh_key_path: str = Field(default="", max_length=400)
    autodl_ssh_password: str = Field(default="", max_length=200)
    local_text: ModalityLane = Field(default_factory=lambda: _default_text_lane("qwen3-8b"))
    local_image: ModalityLane = Field(default_factory=lambda: _default_comfy_lane("t2i.demo"))
    local_video: ModalityLane = Field(default_factory=lambda: _default_comfy_lane("t2v.u03"))
    autodl_text: ModalityLane = Field(default_factory=lambda: _default_text_lane("qwen3.8-27b"))
    autodl_image: ModalityLane = Field(default_factory=lambda: _default_comfy_lane("t2i.demo"))
    autodl_video: ModalityLane = Field(default_factory=lambda: _default_comfy_lane("t2v.u03"))


def _default_text_lane(model: str, *, mock: bool = False, endpoint: str = "http://127.0.0.1:8088") -> ModalityLane:
    return ModalityLane(
        enabled=True,
        mock=mock,
        endpoint=endpoint,
        model=model,
        tunnel_local=8088,
        tunnel_remote=8088,
    )


def _default_comfy_lane(model: str, *, mock: bool = False, endpoint: str = "http://127.0.0.1:8188") -> ModalityLane:
    return ModalityLane(
        enabled=True,
        mock=mock,
        endpoint=endpoint,
        model=model,
        tunnel_local=8188,
        tunnel_remote=8188,
    )


def access_path() -> Path:
    return settings.sqlite_path.parent / "access.json"


def defaults_from_env() -> AccessConfig:
    comfy = str(settings.comfyui_endpoint)
    llm = str(settings.llm_base_url)
    model = str(settings.llm_model)
    return AccessConfig(
        profile="autodl",
        mock_text=settings.ai_mock_text,
        mock_image=settings.ai_mock_image,
        mock_video=settings.ai_mock_mode,
        comfyui_endpoint=comfy,
        llm_base_url=llm,
        llm_model=model,
        local_comfyui_endpoint=comfy,
        local_llm_base_url=llm,
        local_llm_model=model,
        autodl_comfyui_endpoint=comfy,
        autodl_llm_base_url=llm,
        autodl_llm_model=model,
        autodl_ssh_host=str(settings.comfyui_ssh_host or ""),
        autodl_ssh_port=int(settings.comfyui_ssh_port or 0),
        autodl_ssh_user=str(settings.comfyui_ssh_user or "root"),
        autodl_ssh_auth="key" if str(settings.comfyui_ssh_key_path or "").strip() else "password",
        autodl_ssh_key_path=str(settings.comfyui_ssh_key_path or ""),
        autodl_ssh_password=os.getenv("COMFYUI_SSH_PASSWORD") or "",
        local_text=_default_text_lane(model, mock=settings.ai_mock_text, endpoint=llm),
        local_image=_default_comfy_lane("t2i.demo", mock=settings.ai_mock_image, endpoint=comfy),
        local_video=_default_comfy_lane("t2v.u03", mock=settings.ai_mock_mode, endpoint=comfy),
        autodl_text=_default_text_lane(model, mock=settings.ai_mock_text, endpoint=llm),
        autodl_image=_default_comfy_lane("t2i.demo", mock=settings.ai_mock_image, endpoint=comfy),
        autodl_video=_default_comfy_lane("t2v.u03", mock=settings.ai_mock_mode, endpoint=comfy),
    )


def _seed_split_from_legacy(raw: dict[str, Any], data: dict[str, Any]) -> None:
    """旧文件只有一套 Host 时，两套路径都先抄过来；已写出的分套字段不盖。"""
    split_keys = (
        "local_comfyui_endpoint",
        "local_llm_base_url",
        "local_llm_model",
        "autodl_comfyui_endpoint",
        "autodl_llm_base_url",
        "autodl_llm_model",
    )
    if any(key in raw for key in split_keys):
        return
    pairs = (
        ("comfyui_endpoint", "local_comfyui_endpoint", "autodl_comfyui_endpoint"),
        ("llm_base_url", "local_llm_base_url", "autodl_llm_base_url"),
        ("llm_model", "local_llm_model", "autodl_llm_model"),
    )
    for active, local_key, autodl_key in pairs:
        legacy = raw.get(active)
        if not isinstance(legacy, str) or not legacy.strip():
            continue
        data[local_key] = legacy
        data[autodl_key] = legacy


def _hydrate_lane(raw: Any, base: dict[str, Any]) -> dict[str, Any]:
    data = dict(base)
    if not isinstance(raw, dict):
        return data
    for key in ModalityLane.model_fields:
        if key not in raw or raw[key] is None:
            continue
        data[key] = raw[key]
    return ModalityLane.model_validate(data).model_dump()


def _lane_key(profile: str, modality: str) -> str:
    prefix = "local" if profile == "local" else "autodl"
    return f"{prefix}_{modality}"


def _patch_lane_field(data: dict[str, Any], lane_key: str, field: str, value: Any) -> None:
    lane = dict(data.get(lane_key) or {})
    lane[field] = value
    data[lane_key] = lane


def _apply_aliases_to_lanes(raw: dict[str, Any], data: dict[str, Any]) -> None:
    """旧 PUT / 旧文件只写 mock_*、Host 时，补到对应通道；已写出的 nested lane 不盖。"""
    profile = data.get("profile") or "autodl"
    if not isinstance(profile, str):
        profile = "autodl"

    def lane_written(modality: str, *, profile_name: str | None = None) -> bool:
        key = _lane_key(profile_name or profile, modality)
        return isinstance(raw.get(key), dict)

    if "mock_text" in raw and raw["mock_text"] is not None:
        if not lane_written("text", profile_name="autodl"):
            _patch_lane_field(data, "autodl_text", "mock", bool(raw["mock_text"]))
        if not lane_written("text", profile_name="local"):
            _patch_lane_field(data, "local_text", "mock", bool(raw["mock_text"]))
    if "mock_image" in raw and raw["mock_image"] is not None:
        if not lane_written("image", profile_name="autodl"):
            _patch_lane_field(data, "autodl_image", "mock", bool(raw["mock_image"]))
        if not lane_written("image", profile_name="local"):
            _patch_lane_field(data, "local_image", "mock", bool(raw["mock_image"]))
    if "mock_video" in raw and raw["mock_video"] is not None:
        if not lane_written("video", profile_name="autodl"):
            _patch_lane_field(data, "autodl_video", "mock", bool(raw["mock_video"]))
        if not lane_written("video", profile_name="local"):
            _patch_lane_field(data, "local_video", "mock", bool(raw["mock_video"]))

    pairs = (
        ("llm_base_url", "text", "endpoint", None),
        ("llm_model", "text", "model", None),
        ("comfyui_endpoint", "image", "endpoint", "video"),
        ("local_llm_base_url", "text", "endpoint", None),
        ("local_llm_model", "text", "model", None),
        ("local_comfyui_endpoint", "image", "endpoint", "video"),
        ("autodl_llm_base_url", "text", "endpoint", None),
        ("autodl_llm_model", "text", "model", None),
        ("autodl_comfyui_endpoint", "image", "endpoint", "video"),
    )
    for alias, modality, field, extra in pairs:
        if alias not in raw or raw[alias] is None:
            continue
        value = raw[alias]
        if field == "endpoint" and isinstance(value, str):
            value = value.rstrip("/")
        if alias.startswith("local_"):
            targets = ("local",)
        elif alias.startswith("autodl_"):
            targets = ("autodl",)
        else:
            targets = (profile,)
        for target in targets:
            if not lane_written(modality, profile_name=target):
                _patch_lane_field(data, _lane_key(target, modality), field, value)
            if extra and not lane_written(extra, profile_name=target):
                _patch_lane_field(data, _lane_key(target, extra), field, value)


def hydrate_access(raw: Any, *, env: AccessConfig | None = None) -> AccessConfig:
    """已写出的字段（含 false / 空串 / 空列表）保留；仅缺 key 时用 env。空密码不盖已保存密钥。"""
    base = env or defaults_from_env()
    if not isinstance(raw, dict):
        return sync_active(base.model_copy())
    data = base.model_dump()
    for key in AccessConfig.model_fields:
        if key not in raw or raw[key] is None:
            continue
        if key in SECRET_KEEP_EMPTY and raw[key] == "":
            continue
        if key in LANE_KEYS:
            if isinstance(raw[key], dict):
                data[key] = _hydrate_lane(raw[key], data[key])
            continue
        data[key] = raw[key]
    _seed_split_from_legacy(raw, data)
    _apply_aliases_to_lanes(raw, data)
    return sync_active(AccessConfig.model_validate(data))


def load_access() -> AccessConfig:
    path = access_path()
    if not path.is_file():
        return defaults_from_env()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return hydrate_access(raw)
    except (OSError, json.JSONDecodeError, ValidationError):
        return defaults_from_env()


def _effective_mock(lane: ModalityLane) -> bool:
    return (not lane.enabled) or lane.mock


def _norm_lane(lane: ModalityLane) -> ModalityLane:
    return lane.model_copy(
        update={
            "endpoint": (lane.endpoint or "").rstrip("/") or lane.endpoint,
            "model": (lane.model or "").strip(),
        }
    )


def _comfy_endpoint(image: ModalityLane, video: ModalityLane) -> str:
    if image.enabled:
        return image.endpoint.rstrip("/")
    return video.endpoint.rstrip("/")


def profile_lanes(cfg: AccessConfig) -> tuple[ModalityLane, ModalityLane, ModalityLane]:
    if cfg.profile == "local":
        return cfg.local_text, cfg.local_image, cfg.local_video
    return cfg.autodl_text, cfg.autodl_image, cfg.autodl_video


def active_lane(cfg: AccessConfig, modality: ModalityName) -> ModalityLane:
    text, image, video = profile_lanes(cfg)
    if modality == "text":
        return text
    if modality == "image":
        return image
    return video


def sync_active(cfg: AccessConfig) -> AccessConfig:
    local_text = _norm_lane(cfg.local_text)
    local_image = _norm_lane(cfg.local_image)
    local_video = _norm_lane(cfg.local_video)
    autodl_text = _norm_lane(cfg.autodl_text)
    autodl_image = _norm_lane(cfg.autodl_image)
    autodl_video = _norm_lane(cfg.autodl_video)
    if cfg.profile == "local":
        text, image, video = local_text, local_image, local_video
    else:
        text, image, video = autodl_text, autodl_image, autodl_video
    llm = text.endpoint.rstrip("/")
    model = text.model or cfg.llm_model
    comfy = _comfy_endpoint(image, video)
    return cfg.model_copy(
        update={
            "local_text": local_text,
            "local_image": local_image,
            "local_video": local_video,
            "autodl_text": autodl_text,
            "autodl_image": autodl_image,
            "autodl_video": autodl_video,
            "mock_text": _effective_mock(text),
            "mock_image": _effective_mock(image),
            "mock_video": _effective_mock(video),
            "llm_base_url": llm,
            "llm_model": model,
            "comfyui_endpoint": comfy,
            "local_llm_base_url": local_text.endpoint.rstrip("/"),
            "local_llm_model": local_text.model or cfg.local_llm_model,
            "local_comfyui_endpoint": _comfy_endpoint(local_image, local_video),
            "autodl_llm_base_url": autodl_text.endpoint.rstrip("/"),
            "autodl_llm_model": autodl_text.model or cfg.autodl_llm_model,
            "autodl_comfyui_endpoint": _comfy_endpoint(autodl_image, autodl_video),
            "autodl_ssh_host": (cfg.autodl_ssh_host or "").strip(),
            "autodl_ssh_user": (cfg.autodl_ssh_user or "root").strip() or "root",
            "autodl_ssh_key_path": (cfg.autodl_ssh_key_path or "").strip(),
        }
    )


def apply_access(cfg: AccessConfig) -> AccessConfig:
    synced = sync_active(cfg)
    text, image, video = profile_lanes(synced)
    settings.ai_mock_text = synced.mock_text
    settings.ai_mock_image = synced.mock_image
    settings.ai_mock_mode = synced.mock_video
    settings.comfyui_endpoint = image.endpoint.rstrip("/") if image.enabled else video.endpoint.rstrip("/")
    settings.comfyui_video_endpoint = video.endpoint.rstrip("/")
    settings.llm_base_url = text.endpoint.rstrip("/")
    settings.llm_model = text.model or synced.llm_model
    logging.getLogger("genlab").info(
        "access_apply",
        extra={
            "run_id": "access",
            "status": synced.profile,
            "service_id": synced.profile,
            "provider": synced.profile,
            "modality": f"t={int(text.enabled)}/{int(text.mock)} i={int(image.enabled)}/{int(image.mock)} v={int(video.enabled)}/{int(video.mock)}",
        },
    )
    return synced


def save_access(cfg: AccessConfig) -> AccessConfig:
    path = access_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    applied = apply_access(cfg)
    path.write_text(json.dumps(applied.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    return applied


def public_access(cfg: AccessConfig) -> dict[str, Any]:
    payload = cfg.model_dump()
    secret = payload.pop("autodl_ssh_password", "") or ""
    payload["autodl_ssh_password_set"] = bool(secret)
    return {
        "ok": True,
        **payload,
        "orch_host": settings.orch_host,
        "orch_port": settings.orch_port,
    }


# 启动时叠已保存接入，禁止每次请求用 .env 盖回
apply_access(load_access())
