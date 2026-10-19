#!/usr/bin/env bash
# 把编排同步到算力机数据盘并只启动 :8090（不启动结果墙）。
# SSH 来自 platform/.env，密码不进日志、不写到远端 .env。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "FAIL: missing platform/.env" >&2
  exit 1
fi

# shellcheck disable=SC1091
set -a
source .env
set +a

HOST="${COMFYUI_SSH_HOST:-connect.westd.seetacloud.com}"
PORT="${COMFYUI_SSH_PORT:-}"
USER="${COMFYUI_SSH_USER:-root}"
REMOTE_DIR="${ORCH_REMOTE_DIR:-/root/autodl-tmp/platform}"
LOG_FILE="$ROOT/logs/deploy-remote.log"

mkdir -p "$ROOT/logs"
log() {
  printf '%s %s\n' "$(date -Iseconds)" "$*" | tee -a "$LOG_FILE"
}

if [[ -z "$PORT" ]]; then
  log "FAIL: set COMFYUI_SSH_PORT"
  exit 1
fi

SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 -p "$PORT")
if [[ -n "${COMFYUI_SSH_PASSWORD:-}" ]] && command -v sshpass >/dev/null 2>&1; then
  RSYNC_RSH="sshpass -e ssh ${SSH_OPTS[*]}"
  export SSHPASS="$COMFYUI_SSH_PASSWORD"
  remote() { sshpass -e ssh "${SSH_OPTS[@]}" "${USER}@${HOST}" "$@"; }
else
  RSYNC_RSH="ssh ${SSH_OPTS[*]}"
  remote() { ssh "${SSH_OPTS[@]}" "${USER}@${HOST}" "$@"; }
fi

log "sync platform -> ${USER}@${HOST}:${REMOTE_DIR} port=${PORT}"
remote "mkdir -p ${REMOTE_DIR}"
rsync -az --delete \
  --exclude '._*' \
  --exclude '.env' \
  --exclude '.venv/' \
  --exclude 'apps/web/' \
  --exclude 'node_modules/' \
  --exclude 'artifacts/' \
  --exclude 'data/' \
  --exclude 'logs/' \
  -e "$RSYNC_RSH" \
  "$ROOT/" "${USER}@${HOST}:${REMOTE_DIR}/"

log "write remote .env (no ssh password)"
remote "cat > ${REMOTE_DIR}/.env" <<'EOF'
AI_MOCK_MODE=false
AI_MOCK_TEXT=true
AI_MOCK_IMAGE=true
ORCH_HOST=127.0.0.1
ORCH_PORT=8090
LOG_LEVEL=INFO
SKIP_WEB=1
COMFYUI_ENDPOINT=http://127.0.0.1:8188
COMFYUI_VIDEO_ENDPOINT=http://127.0.0.1:8188
COMFYUI_TIMEOUT_MS=1800000
COMFYUI_POLL_INTERVAL_MS=3000
COMFYUI_VIDEO_WIDTH=768
COMFYUI_VIDEO_HEIGHT=768
COMFYUI_VIDEO_LENGTH=73
COMFYUI_VIDEO_STEPS=4
LLM_BASE_URL=http://127.0.0.1:8088
LLM_API_KEY=sk-local
LLM_MODEL=qwen3.8-27b
ARTIFACTS_DIR=./artifacts
SQLITE_PATH=./data/jobs.sqlite
EOF

log "start orchestrator SKIP_WEB=1"
remote "bash -lc 'chmod +x ${REMOTE_DIR}/scripts/*.sh ${REMOTE_DIR}/scripts/*.py && SKIP_WEB=1 bash ${REMOTE_DIR}/scripts/start.sh'"
log "remote health"
remote "curl -fsS -m 5 http://127.0.0.1:8090/health"
echo
log "PASS remote orchestrator"
