# AutoDL 对接 ComfyUI（从 cyberspaceAI 提炼）

来源：`/Volumes/Lexar/git/03T/cyberspaceAI`  
主文档：`docs/CyberSpace-AI_ComfyUI集成方案_20260525.md`  
实现：`lib/ai/clients/comfyui.ts`、`lib/ai/providers/provider-router.ts`

## 结论

AutoDL 上的 ComfyUI 只监听实例内网 `:8188`。本机不直连公网 IP，而是 **SSH 本地端口转发**，把远端 `127.0.0.1:8188` 映射到本机同端口。业务侧始终访问 `http://127.0.0.1:8188`。

```
本机应用 / cyberspaceAI
        │  http://127.0.0.1:8188
        ▼
SSH 隧道  -L 8188:127.0.0.1:8188
        │
        ▼
AutoDL GPU 实例
  ComfyUI  --listen 0.0.0.0 --port 8188
```

## 1. AutoDL 实例

| 项 | 推荐 |
|----|------|
| 镜像 | `comfyui` / `stable-diffusion`（CUDA 12.1 + Python 3.10） |
| 显卡 | RTX 4090 24GB |
| 数据盘 | ≥ 100GB（模型放数据盘，关机不丢） |

SSH 登录信息见 `guide/ssh.md`（每次开机端口可能变）。

实例内启动：

```bash
cd /root/ComfyUI
python main.py --listen 0.0.0.0 --port 8188
```

实例内自检：

```bash
curl http://127.0.0.1:8188/system_stats
```

## 2. 本机打隧道

```bash
ssh -L 8188:127.0.0.1:8188 -p <SSH端口> root@connect.westc.seetacloud.com
```

保持该会话不断。本机再测：

```bash
curl http://127.0.0.1:8188/system_stats
```

## 3. 业务侧环境变量

cyberspaceAI 把隧道后的本机地址当成 AutoDL endpoint：

```env
COMFYUI_ENDPOINT=http://127.0.0.1:8188
COMFYUI_AUTODL_ENDPOINT=http://127.0.0.1:8188
COMFYUI_LOCAL_ENDPOINT=http://127.0.0.1:8188
COMFYUI_POLL_INTERVAL_MS=3000
COMFYUI_TIMEOUT_MS=1800000
```

可选（文档有、代码未强制使用）：`COMFYUI_SSH_HOST` / `COMFYUI_SSH_PORT` / `COMFYUI_SSH_PASSWORD`。

推荐中间层（方案 B）：本机或远端再起 Comfyui-CLI `:8765`，应用走 CLI，CLI 再打 ComfyUI `:8188`。

```env
COMFYUI_CLI_ENDPOINT=http://127.0.0.1:8765
```

## 4. 调用方式（直连）

健康探测：`GET /system_stats`（3–5s 超时；不通则视为 AutoDL 关机）。

任务链路（`ComfyUIClient`）：

1. 加载 workflow JSON，注入 prompt / 尺寸 / ckpt
2. `POST /prompt` → `prompt_id`
3. 轮询 `GET /history/{prompt_id}`
4. 结果用 `GET /view?filename=...` 取回

| 方法 | 端点 |
|------|------|
| 健康 | `GET /system_stats` |
| 提交 | `POST /prompt` |
| 结果 | `GET /history/{prompt_id}` |
| 下载 | `GET /view` |
| 上传参考图 | `POST /upload/image` |
| 进度 | `WS /ws` |

验证脚本（在 cyberspaceAI 仓）：

```bash
cd /Volumes/Lexar/git/03T/cyberspaceAI
COMFYUI_ENDPOINT=http://127.0.0.1:8188 node scripts/diagnostics/verify-comfyui.mjs
```

## 5. 路由优先级

`lib/ai/providers/provider-router.ts`：

- 图片：Comfyui-CLI → AutoDL 直连（`COMFYUI_AUTODL_ENDPOINT`）→ Local → 商业 API → Mock
- 视频：Comfyui-CLI → AutoDL 直连 → 商业 API → Local → Mock

探测失败（关机、隧道断）自动降级。画布可手动指定 `autodl` / `local` / `commercial`。

## 6. 模型（数据盘）

| 用途 | 模型 |
|------|------|
| 图 | Flux 1 Dev / Schnell |
| 视频 | Wan 2.1 FP8 |
| 3D | Hunyuan3D 2.0 |

workflow 模板在 cyberspaceAI：`lib/ai/clients/comfyui-workflow-*.json`。

## 注意

- AutoDL 关机后隧道失效，Router 应降级，不要把远端 IP 写进业务代码。
- 模型放数据盘，不要放系统盘。
- 视频超时建议 15–30 分钟。
- 文档里的 `docs/AutoDL实战手册.md` 在 cyberspaceAI 仓内不存在，以本页 + 集成方案为准。
