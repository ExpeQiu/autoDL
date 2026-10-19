#!/usr/bin/env bash
# 启动编排中枢（默认 Mock）。用法：./scripts/start.sh [--fg]
# SKIP_WEB=1 时只起编排，不装、不启动结果墙（算力机部署用）。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MODE="bg"
if [[ "${1:-}" == "--fg" ]]; then
  MODE="fg"
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "created .env from .env.example"
fi

# shellcheck disable=SC1091
set -a
source .env
set +a

HOST="${ORCH_HOST:-127.0.0.1}"
PORT="${ORCH_PORT:-8090}"
PID_FILE="$ROOT/logs/orchestrator.pid"
LOG_FILE="$ROOT/logs/orchestrator.stdout.log"
export COPYFILE_DISABLE=1

# Lexar 等外置卷会写 AppleDouble，pip 解析 dist-info 会炸；venv 放到本机盘
if [[ "${GENLAB_VENV:-}" != "" ]]; then
  VENV="$GENLAB_VENV"
elif [[ "$ROOT" == /Volumes/* ]]; then
  VENV="$HOME/.cache/autodl-genlab/venv"
else
  VENV="$ROOT/.venv"
fi

mkdir -p "$ROOT/logs" "$ROOT/artifacts" "$ROOT/data" "$(dirname "$VENV")"

PY="${PYTHON:-}"
if [[ -z "$PY" ]]; then
  for c in python3.12 python3.11 python3; do
    if command -v "$c" >/dev/null 2>&1; then
      PY="$c"
      break
    fi
  done
fi
if [[ -z "$PY" ]]; then
  echo "FAIL: no python3" >&2
  exit 1
fi

need_venv=0
if [[ ! -x "$VENV/bin/python" ]]; then
  need_venv=1
else
  vpy="$("$VENV/bin/python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
  tpy="$("$PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  if [[ "$vpy" != "$tpy" ]]; then
    need_venv=1
  fi
fi
if [[ "$need_venv" -eq 1 ]]; then
  rm -rf "$VENV"
  "$PY" -m venv "$VENV"
fi
export PIP_DISABLE_PIP_VERSION_CHECK=1
if ! "$VENV/bin/python" -c "import fastapi, uvicorn, httpx, pydantic_settings" 2>/dev/null; then
  "$VENV/bin/pip" install -q -r "$ROOT/orchestrator/requirements.txt"
fi

orch_running=0
if [[ -f "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE")"
  if kill -0 "$old_pid" 2>/dev/null; then
    echo "orchestrator already running pid=$old_pid port=$PORT"
    orch_running=1
  else
    rm -f "$PID_FILE"
  fi
fi

export PYTHONPATH="$ROOT/orchestrator:${PYTHONPATH:-}"
cmd=("$VENV/bin/python" -m uvicorn app.main:app --host "$HOST" --port "$PORT" --app-dir "$ROOT/orchestrator")

if [[ "$MODE" == "fg" ]]; then
  exec "${cmd[@]}"
fi

if [[ "$orch_running" -eq 0 ]]; then
  "$PY" "$ROOT/scripts/_spawn.py" --log "$LOG_FILE" -- "${cmd[@]}" >"$PID_FILE"
  sleep 0.8

  if ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "FAIL start orchestrator" >&2
    tail -40 "$LOG_FILE" >&2 || true
    exit 1
  fi
fi

code="$(curl -sS -m 5 -o /tmp/genlab-health.json -w "%{http_code}" "http://${HOST}:${PORT}/health" || true)"
if [[ "$code" != "200" ]]; then
  echo "FAIL health http=$code" >&2
  tail -40 "$LOG_FILE" >&2 || true
  exit 1
fi

if [[ "${SKIP_WEB:-0}" == "1" ]]; then
  echo "started orch=http://$HOST:$PORT  skip web (mock=${AI_MOCK_MODE:-true})"
  exit 0
fi

WEB_DIR="$ROOT/apps/web"
WEB_PORT="${WEB_PORT:-3190}"
WEB_PID_FILE="$ROOT/logs/web.pid"
WEB_LOG="$ROOT/logs/web.stdout.log"
export npm_config_cache="${npm_config_cache:-$HOME/.cache/npm}"

if [[ ! -d "$WEB_DIR/node_modules/next" ]]; then
  echo "installing web deps..."
  (cd "$WEB_DIR" && npm install --no-fund --no-audit)
fi

web_running=0
if [[ -f "$WEB_PID_FILE" ]]; then
  wpid="$(cat "$WEB_PID_FILE")"
  if kill -0 "$wpid" 2>/dev/null; then
    echo "web already running pid=$wpid port=$WEB_PORT"
    web_running=1
  else
    rm -f "$WEB_PID_FILE"
  fi
fi

if [[ "$web_running" -eq 0 ]]; then
  "$PY" "$ROOT/scripts/_spawn.py" --cwd "$WEB_DIR" --log "$WEB_LOG" -- \
    npx next dev --hostname 127.0.0.1 --port "$WEB_PORT" >"$WEB_PID_FILE"
  for _ in $(seq 1 60); do
    if curl -sS -L -m 1 -o /tmp/genlab-web.html "http://127.0.0.1:${WEB_PORT}/" 2>/dev/null \
      && grep -q "生成测试平台" /tmp/genlab-web.html; then
      break
    fi
    sleep 0.5
  done
fi

if ! curl -sS -L -m 8 -o /tmp/genlab-web.html "http://127.0.0.1:${WEB_PORT}/"; then
  echo "FAIL web unreachable" >&2
  tail -40 "$WEB_LOG" >&2 || true
  exit 1
fi
if ! grep -q "生成测试平台" /tmp/genlab-web.html; then
  echo "FAIL web page mismatch（端口 ${WEB_PORT} 可能被占用）" >&2
  tail -40 "$WEB_LOG" >&2 || true
  exit 1
fi

echo "started orch=http://$HOST:$PORT  打开 http://127.0.0.1:${WEB_PORT}/  （mock=${AI_MOCK_MODE:-true})"
