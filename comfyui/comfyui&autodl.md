# AutoDL 对接 ComfyUI 完整方案

> 从 cyberspaceAI 提炼。主文档：`docs/CyberSpace-AI_ComfyUI集成方案_20260525.md`  
> 实现：`lib/ai/clients/comfyui.ts`、`lib/ai/clients/comfyui-cli.ts`、`lib/ai/providers/provider-router.ts`  
> SSH 登录：见 `guide/服务器&ssh.md`（开机后端口可能变化，勿写死进业务代码）

---

## 一、结论

AutoDL 上的 ComfyUI **只监听实例内网 `:8188`**，本机不能直连公网 IP。

对接方式是 **SSH 本地端口转发**：把远端 `127.0.0.1:8188` 映射到本机同端口。业务侧（cyberspaceAI / 本仓脚本）始终访问：

```text
http://127.0.0.1:8188
```

关机、断隧道、健康检查失败时，由 Provider Router 降级到本地 ComfyUI 或商业 API，不要把 AutoDL 动态 IP 写进代码。

### 当前实例（2026-08-18 已装好并拉起）

| 项 | 值 |
|----|----|
| GPU | RTX 5090 32GB（compute 12.0） |
| 驱动 / CUDA | 595.71 / 13.2（PyTorch 轮子为 cu128） |
| Python / torch | 3.12.3 / `2.8.0+cu128`，`torchaudio==2.8.0+cu128` |
| 安装目录 | `/root/autodl-tmp/ComfyUI`（数据盘，ComfyUI `0.33.0`） |
| 服务 | `0.0.0.0:8188`，`GET /system_stats` 已通 |
| 日志 / PID | `/root/autodl-tmp/logs/comfyui.log`、`comfyui.pid` |
| 脚本 | `/root/autodl-tmp/src/scripts/comfyui_{install,start,stop,verify}.sh` |
| 模型 | MiniMax H3 已落盘（fl2va+ref2va pruned int8 + VAE + Turbo LoRA），约 63GB |

实例内：

```bash
bash /root/autodl-tmp/src/scripts/comfyui_start.sh
bash /root/autodl-tmp/src/scripts/comfyui_verify.sh
bash /root/autodl-tmp/src/scripts/comfyui_stop.sh
```

注意：阿里云 pip 镜像缺 `comfyui-workflow-templates==0.11.43`，安装走官方 PyPI。`requirements.txt` 会把 `torchaudio` 升到 2.11，与 torch 2.8 ABI 不兼容，必须钉回 `2.8.0+cu128`。ComfyUI 会提示 5090 优化算子需要 cu130，当前 cu128 可运行。

---

## 二、目标与分层

| 目标 | 说明 |
|------|------|
| 弹性算力 | AutoDL 云端 GPU → 本地 Mac mini → 商业 API 三级切换 |
| 验证优先 | 先租 AutoDL 跑通图/视频/3D，再考虑自建 |
| 无缝降级 | `/system_stats` 不通即视为关机，自动切备选 |

```text
画布 / Agent / 脚本
        │
        ▼
Provider Router（健康检查 + 优先级）
        │
        ├── Comfyui-CLI :8765     ← 方案 B，推荐
        │         └── ComfyUI :8188
        ├── AutoDL 直连 :8188     ← SSH 隧道后的本机地址
        ├── Local ComfyUI :8188
        └── 商业 API（即梦 / Kling 等）
```

切换逻辑：AutoDL 开机且隧道通 → 优先用；关机或隧道断 → Local；再失败 → 商业 API。

---

## 三、网络拓扑

```text
本机应用 / cyberspaceAI
        │  http://127.0.0.1:8188
        ▼
SSH 隧道  ssh -L 8188:127.0.0.1:8188 -p <端口> root@<host>
        │
        ▼
AutoDL GPU 实例
  ComfyUI  --listen 0.0.0.0 --port 8188
  模型在数据盘（关机不丢）
```

关键约束：

- AutoDL 控制台给出的 SSH 是 `ssh -p <动态端口> root@connect.*.seetacloud.com`，**每次开机端口可能变**。
- ComfyUI 默认不对外暴露 8188；即使 `--listen 0.0.0.0`，也走隧道，不走公网直连。
- 隧道会话必须常驻；断了之后本机 `127.0.0.1:8188` 立即失效。

---

## 四、AutoDL 实例

### 4.1 规格

