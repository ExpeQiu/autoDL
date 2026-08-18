from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ai_mock_mode: bool = True
    ai_mock_text: bool = True
    ai_mock_image: bool = True
    orch_host: str = "127.0.0.1"
    orch_port: int = 8090
    log_level: str = "INFO"
    comfyui_endpoint: str = "http://127.0.0.1:8188"
    comfyui_timeout_ms: int = 1800000
    comfyui_poll_interval_ms: int = 3000
    comfyui_video_width: int = 768
    comfyui_video_height: int = 768
    comfyui_video_length: int = 73
    comfyui_video_steps: int = 4
    llm_base_url: str = "http://127.0.0.1:8088"
    llm_api_key: str = "sk-local"
    llm_model: str = "qwen3-8b"
    llm_timeout_s: float = 180.0
    artifacts_dir: Path = ROOT / "artifacts"
    sqlite_path: Path = ROOT / "data" / "jobs.sqlite"
    log_path: Path = ROOT / "logs" / "orchestrator.log"


settings = Settings()
if not settings.artifacts_dir.is_absolute():
    settings.artifacts_dir = (ROOT / settings.artifacts_dir).resolve()
if not settings.sqlite_path.is_absolute():
    settings.sqlite_path = (ROOT / settings.sqlite_path).resolve()
if not settings.log_path.is_absolute():
    settings.log_path = (ROOT / settings.log_path).resolve()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "msg": record.getMessage(),
            "logger": record.name,
        }
        for key in ("run_id", "job_id", "modality", "provider", "status", "elapsed_ms"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> logging.Logger:
    settings.log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("genlab")
    if logger.handlers:
        return logger
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    formatter = JsonFormatter()
    file_handler = logging.FileHandler(settings.log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.propagate = False
    return logger
