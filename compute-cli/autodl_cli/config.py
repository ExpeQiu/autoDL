from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

CLI_ROOT = Path(__file__).resolve().parent.parent
USER_CONFIG = Path.home() / ".autodl" / "config.yaml"

_TRUE = {"1", "true", "yes", "on"}


def _parse_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            out[key] = value
    return out


def load_env() -> None:
    """CLI 参数已在 os.environ 时不覆盖。文件只填补空缺。"""
    file_vals = _parse_dotenv(CLI_ROOT.parent / "platform" / ".env")
    file_vals.update(_parse_dotenv(CLI_ROOT / ".env"))
    if yaml is not None and USER_CONFIG.is_file():
        try:
            data = yaml.safe_load(USER_CONFIG.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            data = {}
        if isinstance(data, dict):
            for key, value in data.items():
                if value is None:
                    continue
                file_vals.setdefault(str(key), str(value))
    for key, value in file_vals.items():
        os.environ.setdefault(key, value)


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUE


def is_mock(demo: bool = False) -> bool:
    if demo:
        return True
    return _flag("AUTODL_MOCK", default=True)


def allow_power() -> bool:
    return _flag("AUTODL_ALLOW_POWER", default=False)


def get_log_level() -> str:
    return os.getenv("LOG_LEVEL", "INFO").upper()


def orch_base() -> str:
    return os.getenv("ORCH_BASE", "http://127.0.0.1:8090").rstrip("/")


def comfyui_endpoint() -> str:
    return os.getenv("COMFYUI_ENDPOINT", "http://127.0.0.1:8188").rstrip("/")


def llm_base_url() -> str:
    return os.getenv("LLM_BASE_URL", "http://127.0.0.1:8088").rstrip("/")


def token_set() -> bool:
    return bool(os.getenv("AUTODL_TOKEN", "").strip())


def instance_uuid() -> str:
    return os.getenv("AUTODL_INSTANCE_UUID", "").strip()


def ssh_host() -> str:
    return os.getenv("COMFYUI_SSH_HOST", "connect.westd.seetacloud.com").strip()


def ssh_port() -> str:
    return os.getenv("COMFYUI_SSH_PORT", "").strip()


def ssh_user() -> str:
    return os.getenv("COMFYUI_SSH_USER", "root").strip()


def ssh_password() -> str:
    return os.getenv("COMFYUI_SSH_PASSWORD", "").strip() or os.getenv("SSHPASS", "").strip()


def config_snapshot() -> dict[str, Any]:
    """给 config check 用的脱敏快照。"""
    return {
        "mock": is_mock(),
        "allow_power": allow_power(),
        "token_set": token_set(),
        "instance_uuid_set": bool(instance_uuid()),
        "orch_base": orch_base(),
        "comfyui_endpoint": comfyui_endpoint(),
        "llm_base_url": llm_base_url(),
        "ssh_host": ssh_host(),
        "ssh_port_set": bool(ssh_port()),
        "ssh_password_set": bool(ssh_password()),
        "ssh_user": ssh_user(),
        "env_file": str(CLI_ROOT / ".env"),
        "user_config": str(USER_CONFIG),
    }
