---
name: autodl
description: AutoDL 算力 CLI。探活、文生/单图/首尾帧/多图视频、按需开关 GPU（需授权）。供 Codex / OpenClaw / Hermes / Cursor 调用。
version: 0.1.0
metadata:
  cli_command: autodl
  requires_install: true
  agent_safe_commands:
    - config-check
    - compute-health
    - instance-status
    - instance-list
    - wallet-balance
    - tunnel-status
    - job-submit-demo
    - video-submit-demo
    - job-get
    - job-list
    - job-file
    - llm-chat-demo
    - service-list
  human_required_commands:
    - instance-power-on
    - instance-power-off
    - job-submit-live
    - llm-chat-live
    - tunnel-start
---

# autodl

## 前置条件

```bash
cd "/Volumes/Lexar/git/10 baseTools/AutoDL/compute-cli"
pip install -e .
autodl --version
```

密钥在 `.env`，不要打印 Token / SSH 密码。默认 `AUTODL_MOCK=true`。

## Agent 推荐命令

配置检查：

```bash
autodl config check --format json
```

算力探活（离线）：

```bash
autodl --demo compute health --format json
```

接编排（编排需已启动，`AUTODL_MOCK=false`）：

```bash
AUTODL_MOCK=false autodl compute health --format json
AUTODL_MOCK=false autodl job submit --modality image --prompt "一只猫" --format json
```

编排不可达 → exit 2。编排仍可开 `AI_MOCK_MODE=true`，此时不碰 GPU。

提交 Mock 图（agent_safe）：

```bash
autodl job submit --modality image --prompt "一只猫" --demo --format json
```

提交 Mock 视频（agent_safe，Codex / OpenClaw 用同一条命令）：

```bash
autodl job submit --modality video --play text --prompt "海边日落" --demo --format json
autodl job submit --modality video --play first_frame --image ./first.png --prompt "镜头推进" --demo --format json
autodl job submit --modality video --play first_last_frame --image ./first.png --end-image ./last.png --prompt "白天过渡到夜晚" --demo --format json
autodl job submit --modality video --play multi --images "./a.png|./b.png" --prompt "<Picture 1> 走向 <Picture 2>" --demo --format json
```

- `--play`：`text` 文生视频、`first_frame` 单图、`first_last_frame` 首尾帧、`multi` 多图（2–9 张，路径用 `|` 分隔）
- 采样：`--width/--height` 默认 768，生效夹到 256–1344 并对齐 16；`--duration` 大于 0 才换算帧数，对齐 `17k+5` 且不超过 124，省略为 73 帧；`--steps` 1–8，默认 4；`--seed` 省略为随机。完整表见 `platform/guide/架构与契约.md`
- 多图提示词按顺序写 `<Picture 1>` `<Picture 2>`
- 真算力去掉 `--demo`。MCP 只暴露 `autodl_video_submit_demo`，不暴露无 `--demo` 的提交
- 参数：`--modality` 为 `text|image|video`；`--prompt` 必填；`--workflow` 可选，视频留空时按 `--play` 选择
- 退出码：0 成功 / 1 配置错误 / 2 任务不存在或未就绪 / 3 算力失败 / 4 Token 或余额
- 输出字段：`module`, `data_source`, `ok`, `run_id`, `job_id`, `items[0].status`, `items[0].output_uri`

查任务 / 拉产物：

```bash
autodl job get job_xxx --format json
autodl job file job_xxx -o /tmp/out.svg --format json
```

发现对外服务（文本 / 图片 / 视频）：

```bash
autodl --demo service list --format json
autodl --demo service list --exposed --format json
```

- 参数：`--exposed` 只列出已打开的；`--modality` 为 `text|image|video`
- `items[].invoke`：`job submit --modality --workflow`
- 退出码：0 成功 / 2 编排不可达（live）

文本一轮（Mock）：

```bash
autodl llm chat --prompt "只回复：ok" --demo --format json
```

## 长任务说明

`tunnel start` 自己会把 ssh 放到后台并立即返回 JSON，不要再包一层前台 ssh。`job wait`（真视频）禁止阻塞会话。`--demo` 的 `job wait` 立即返回。

真隧道（`AUTODL_MOCK=false`）：

```bash
AUTODL_MOCK=false autodl tunnel status --format json
AUTODL_MOCK=false autodl tunnel start --format json
AUTODL_MOCK=false autodl tunnel stop --format json
```

需 `COMFYUI_SSH_PORT`；密码走 `COMFYUI_SSH_PASSWORD` + sshpass，或 SSH 密钥。断隧道 / 端口未听 → exit 2。

实例与余额（需 `AUTODL_TOKEN`，开机另需 `AUTODL_ALLOW_POWER=true`）：

```bash
AUTODL_MOCK=false autodl wallet balance --format json
AUTODL_MOCK=false autodl instance list --format json
AUTODL_MOCK=false autodl instance status --format json
AUTODL_ALLOW_POWER=true AUTODL_MOCK=false autodl instance power-on --wait --format json
```

`instance status` 若 `shutdown` → exit 2。stdout 不含 SSH 密码；开机后把返回的 `ssh_port` 写入 `COMFYUI_SSH_PORT` 再 `tunnel start`。

## 禁止 Agent 自动调用

| 命令 | 原因 |
|------|------|
| `instance power-on` / `power-off` | 计费；需 `AUTODL_ALLOW_POWER=true` |
| `job submit` 无 `--demo` | 真 GPU |
| 改 SSH 密码 / 释放实例 | 破坏性 |

## MCP（可选）

```bash
autodl-mcp
```

仅 A 级 Tool：`autodl_config_check`、`autodl_job_submit_demo`、`autodl_tunnel_status` 等。禁止通过 MCP 调开机/关机/真提交/打隧道。

## 输出解析

- stdout = JSON 信封
- stderr = JSON 日志（含 `run_id` / `job_id`）
