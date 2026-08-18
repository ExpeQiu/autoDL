#!/usr/bin/env bash
# 在 AutoDL 实例内：编译 llama.cpp（CUDA，不拉 HF Web UI）
set -euo pipefail

ROOT=/root/autodl-tmp
SRC="$ROOT/llama.cpp"
BUILD="$SRC/build"
BIN="$BUILD/bin/llama-server"
export PATH=/usr/local/cuda/bin:/root/miniconda3/bin:${PATH:-/usr/bin:/bin}
export CUDA_HOME="${CUDA_HOME:-/usr/local/cuda}"

if [ ! -d "$SRC" ]; then
  echo "ERROR: 未找到 $SRC" >&2
  exit 1
fi

if ! cmake --version | head -1 | grep -Eq '3\.(2[8-9]|[3-9][0-9])|[4-9]\.'; then
  echo "cmake too old, installing via pip"
  pip install -q 'cmake>=3.28'
fi
CMAKE_BIN="$(command -v cmake)"
echo "using $CMAKE_BIN $($CMAKE_BIN --version | head -1)"

if [ ! -x "$BIN" ]; then
  echo "===== cmake llama-server CUDA sm_120 no-prebuilt-ui ====="
  "$CMAKE_BIN" -S "$SRC" -B "$BUILD" \
    -DGGML_CUDA=ON \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CUDA_ARCHITECTURES="${CMAKE_CUDA_ARCHITECTURES:-120}" \
    -DLLAMA_BUILD_UI=ON \
    -DLLAMA_USE_PREBUILT_UI=OFF
  "$CMAKE_BIN" --build "$BUILD" --config Release -j"$(nproc)" --target llama-server
fi

test -x "$BIN"
echo "bin=$BIN"
"$BIN" --version | head -8 || true
