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

HOST="${COMFYUI_SSH_HOST:-connect.westc.seetacloud.com}"
PORT="${COMFYUI_SSH_PORT:-}"
USER="${COMFYUI_SSH_USER:-root}"
LOCAL_COMFY="${COMFYUI_LOCAL_PORT:-8188}"
REMOTE_COMFY="${COMFYUI_REMOTE_PORT:-8188}"
LOCAL_LLM="${LLM_LOCAL_PORT:-8088}"
REMOTE_LLM="${LLM_REMOTE_PORT:-8088}"
# 文本测试只转 8088，避免本机 8188 已被占用时 ExitOnForwardFailure 整条隧道失败
LLM_ONLY="${TUNNEL_LLM_ONLY:-0}"

if [[ -z "$PORT" ]]; then
  echo "FAIL: set COMFYUI_SSH_PORT（开机后以 AutoDL 控制台为准）" >&2
  exit 1
fi

args=(
  -N
  -o ServerAliveInterval=30
  -o ExitOnForwardFailure=yes
  -o StrictHostKeyChecking=no
  -L "${LOCAL_LLM}:127.0.0.1:${REMOTE_LLM}"
)
if [[ "$LLM_ONLY" != "1" ]]; then
  args+=(-L "${LOCAL_COMFY}:127.0.0.1:${REMOTE_COMFY}")
fi
args+=(-p "$PORT" "${USER}@${HOST}")

if [[ "$LLM_ONLY" == "1" ]]; then
  echo "tunnel 127.0.0.1:${LOCAL_LLM}->:${REMOTE_LLM}  ${USER}@${HOST}:${PORT}  (llm-only)"
else
  echo "tunnel 127.0.0.1:${LOCAL_COMFY}->:${REMOTE_COMFY}  127.0.0.1:${LOCAL_LLM}->:${REMOTE_LLM}  ${USER}@${HOST}:${PORT}"
fi

if [[ -n "${COMFYUI_SSH_PASSWORD:-}" ]] && command -v sshpass >/dev/null 2>&1; then
  exec sshpass -p "$COMFYUI_SSH_PASSWORD" ssh "${args[@]}"
fi
exec ssh "${args[@]}"