| 项 | 推荐 | 理由 |
|----|------|------|
| 镜像 | 当前为 conda base + 自装 ComfyUI | Python 3.12 + torch cu128 |
| 显卡 | 当前 RTX 5090 32GB | 5090 需 torch≥2.8 + cu128 |
| 数据盘 | `/root/autodl-tmp` 约 50GB | 代码与模型都放这里 |
| 登录 | `guide/服务器&ssh.md` | 密码与端口以控制台为准 |

成本量级（文档估算，以控制台报价为准）：

| 场景 | 日均 | 说明 |
|------|------|------|
| 验证 2–3h/天 | 约 ¥15–25 | RTX 4090 |
| 轻量 4–6h/天 | 约 ¥30–50 | 用完即关 |
| 批量 8h+/天 | 更高 | 可考虑 A100 |

### 4.2 实例内启动 ComfyUI

```bash
export PATH=/root/miniconda3/bin:$PATH
cd /root/autodl-tmp/ComfyUI
python main.py --listen 0.0.0.0 --port 8188
```

推荐用脚本：

```bash
bash /root/autodl-tmp/src/scripts/comfyui_start.sh
```

实例内自检：

```bash
curl -sS http://127.0.0.1:8188/system_stats
```

应返回 JSON，含 `system.comfyui_version`、内存 / GPU 信息。失败则先查进程与日志，不要打隧道。

### 4.3 模型放到数据盘

模型一律放 AutoDL **数据盘**（本机是 `/root/autodl-tmp/ComfyUI/models/`），不要放系统盘。数据盘已扩容至 **100GB**（约 86GB 可用），本实例按 5090 最小集 + `ref2va` pruned int8 下载（约 63GB）。

工作流来源：`source/comfyui/zealman-AutoDL镜像工作流/V9镜像内工作流/U视频-MINIMAX-H3/`，说明见同仓 `工作流说明/U视频-MINIMAX-H3.md`。官方权重仓：[Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3)。

#### 4.3.1 MiniMax H3（本实例优先）

ComfyUI 目录约定：

| 文件放到 | 用途 |
|----------|------|
| `models/diffusion_models/` | fl2va（文生/图生/首尾帧）、ref2va（多参考） |
| `models/text_encoders/` | Qwen3-VL MiniMax H3 文本视觉编码器 |
| `models/vae/` | 视频 VAE + 音频 VAE |
| `models/loras/` 或 `models/loras/minimax/` | LightX2V / Turbo 加速 LoRA |
| `models/vae_approx/` | TAEH3 预览解码（可选） |

**本机 RTX 5090 32GB 推荐最小集（约 42GB，对应 U03 文生 / U02 图生）**

| 角色 | 文件 | 约大小 | HuggingFace |
|------|------|--------|-------------|
| DiT 文/图/首尾帧 | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | 19.5 GiB | `…/diffusion_models/` |
| 文本编码器 | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | 14.6 GiB | `…/text_encoders/` |
| 视频 VAE | `minimax_h3_video_vae_fp16.safetensors` | 4.9 GiB | `…/vae/` |
| 音频 VAE | `minimax_h3_audio_vae_fp32.safetensors` | 0.6 GiB | `…/vae/` |
| 加速 LoRA | `minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors` | 1.8 GiB | `…/loras/` |

多参考（U01/U04/U06/U07/U09）再加 **二选一**（不要和 bf16 全量同时下）：

| 档 | 文件 | 约大小 |
|----|------|--------|
| 推荐 5090 | `minimax_h3_ref2va_pruned_int8_convrot.safetensors` | 19.5 GiB |
| 更高一致性 | `minimax_h3_ref2va_int8_convrot.safetensors` | 31.7 GiB |

`fl2va` 与 `ref2va` 各一份 pruned int8 ≈ 39 GiB，加上编码器/VAE/LoRA 约 63GB。本盘 100GB 够这一套，仍不要下 bf16 满血。

**官方仓其余档位（按需，勿一次全下）**

| 文件 | 约大小 | 何时用 |
|------|--------|--------|
| `minimax_h3_fl2va_bf16.safetensors` / `ref2va_bf16` | 各 61.7 GiB | 满血，显存/磁盘都不够本实例 |
| `minimax_h3_fl2va_int8_convrot.safetensors` / `ref2va_int8_convrot` | 各 31.7 GiB | 未剪枝 int8，质量略好、更吃盘 |
| `minimax_h3_*_pruned_fp8_scaled.safetensors` | 各 19.5 GiB | 与 pruned int8 同级体积，按节点精度选 |
| `minimax_h3_*_pruned_bf16.safetensors` | 各 37.5 GiB | 剪枝但仍是 bf16 |
| `qwen3vl_32b_minimax_h3_int8_convrot.safetensors` | 25.3 GiB | 编码器更高精度 |
| `qwen3vl_32b_minimax_h3_bf16.safetensors` | 48.0 GiB | 满血编码器 |
| `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors` | 1.8 GiB | 8 步加速 |
| `minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors` | 1.8 GiB | 多参考 4 步加速 |

