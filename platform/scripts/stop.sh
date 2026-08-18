#!/usr/bin/env bash
# 停止编排与前端
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$ROOT/logs/orchestrator.pid"
WEB_PID_FILE="$ROOT/logs/web.pid"
PORT="${ORCH_PORT:-8090}"
WEB_PORT="${WEB_PORT:-3190}"

if [[ -f "$ROOT/.env" ]]; then
  # shellcheck disable=SC1091
  set -a
  source "$ROOT/.env"
  set +a
  PORT="${ORCH_PORT:-8090}"
  WEB_PORT="${WEB_PORT:-3190}"
fi

stop_pidfile() {
  local file="$1"
  local label="$2"
  if [[ ! -f "$file" ]]; then
    return 0
  fi
  local pid
  pid="$(cat "$file")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    for _ in 1 2 3 4 5 6 7 8; do
      if ! kill -0 "$pid" 2>/dev/null; then
        break
      fi
      sleep 0.25
    done
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
    echo "stopped $label pid=$pid"
  fi
  rm -f "$file"
}

clear_port() {
  local port="$1"
  if ! command -v lsof >/dev/null 2>&1; then
    return 0
  fi
  local extra
  extra="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$extra" ]]; then
    echo "$extra" | xargs kill 2>/dev/null || true
    echo "cleared port=$port pids=$extra"
  fi
}

stop_pidfile "$WEB_PID_FILE" "web"
stop_pidfile "$PID_FILE" "orchestrator"
clear_port "$WEB_PORT"
clear_port "$PORT"
