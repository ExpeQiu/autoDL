#!/usr/bin/env bash
# 在 AutoDL 实例内启动 llama-server（OpenAI 兼容 :8088）
set -euo pipefail

ROOT=/root/autodl-tmp
BIN="$ROOT/llama.cpp/build/bin/llama-server"
MODEL="${LLM_MODEL_PATH:-$ROOT/models/Qwen3.8-27B-Uncensored-Q4_K_M.gguf}"
PORT="${LLM_PORT:-8088}"
LOG_DIR="$ROOT/logs"
LOG="$LOG_DIR/llama.log"
PID_FILE="$LOG_DIR/llama.pid"
ALIAS="${LLM_ALIAS:-qwen3.8-27b}"

mkdir -p "$LOG_DIR"
export PATH=/usr/local/cuda/bin:${PATH:-/usr/bin:/bin}

if [ ! -x "$BIN" ]; then
  echo "ERROR: 未编译 llama-server，先跑 llama_install.sh" >&2
  exit 1
fi
if [ ! -f "$MODEL" ]; then
  echo "ERROR: 模型不存在 $MODEL，先跑 llama_download.sh" >&2
  exit 1
fi

if curl -fsS -m 3 "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1 \
  || curl -fsS -m 3 "http://127.0.0.1:${PORT}/v1/models" >/dev/null 2>&1; then
  echo "llama-server already healthy on :$PORT"
  exit 0
fi

if [ -f "$PID_FILE" ]; then
  old=$(cat "$PID_FILE" || true)
  if [ -n "${old:-}" ] && kill -0 "$old" 2>/dev/null; then
    echo "pid $old running, waiting health"
  else
    rm -f "$PID_FILE"
  fi
fi

echo "===== $(date -Iseconds) START llama-server port=$PORT model=$MODEL =====" >>"$LOG"
nohup "$BIN" \
  -m "$MODEL" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --alias "$ALIAS" \
  -ngl 99 \
  -c "${LLM_CTX:-8192}" \
  --jinja \
  >>"$LOG" 2>&1 &
echo $! >"$PID_FILE"
echo "pid=$(cat "$PID_FILE") log=$LOG"

for i in $(seq 1 90); do
  if curl -fsS -m 3 "http://127.0.0.1:${PORT}/v1/models" >/dev/null 2>&1; then
    echo "healthy after ${i}s"
    curl -sS -m 5 "http://127.0.0.1:${PORT}/v1/models"
    echo
    exit 0
  fi
  sleep 2
done

echo "ERROR: llama-server 未在 180s 内就绪，见 $LOG" >&2
tail -50 "$LOG" >&2
exit 1
