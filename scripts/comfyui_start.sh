#!/usr/bin/env bash
# 在 AutoDL 实例内启动 ComfyUI（:8188）
set -euo pipefail

INSTALL_DIR=/root/autodl-tmp/ComfyUI
LOG_DIR=/root/autodl-tmp/logs
LOG="$LOG_DIR/comfyui.log"
PID_FILE="$LOG_DIR/comfyui.pid"
PORT="${COMFYUI_PORT:-8188}"

mkdir -p "$LOG_DIR"
export PATH=/root/miniconda3/bin:${PATH:-/usr/bin:/bin}
if [ -f /root/miniconda3/etc/profile.d/conda.sh ]; then
  # shellcheck source=/dev/null
  source /root/miniconda3/etc/profile.d/conda.sh
  conda activate base
fi

if [ ! -f "$INSTALL_DIR/main.py" ]; then
  echo "ERROR: ComfyUI 未安装: $INSTALL_DIR" >&2
  exit 1
fi

if curl -fsS -m 3 "http://127.0.0.1:${PORT}/system_stats" >/dev/null 2>&1; then
  echo "ComfyUI already healthy on :$PORT"
  exit 0
fi

if [ -f "$PID_FILE" ]; then
  old=$(cat "$PID_FILE" || true)
  if [ -n "${old:-}" ] && kill -0 "$old" 2>/dev/null; then
    echo "stale listen? pid=$old still running, waiting health"
  else
    rm -f "$PID_FILE"
  fi
fi

cd "$INSTALL_DIR"
echo "===== $(date -Iseconds) START comfyui port=$PORT =====" >>"$LOG"
nohup python main.py --listen 0.0.0.0 --port "$PORT" >>"$LOG" 2>&1 &
echo $! >"$PID_FILE"
echo "pid=$(cat "$PID_FILE") log=$LOG"

for i in $(seq 1 60); do
  if curl -fsS -m 3 "http://127.0.0.1:${PORT}/system_stats" >/dev/null 2>&1; then
    echo "healthy after ${i}s"
    curl -sS -m 5 "http://127.0.0.1:${PORT}/system_stats" | python -m json.tool | head -40
    exit 0
  fi
  sleep 2
done

echo "ERROR: ComfyUI 未在 120s 内就绪，见 $LOG" >&2
tail -50 "$LOG" >&2
exit 1
