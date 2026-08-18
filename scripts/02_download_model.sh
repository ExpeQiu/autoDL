#!/usr/bin/env bash
set -euo pipefail
LOG=/root/autodl-tmp/logs/model-download.log
mkdir -p /root/autodl-tmp/logs /root/autodl-tmp/models
exec > >(tee -a "$LOG") 2>&1
echo "===== $(date -Iseconds) START model download ====="
export PATH=/root/miniconda3/bin:$PATH
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
export HF_HUB_ENABLE_HF_TRANSFER=0
echo "HF_ENDPOINT=$HF_ENDPOINT"
DEST=/root/autodl-tmp/models
FILE=Qwen3.8-27B-Uncensored-Q4_K_M.gguf
OUT="$DEST/$FILE"

/root/miniconda3/bin/pip install -U "huggingface_hub>=0.25" -q
echo "huggingface_hub ready"

if [ -f "$OUT" ]; then
  echo "file exists, size=$(du -h "$OUT" | cut -f1)"
else
  echo "===== hf download ====="
  if ! hf download JonathanColetti/Qwen3.8-27B-Uncensored-GGUF "$FILE" --local-dir "$DEST"; then
    echo "hf download failed, wget mirror"
    URL="$HF_ENDPOINT/JonathanColetti/Qwen3.8-27B-Uncensored-GGUF/resolve/main/$FILE"
    wget -c -O "$OUT" "$URL"
  fi
fi

ls -lh "$OUT"
BYTES=$(stat -c%s "$OUT")
echo "bytes=$BYTES"
if [ "$BYTES" -lt 10000000000 ]; then
  echo "ERROR: file too small" >&2
  exit 1
fi
echo "===== $(date -Iseconds) DONE model download ====="
