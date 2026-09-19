#!/usr/bin/env bash
# SSH 本地转发 AutoDL：ComfyUI :8188 + llama.cpp :8088
# 用法：在 platform 目录 source .env 后 ./scripts/tunnel.sh
# 密码用 COMFYUI_SSH_PASSWORD 或 SSHPASS，不要写进仓库。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -f "$ROOT/.env" ]]; then
  # shellcheck disable=SC1091
  set -a
  source "$ROOT/.env"
  set +a
fi

ACCESS_JSON="$ROOT/data/access.json"
if [[ -f "$ACCESS_JSON" ]]; then
  overlay="$(python3 - "$ACCESS_JSON" <<'PY'
import json, shlex, sys
raw = json.loads(open(sys.argv[1], encoding="utf-8").read())
mapping = {
    "autodl_ssh_host": "COMFYUI_SSH_HOST",
    "autodl_ssh_user": "COMFYUI_SSH_USER",
    "autodl_ssh_key_path": "COMFYUI_SSH_KEY_PATH",
    "autodl_ssh_password": "COMFYUI_SSH_PASSWORD",
}
for src, dest in mapping.items():
    value = raw.get(src)
    if isinstance(value, str) and value.strip():
        print(f"export {dest}={shlex.quote(value.strip())}")
port = raw.get("autodl_ssh_port") or 0
if isinstance(port, int) and port > 0:
    print(f"export COMFYUI_SSH_PORT={port}")

def lane(key):
    value = raw.get(key)
    return value if isinstance(value, dict) else {}

text = lane("autodl_text")
image = lane("autodl_image")
video = lane("autodl_video")
need_llm = bool(text.get("enabled", True)) and not text.get("mock")
need_comfy = (bool(image.get("enabled", True)) and not image.get("mock")) or (
    bool(video.get("enabled", True)) and not video.get("mock")
)
if need_llm:
    local = int(text.get("tunnel_local") or 8088)
    remote = int(text.get("tunnel_remote") or 8088)
    print(f"export LLM_LOCAL_PORT={local}")
    print(f"export LLM_REMOTE_PORT={remote}")
if need_comfy:
    src = image if (image.get("enabled", True) and not image.get("mock")) else video
    local = int(src.get("tunnel_local") or 8188)
    remote = int(src.get("tunnel_remote") or 8188)
    print(f"export COMFYUI_LOCAL_PORT={local}")
    print(f"export COMFYUI_REMOTE_PORT={remote}")
if need_llm and not need_comfy:
    print("export TUNNEL_LLM_ONLY=1")
elif need_comfy and not need_llm:
    print("export TUNNEL_COMFY_ONLY=1")
elif not need_llm and not need_comfy:
    print("export TUNNEL_SKIP=1")
PY
)"
  eval "$overlay"
fi

HOST="${COMFYUI_SSH_HOST:-connect.westc.seetacloud.com}"
PORT="${COMFYUI_SSH_PORT:-}"
USER="${COMFYUI_SSH_USER:-root}"
LOCAL_COMFY="${COMFYUI_LOCAL_PORT:-8188}"
REMOTE_COMFY="${COMFYUI_REMOTE_PORT:-8188}"
LOCAL_LLM="${LLM_LOCAL_PORT:-8088}"
REMOTE_LLM="${LLM_REMOTE_PORT:-8088}"
# 文本只转 8088，视频只转 8188；两者同时为 1 时以视频为准
LLM_ONLY="${TUNNEL_LLM_ONLY:-0}"
COMFY_ONLY="${TUNNEL_COMFY_ONLY:-0}"
if [[ "${TUNNEL_SKIP:-0}" == "1" ]]; then
  echo "tunnel skip: autodl 文/图/视频均 Mock 或未启用"
  exit 0
fi
if [[ "$COMFY_ONLY" == "1" ]]; then
  LLM_ONLY=0
fi

if [[ -z "$PORT" ]]; then
  echo "FAIL: set COMFYUI_SSH_PORT（开机后以 AutoDL 控制台为准）" >&2
  exit 1
fi

args=(
  -N
  -o ServerAliveInterval=30
  -o ExitOnForwardFailure=yes
  -o StrictHostKeyChecking=no
)
if [[ "$COMFY_ONLY" == "1" ]]; then
  args+=(-L "${LOCAL_COMFY}:127.0.0.1:${REMOTE_COMFY}")
  echo "tunnel 127.0.0.1:${LOCAL_COMFY}->:${REMOTE_COMFY}  ${USER}@${HOST}:${PORT}  (comfy-only)"
elif [[ "$LLM_ONLY" == "1" ]]; then
  args+=(-L "${LOCAL_LLM}:127.0.0.1:${REMOTE_LLM}")
  echo "tunnel 127.0.0.1:${LOCAL_LLM}->:${REMOTE_LLM}  ${USER}@${HOST}:${PORT}  (llm-only)"
else
  args+=(
    -L "${LOCAL_COMFY}:127.0.0.1:${REMOTE_COMFY}"
    -L "${LOCAL_LLM}:127.0.0.1:${REMOTE_LLM}"
  )
  echo "tunnel 127.0.0.1:${LOCAL_COMFY}->:${REMOTE_COMFY}  127.0.0.1:${LOCAL_LLM}->:${REMOTE_LLM}  ${USER}@${HOST}:${PORT}"
fi

args+=(-p "$PORT" "${USER}@${HOST}")

KEY_PATH="${COMFYUI_SSH_KEY_PATH:-}"
if [[ -n "$KEY_PATH" ]]; then
  args+=(-i "$KEY_PATH")
fi

if [[ -z "$KEY_PATH" && -n "${COMFYUI_SSH_PASSWORD:-}" ]] && command -v sshpass >/dev/null 2>&1; then
  exec sshpass -p "$COMFYUI_SSH_PASSWORD" ssh "${args[@]}"
fi
exec ssh "${args[@]}"
