#!/usr/bin/env bash
# 下载 MiniMax H3 到 ComfyUI models/（数据盘）。wget 断点续传，避免 hf cache 双倍占盘。
set -euo pipefail

LOG_DIR=/root/autodl-tmp/logs
MODELS=/root/autodl-tmp/ComfyUI/models
LOG="$LOG_DIR/h3-download.log"
MIRROR="${HF_ENDPOINT:-https://www.modelscope.cn/models/Comfy-Org/MiniMax-H3/resolve/master}"
FALLBACK="${HF_FALLBACK:-https://hf-mirror.com/Comfy-Org/MiniMax-H3/resolve/main}"

mkdir -p "$LOG_DIR" \
  "$MODELS/diffusion_models" \
  "$MODELS/text_encoders" \
  "$MODELS/vae" \
  "$MODELS/loras"
exec > >(tee -a "$LOG") 2>&1
echo "===== $(date -Iseconds) START MiniMax H3 download ====="
df -h /root/autodl-tmp

download_one() {
  local rel=$1
  local min_bytes=$2
  local dest="$MODELS/$rel"
  local url="$MIRROR/$rel"
  mkdir -p "$(dirname "$dest")"
  if [ -f "$dest" ]; then
    local have
    have=$(stat -c%s "$dest")
    if [ "$have" -ge "$min_bytes" ]; then
      echo "SKIP $rel bytes=$have"
      return 0
    fi
    echo "RESUME $rel have=$have need>=$min_bytes"
  fi
  echo "GET $url"
  if ! wget -c --tries=20 --timeout=60 --read-timeout=120 \
    -O "$dest" "$url"; then
    echo "WARN wget failed, try hf-mirror"
    wget -c --tries=10 --timeout=60 --read-timeout=120 \
      -O "$dest" "$FALLBACK/$rel"
  fi
  local got
  got=$(stat -c%s "$dest")
  echo "GOT $rel bytes=$got"
  if [ "$got" -lt "$min_bytes" ]; then
    echo "ERROR $rel too small ($got < $min_bytes)" >&2
    return 1
  fi
}

# 官方体积（字节），校验用 99%
download_one diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors 20760675820
download_one text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors 15530271125
download_one vae/minimax_h3_video_vae_fp16.safetensors 5155730411
download_one vae/minimax_h3_audio_vae_fp32.safetensors 599202260
download_one loras/minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors 1936631062
download_one diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors 20760675820
download_one loras/minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors 1936631070

echo "===== files ====="
find "$MODELS" -name '*.safetensors' -printf '%s\t%p\n' | sort
df -h /root/autodl-tmp
echo "===== $(date -Iseconds) DONE MiniMax H3 download ====="
