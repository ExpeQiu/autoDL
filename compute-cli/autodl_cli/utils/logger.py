from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from autodl_cli.config import CLI_ROOT, get_log_level

LOG_PATH = CLI_ROOT / "logs" / "autodl.log"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "msg": record.getMessage(),
            "logger": record.name,
        }
        cmd = getattr(record, "cmd", None)
        if cmd:
            payload["module"] = cmd
        for key in ("run_id", "job_id", "instance_uuid", "modality", "provider", "status"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False)


def setup_logger(verbose: bool = False, quiet: bool = False) -> logging.Logger:
    logger = logging.getLogger("autodl")
    logger.handlers.clear()
    if quiet:
        level = logging.WARNING
    elif verbose:
        level = logging.DEBUG
    else:
        level = getattr(logging, get_log_level(), logging.INFO)
    logger.setLevel(level)
    formatter = JsonFormatter()
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.propagate = False
    return logger
