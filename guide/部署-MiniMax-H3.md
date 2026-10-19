# MiniMax H3 部署方案

在一台 GPU 服务器上安装 ComfyUI，并加载 MiniMax H3 开源权重，提供文生视频、图生 / 首尾帧、多参考生视频。服务只监听本机 `8188`。本文自洽，不依赖 Qwen 文本服务。

已验证组合：RTX 5090 32GB、驱动 595 / CUDA 13.x、`torch 2.8.0+cu128`、ComfyUI `0.33.0`。脚本在本仓 `scripts/comfyui_{install,download_h3,start,stop,verify}.sh`，路径写死为 `/root/autodl-tmp`。换机器时保持这个数据盘布局，或改脚本顶部目录后再跑。

## 1. 机器

| 项 | 最低 | 已验证 |
|----|------|--------|
| GPU | ≥24GB；pruned int8 建议 32GB | RTX 5090 32GB（compute 12.0） |
| 磁盘 | ≥100GB 数据盘 | `/root/autodl-tmp` 100GB，权重约 63GB |
| Python | 3.12 + 已装好的 CUDA 版 PyTorch | conda `base`，`torch 2.8.0+cu128`，`torchaudio 2.8.0+cu128` |
| 系统 | 官方 PyTorch 镜像，不要在空系统盘硬装 CUDA | AutoDL conda 镜像 |

代码和权重只放数据盘。不要装到 `/root/ComfyUI`（系统盘，关机或重装会丢）。

5090 必须 cu128 及以上。4090 可用 cu124，但不要和本文的 torch 轮子混用。ComfyUI 可能提示 5090 优化算子需要 cu130，cu128 可以运行。

同一张 32GB 卡上，H3 加载后约占满显存，不能再驻留 Qwen Q4_K_M（约 17GB）。要跑文本时先停 ComfyUI。

## 2. 目录

```text
/root/autodl-tmp/
  ComfyUI/                 # 0.33.0，监听 0.0.0.0:8188
    models/diffusion_models/
    models/text_encoders/
    models/vae/
    models/loras/
  src/scripts/             # 本仓 scripts/ 拷到这里
  logs/comfyui.log
  logs/comfyui.pid
  logs/h3-download.log
```

## 3. 安装 ComfyUI

先确认 CUDA 版 torch 还在，再装 ComfyUI。安装脚本不会重装 torch，但会钉回 torchaudio。

```bash
export PATH=/root/miniconda3/bin:$PATH
source /root/miniconda3/etc/profile.d/conda.sh
conda activate base
python - <<'PY'
import torch
print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))
PY
```

5090 应看到 `2.8.x+cu128` 且 `True`。

```bash
bash /root/autodl-tmp/src/scripts/comfyui_install.sh
```

脚本做的事：

1. 若 `/root/autodl-tmp/ComfyUI/main.py` 不存在，则 `git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git`。
2. `pip install -r requirements.txt`，index 用官方 PyPI，extra index 用 `https://download.pytorch.org/whl/cu128`。阿里云镜像缺 `comfyui-workflow-templates` 等精确版本，不要改回阿里云做主源。
3. 强制重装 `torchaudio==2.8.0`（cu128，`--no-deps`）。`requirements.txt` 会把 torchaudio 升到 2.11，与 torch 2.8 ABI 不兼容。
4. 断言 `torch.cuda.is_available()`，防止被换成 CPU 轮子。

H3 节点在 ComfyUI 0.33 内核里：`MiniMaxH3ImageToVideo`、`MiniMaxH3ReferenceToVideo`。不要安装 `ComfyUI-MiniMaxH3-Cache`。浅克隆拿到的是当时的 main；要复现已验证环境，克隆后切到包含这些节点的 `0.33.0` 或更新的发布。

## 4. 权重

官方仓：[Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3)。只下 pruned int8 这一套，不要下 bf16 满血（单文件约 62GiB）。

| 放到 | 文件 | 用途 | 校验下限（字节） |
|------|------|------|------------------|
| `models/diffusion_models/` | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | 文生 / 图生 / 首尾帧 | 20760675820 |
| `models/diffusion_models/` | `minimax_h3_ref2va_pruned_int8_convrot.safetensors` | 多参考 | 20760675820 |
| `models/text_encoders/` | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | Qwen3-VL-32B 文本视觉编码器 | 15530271125 |
| `models/vae/` | `minimax_h3_video_vae_fp16.safetensors` | 视频 VAE | 5155730411 |
| `models/vae/` | `minimax_h3_audio_vae_fp32.safetensors` | 音频 VAE | 599202260 |
| `models/loras/` | `minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors` | FL2V 四步加速 | 1936631062 |
| `models/loras/` | `minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors` | Ref2V 四步加速 | 1936631070 |

