#!/usr/bin/env bash
# 停止 AutoDL 上的 llama-server
set -euo pipefail

PID_FILE=/root/autodl-tmp/logs/llama.pid
PORT="${LLM_PORT:-8088}"

if [ -f "$PID_FILE" ]; then
  pid=$(cat "$PID_FILE")
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" || true
    sleep 1
    kill -9 "$pid" 2>/dev/null || true
    echo "stopped pid=$pid"
  fi
  rm -f "$PID_FILE"
fi

if command -v fuser >/dev/null 2>&1; then
  fuser -k "${PORT}/tcp" 2>/dev/null || true
fi
echo "llama-server stopped"