下载示例（实例内，镜像站可设 `HF_ENDPOINT=https://hf-mirror.com`）：

```bash
export PATH=/root/miniconda3/bin:$PATH
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
BASE=/root/autodl-tmp/ComfyUI/models
mkdir -p "$BASE"/{diffusion_models,text_encoders,vae,loras}
hf download Comfy-Org/MiniMax-H3 \
  diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors \
  text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors \
  vae/minimax_h3_video_vae_fp16.safetensors \
  vae/minimax_h3_audio_vae_fp32.safetensors \
  loras/minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors \
  --local-dir "$BASE"
```

ComfyUI 认的是 `models/<子目录>/文件名`。若 `hf download` 把仓目录结构原样放下，确认 `diffusion_models/` 等已在 `models/` 下，不要多套一层 `MiniMax-H3/`。

**zealman 工作流额外 LoRA 名（镜像内可能已预置，官方仓不一定同名）**

| 工作流常见文件名 | 出现位置 |
|------------------|----------|
| `minimax/minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy_resized_avg_rank_21_bf16.safetensors` | U01–U06 LightX2V |
| `minimax/minimax_h3_turbo_4步加速_comfyui.safetensors` | U07 |
| `minimax/minimax_h3_turbo_v4_step600.safetensors` | U09 |
| `minimax_h3_turbo_4step_ema_ckpt850_pruned_comfyui.safetensors` | U12，仓 `drbaph/MiniMax-H3-Turbo-Lora-ComfyUI` |
| `taeh3.safetensors` | U06/U10 预览，仓 `Kijai/MiniMax-H3-TAE` |

缺官方同名 LoRA 时，可用上表 `loras/minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors` 在工作流里改选。

**工作流怎么配模型**

| 能力 | 典型工作流 | DiT |
|------|------------|-----|
| 文生视频 | U03 | fl2va |
| 图生 / 首尾帧 | U02、U08 | fl2va |
| 多图参考 | U01、U04、U06 | ref2va |
| 全能切换 | U07、U10、U12 | fl2va + ref2va |
| 二采提清 | U09 | ref2va + Turbo |
| 成片后再超分 | U05、U12（可选） | H3 + LTX 2.3 超分（另占盘，本盘先不要下） |

U08 还可选 Qwen3.5 9B GGUF 反推写词，与 H3 主权重无关，低配可关。

#### 4.3.2 其它（cyberspaceAI 原方案，本实例暂缓）

| 用途 | 模型 | 约大小 |
|------|------|--------|
| 图 | Flux 1 Dev / Schnell | ~23GB |
| 视频（旧） | Wan 2.1 FP8 | ~9GB |
| 3D | Hunyuan3D 2.0 | ~4GB+ |

cyberspaceAI 侧 JSON 模板仍在：`lib/ai/clients/comfyui-workflow-*.json`。与 MiniMax H3 不要抢同一块 50GB 盘。

---

## 五、本机 SSH 隧道

登录原文见 `guide/服务器&ssh.md`。隧道命令形态：

```bash
ssh -L 8188:127.0.0.1:8188 -p <SSH端口> root@connect.westc.seetacloud.com
```

保持该会话不断。本机再测：

```bash
curl -sS http://127.0.0.1:8188/system_stats
```

可选保活（本机终端）：

```bash
ssh -N -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes \
  -L 8188:127.0.0.1:8188 -p <SSH端口> root@connect.westc.seetacloud.com
```

`-N` 只转发不进 shell；`ExitOnForwardFailure` 在 8188 已被占用时直接失败，避免静默连上空端口。

---

## 六、业务侧配置

### 6.1 环境变量（直连，方案 A）

cyberspaceAI 把**隧道后的本机地址**当成 AutoDL endpoint：

```env
# 主入口（工厂默认）
COMFYUI_ENDPOINT=http://127.0.0.1:8188

# Router 优先探测的 AutoDL 地址（隧道映射后仍是本机）
COMFYUI_AUTODL_ENDPOINT=http://127.0.0.1:8188

# 本机自建 ComfyUI（可与上面相同，或改成另一端口）
COMFYUI_LOCAL_ENDPOINT=http://127.0.0.1:8188

COMFYUI_POLL_INTERVAL_MS=3000
COMFYUI_TIMEOUT_MS=1800000

# 可选：默认 checkpoint
COMFYUI_CKPT_NAME=flux1-dev.safetensors
COMFYUI_IMAGE_MODEL=flux1-dev.safetensors
COMFYUI_VIDEO_MODEL=wan2.1_fp8_e4m3fn.safetensors
```

