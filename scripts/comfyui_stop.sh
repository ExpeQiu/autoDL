#!/usr/bin/env bash
# 停止 AutoDL 实例内的 ComfyUI
set -euo pipefail

LOG_DIR=/root/autodl-tmp/logs
PID_FILE="$LOG_DIR/comfyui.pid"
PORT="${COMFYUI_PORT:-8188}"

stop_pid() {
  local pid=$1
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    echo "kill $pid"
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 15); do
      kill -0 "$pid" 2>/dev/null || return 0
      sleep 1
    done
    kill -9 "$pid" 2>/dev/null || true
  fi
}

if [ -f "$PID_FILE" ]; then
  stop_pid "$(cat "$PID_FILE" || true)"
  rm -f "$PID_FILE"
fi

# 兜底：按端口回收
pids=$(ss -ltnp 2>/dev/null | awk -v p=":${PORT}" '$4 ~ p {print}' | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u || true)
for pid in $pids; do
  stop_pid "$pid"
done

echo "stopped port=$PORT"
