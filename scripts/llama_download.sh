#!/usr/bin/env bash
# 下载 Qwen3.8-27B-Uncensored Q4_K_M（带 MTP）via hf-mirror
set -euo pipefail

DEST="${LLM_MODEL_PATH:-/root/autodl-tmp/models/Qwen3.8-27B-Uncensored-Q4_K_M.gguf}"
REPO="JonathanColetti/Qwen3.8-27B-Uncensored-GGUF"
FILE="Qwen3.8-27B-Uncensored-Q4_K_M.gguf"
MIN_BYTES=16000000000
URL="https://hf-mirror.com/${REPO}/resolve/main/${FILE}"

mkdir -p "$(dirname "$DEST")"

if [ -f "$DEST" ] && [ "$(stat -c%s "$DEST")" -ge "$MIN_BYTES" ]; then
  echo "already have $DEST"
  ls -lh "$DEST"
  exit 0
fi

echo "wget -c $URL"
echo "dest=$DEST"
wget -c --tries=20 --timeout=60 --read-timeout=120 -O "$DEST" "$URL"

size=$(stat -c%s "$DEST")
if [ "$size" -lt "$MIN_BYTES" ]; then
  echo "FAIL size=$size < $MIN_BYTES" >&2
  exit 1
fi
ls -lh "$DEST"
echo "PASS"