文档中有、代码未强制读取的 SSH 字段（留给隧道脚本，不要进客户端）：

```env
COMFYUI_SSH_HOST=connect.westc.seetacloud.com
COMFYUI_SSH_PORT=12345
COMFYUI_SSH_PASSWORD=
```

密码、端口只放 `guide/服务器&ssh.md` 或本机 `.env`，不要提交仓库。

### 6.2 Comfyui-CLI 中间层（方案 B，推荐）

```text
画布/Agent → /api/ai/* → ComfyUICliClient → Comfyui-CLI :8765 → ComfyUI :8188
                                    ↘（降级）ComfyUIClient 直连 :8188
```

```env
COMFYUI_CLI_ENDPOINT=http://127.0.0.1:8765
COMFYUI_ENDPOINT=http://127.0.0.1:8188
COMFYUI_CLI_DEFAULT_PROFILE=fast
COMFYUI_CLI_DEFAULT_WORKFLOW_T2I=wan2.1_txt2img
COMFYUI_CLI_DEFAULT_WORKFLOW_T2V=wan2.1_txt2vid
COMFYUI_CLI_DEFAULT_WORKFLOW_I2V=wan2.1_img2vid
```

CLI 健康：`GET {CLI}/api/health`，`healthy === true` 才选用。

cyberspaceAI BFF：

| 端点 | 说明 |
|------|------|
| `GET /api/ai/comfyui-cli/health` | 代理 CLI 健康检查 |
| `GET /api/ai/comfyui-cli/workflows` | 代理 workflow 列表 |

系统设置里 `comfyuiMode` 可为 `autodl` / `local` / `commercial`；`comfyuiIntegrationMode` 可为 `cli` / `direct` / `commercial`。

---

## 七、调用协议（直连 ComfyUI）

实现类：`ComfyUIClient`。超时默认：图 5 分钟，视频/3D 15 分钟（环境变量可提到 30 分钟）。

### 7.1 核心 API

| 方法 | 端点 | 用途 |
|------|------|------|
| GET | `/system_stats` | 健康 / GPU；Router 3–5s 超时 |
| POST | `/prompt` | 提交 workflow，返回 `prompt_id` |
| GET | `/history/{prompt_id}` | 轮询结果 |
| GET | `/view?filename=&type=&subfolder=` | 下载输出 |
| POST | `/upload/image` | 参考图（URL 或 data URL 先上传） |
| POST | `/interrupt` | 中断 |
| WS | `/ws` | 实时进度（文档规划，轮询已落地） |

### 7.2 任务链路

1. 加载 workflow JSON，按节点映射注入 prompt / 负向 / 宽高 / seed / ckpt。
2. 若 `LoadImage` 的值为 `http(s)://` 或 `data:`，先 `POST /upload/image`，再改成返回的文件名。
3. `POST /prompt`，body：`{ prompt: workflow, client_id }`。
4. 轮询 `GET /history/{prompt_id}`：有 `outputs` 则成功；`status_str === error` 或 `execution_error` 则失败。
5. 从 outputs 取 `images` / `videos` / `gifs`，拼 `/view` URL 返回给上层。

### 7.3 健康探测（Router）

`checkEndpointHealth(endpoint)`：

1. `GET {endpoint}/system_stats`，5s 超时
2. 失败再试 `GET {endpoint}/`
3. 结果缓存 30 秒

不通 = AutoDL 关机或隧道断，进入下一候选。

---

## 八、Provider 路由

文件：`lib/ai/providers/provider-router.ts`（`comfyui-router.ts` 再导出）。

优先级（数字越小越先）：

**图片**

1. Comfyui-CLI（`COMFYUI_CLI_ENDPOINT`）
2. AutoDL 直连（`COMFYUI_AUTODL_ENDPOINT` 或 `COMFYUI_ENDPOINT`）
3. Local（`COMFYUI_LOCAL_ENDPOINT`）
4. 商业 API（如 Gemini Banana）
5. Mock（`AI_MOCK_MODE=true` 或测试环境）

**视频**

1. Comfyui-CLI
2. AutoDL 直连
3. 商业 API（即梦视频）
4. Local
5. Mock

**其它（含 3D）**