合计约 63GB。`fl2va` 与 `ref2va` 不能互相替代。

```bash
bash /root/autodl-tmp/src/scripts/comfyui_download_h3.sh
```

下载用 `wget -c` 直接落到 `models/`，不走 Hugging Face 缓存，避免双倍占盘。主源 ModelScope，失败再切 hf-mirror：

```text
https://www.modelscope.cn/models/Comfy-Org/MiniMax-H3/resolve/master/<相对路径>
https://hf-mirror.com/Comfy-Org/MiniMax-H3/resolve/main/<相对路径>
```

可用 `HF_ENDPOINT`、`HF_FALLBACK` 覆盖。已有文件达到校验下限则跳过。ComfyUI 认的是 `models/<子目录>/文件名`，不要多套一层 `MiniMax-H3/`。

按需才下、不要和上面同时占盘的档位：未剪枝 int8（各约 32GiB）、pruned bf16（各约 38GiB）、满血 bf16（各约 62GiB）、编码器 int8 / bf16（25GiB / 48GiB）、8 步 LoRA `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors`。

## 5. 启动与停止

```bash
bash /root/autodl-tmp/src/scripts/comfyui_start.sh
bash /root/autodl-tmp/src/scripts/comfyui_verify.sh
bash /root/autodl-tmp/src/scripts/comfyui_stop.sh
```

启动命令等价于：

```bash
cd /root/autodl-tmp/ComfyUI
python main.py --listen 0.0.0.0 --port 8188
```

`COMFYUI_PORT` 可改端口。脚本用 `nohup` 写日志，最多等 120 秒直到 `GET /system_stats` 返回。已健康则直接退出。

## 6. 怎么用权重

| 能力 | 节点 | DiT | LoRA |
|------|------|-----|------|
| 文生视频 | `MiniMaxH3ImageToVideo`，不接图 | fl2va | fl2v turbo 4step |
| 首帧 / 尾帧 / 首尾帧 | 同上，接 `first_frame` / `last_frame` | fl2va | 同上 |
| 多参考（≤9 图，≤3 视频，≤3 音频） | `MiniMaxH3ReferenceToVideo` | ref2va | ref2v turbo 4step |

约束：

- 短边原生 768。16:9 用 **1344×768**。边长对齐 32，长边不超过 1344。
- 帧数对齐 **17k+5**（73 帧约 3 秒，124 帧约 5 秒，24fps）。最低分辨率约 384p。
- 一次前向同时出画面和立体声。Turbo 四步比默认 20 步快，画质和声音略降。
- 参考模式提示词按接入顺序写 `<Picture 1>`、`<Video 1>`、`<Audio 1>`。

调用面：`GET /system_stats`、`POST /prompt`、`GET /history/{id}`、`GET /view`、`POST /upload/image`。视频超时按 30 分钟留（首次加载权重大于 10 分钟）。

## 7. 验收

```bash
curl -sS http://127.0.0.1:8188/system_stats
```

通过标准：HTTP 200，JSON 里有 `system.comfyui_version`，`devices[0]` 能看到 GPU 与显存。`comfyui_verify.sh` 打印 `PASS`。

再确认七个 safetensors 都在对应子目录，且体积不低于第 4 节下限。然后提交一条 768 边长、73 帧、4 步的文生视频，能从 `/history` 拿到视频文件。

## 8. 换服务器时改什么

| 变了 | 改 |
|------|----|
| 数据盘不是 `/root/autodl-tmp` | 四个 `comfyui_*.sh` 里的 `INSTALL_DIR` / `MODELS` / `LOG_DIR` |
| GPU 不是 5090 | torch / CUDA 轮子；24GB 卡可只留 fl2va 一套（约 42GB），先不下 ref2va |
| 没有 conda `/root/miniconda3` | 脚本里的 `PATH` 和 `conda activate base` |
| 要对外提供 | 不要把 8188 直接暴露公网；用 SSH `-L 8188:127.0.0.1:8188` 或内网反代 |

## 9. 已知问题

| 现象 | 处理 |
|------|------|
| torch 变成 CPU 版 | 重跑 install，确认 extra index 是 cu128 |
| torchaudio 导入失败 | 钉 `torchaudio==2.8.0+cu128` |
| 缺 H3 节点 | ComfyUI 低于 0.33；升级内核，不要装 Cache 插件 |
| 下载中断或文件偏小 | 再跑 download 脚本，`wget -c` 会续传；低于下限会失败 |
| 盘满 | 100GB 盘只够这一套 pruned int8；不要再下 LTX 超分或 bf16 |
| OOM | 先停掉同卡上的 llama-server |
| 启动 120 秒未就绪 | 看 `/root/autodl-tmp/logs/comfyui.log` |
