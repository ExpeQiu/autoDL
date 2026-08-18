#!/usr/bin/env bash
# 在 AutoDL 实例内安装 ComfyUI（数据盘，不覆盖已有 torch cu128）
set -euo pipefail

LOG_DIR=/root/autodl-tmp/logs
INSTALL_DIR=/root/autodl-tmp/ComfyUI
REPO_URL="${COMFYUI_REPO_URL:-https://github.com/comfyanonymous/ComfyUI.git}"
LOG="$LOG_DIR/comfyui-install.log"

mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG") 2>&1
echo "===== $(date -Iseconds) START comfyui install ====="

export PATH=/root/miniconda3/bin:${PATH:-/usr/bin:/bin}
if [ -f /root/miniconda3/etc/profile.d/conda.sh ]; then
  # shellcheck source=/dev/null
  source /root/miniconda3/etc/profile.d/conda.sh
  conda activate base
fi

echo "python=$(command -v python) $(python -V 2>&1)"
python - <<'PY'
import torch
print(f"torch={torch.__version__} cuda={torch.cuda.is_available()} cuda_ver={torch.version.cuda}")
if torch.cuda.is_available():
    print(f"gpu={torch.cuda.get_device_name(0)} cap={torch.cuda.get_device_capability(0)}")
PY

if [ ! -f "$INSTALL_DIR/main.py" ]; then
  echo "===== git clone ====="
  if [ -d "$INSTALL_DIR/.git" ]; then
    git -C "$INSTALL_DIR" pull --ff-only || true
  else
    rm -rf "$INSTALL_DIR"
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
  fi
else
  echo "ComfyUI already present: $INSTALL_DIR"
  git -C "$INSTALL_DIR" rev-parse --short HEAD || true
fi

cd "$INSTALL_DIR"
echo "===== pip requirements (keep existing torch) ====="
# AutoDL 默认阿里云镜像缺部分 comfyui-* 精确版本，优先官方 PyPI
export PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.org/simple}"
export PIP_EXTRA_INDEX_URL="${PIP_EXTRA_INDEX_URL:-https://download.pytorch.org/whl/cu128 http://mirrors.aliyun.com/pypi/simple}"
python -m pip install -U pip wheel setuptools
# 禁止把 cu128 的 torch 换成 CPU / 旧 CUDA 轮子
python -m pip install -r requirements.txt \
  --index-url https://pypi.org/simple \
  --extra-index-url https://download.pytorch.org/whl/cu128

# requirements 可能把 torchaudio 升到与 torch 2.8 不兼容的版本
python -m pip install --force-reinstall --no-deps "torchaudio==2.8.0" \
  --index-url https://download.pytorch.org/whl/cu128

python - <<'PY'
import torch, torchaudio
assert torch.cuda.is_available(), "torch 无 CUDA，安装被降级了"
print("post-install torch", torch.__version__, torch.version.cuda)
print("post-install torchaudio", torchaudio.__version__)
PY

mkdir -p "$INSTALL_DIR/models/checkpoints" "$INSTALL_DIR/input" "$INSTALL_DIR/output"
echo "===== $(date -Iseconds) DONE comfyui install dir=$INSTALL_DIR ====="
ls -ld "$INSTALL_DIR"
python -c "import folder_paths" 2>/dev/null || true
du -sh "$INSTALL_DIR"