1. 开源模型服务 / AutoDL endpoint
2. Comfyui-CLI
3. Local
4. Mock

手动指定 `manualProvider` 时跳过探测。画布可覆盖为 `autodl` / `local` / `commercial`。

---

## 九、连通验收

### 9.1 清单

- [ ] AutoDL 实例已开机，镜像为 ComfyUI
- [ ] 实例内 `curl 127.0.0.1:8188/system_stats` 成功
- [ ] 本机隧道已建立且会话未断
- [ ] 本机 `curl 127.0.0.1:8188/system_stats` 成功
- [ ] 数据盘已有目标 checkpoint
- [ ] cyberspaceAI `.env` 已设 `COMFYUI_AUTODL_ENDPOINT=http://127.0.0.1:8188`
- [ ] 文生图能在约 5 分钟内返回 `/view` URL

### 9.2 验证脚本（cyberspaceAI 仓）

直连：

```bash
cd /Volumes/Lexar/git/03T/cyberspaceAI
COMFYUI_ENDPOINT=http://127.0.0.1:8188 \
  node scripts/diagnostics/verify-comfyui.mjs
```

CLI：

```bash
node scripts/diagnostics/verify-comfyui-cli.mjs
```

脚本会：打 `/system_stats` → 列 checkpoints → 提交最小 t2i workflow → 轮询 `/history` → 打印 `/view` URL。

---

## 十、风险

| 风险 | 处理 |
|------|------|
| AutoDL 关机 / 端口变更 | Router 降级；隧道命令用最新 `guide/服务器&ssh.md` |
| 隧道断开 | 本机 8188 失效；重连并确认 `ExitOnForwardFailure` |
| 本机 8188 已被本地 ComfyUI 占用 | 改隧道本地端口，或停掉本地实例，并同步改 env |
| 模型下载慢 | 提前下到数据盘；用镜像站 `HF_ENDPOINT` |
| 视频超时 | `COMFYUI_TIMEOUT_MS=1800000`；失败再降级商业 API |
| ComfyUI 版本漂移 | 固定 AutoDL 镜像，避免随手升级 |

---

## 十一、与 cyberspaceAI 的对应关系

| 能力 | 位置 |
|------|------|
| 直连客户端 | `lib/ai/clients/comfyui.ts` |
| CLI 客户端 | `lib/ai/clients/comfyui-cli.ts` |
| 工厂 | `lib/ai/clients/factory.ts`（`AIProvider.COMFYUI` / `COMFYUI_CLI`） |
| 路由 | `lib/ai/providers/provider-router.ts` |
| 集成设置 API | `app/api/system-settings/integrations/route.ts` |
| 配置总览 | `app/api/ai/config-overview/route.ts` |
| 方案文档 | `docs/CyberSpace-AI_ComfyUI集成方案_20260525.md` |
| 编排方向 | `docs/neway/新综合方案.md`（视频优先 AutoDL） |

说明：集成方案附录中的 `docs/AutoDL实战手册.md` 在 cyberspaceAI 仓内不存在，以本文 + 上述集成方案为准。

---

## 十二、Vplatform 对接

Vplatform-CLI 当前走 **服务器1 MiniMax H3**（本实例无 Flux / Wan 文生图权重）。

| 项 | 值 |
|----|----|
| 工作流 | `15CLI/Vplatform-CLI/workflows/minimax_h3_txt2vid.json`、`minimax_h3_img2vid.json` |
| 隧道 | `ssh -L 8188:127.0.0.1:8188 -p 30856 root@connect.westc.seetacloud.com` |
| 或脚本 | `bash /Volumes/Lexar/git/15CLI/Vplatform-CLI/scripts/autodl-tunnel.sh start` |

```bash
cd /Volumes/Lexar/git/15CLI/Vplatform-CLI
vplatform video -p "红色跑车缓慢旋转，电影感"
vplatform video -p "镜头推进" -i keyframe.png
```

图：本实例无 t2i，`vplatform image` 不可用。

## 十三、生成测试平台（3190）

交互页 `http://127.0.0.1:3190/` 经编排 `:8090` 提交视频任务。

```bash
cd "/Volumes/Lexar/git/10 baseTools/AutoDL/platform"
# .env: AI_MOCK_MODE=false  AI_MOCK_IMAGE=true
./scripts/start.sh
```

选「视频」→ 生成。工作流 `t2v.u03` = MiniMax H3 Turbo 4 步（默认 768×768 / 73 帧）。首次加载权重可能超过 10 分钟，结果墙会从 queued 变为 succeeded。

