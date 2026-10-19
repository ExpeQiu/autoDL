# CLI 对接：算力机上的编排

命令契约仍是 [CLI接口.md](./CLI接口.md)。本文只说明编排已经在算力机 2 上之后，本机 `autodl` 怎么连上它。

编排进程在 `/root/autodl-tmp/platform`，只听实例内 `127.0.0.1:8090`。CLI 留在调用方机器。`ORCH_BASE` 只写隧道后的本机地址，不写 `seetacloud` 域名，也不写公网 IP。SSH 端口以 [服务器&ssh.md](./服务器&ssh.md) 和控制台为准。

```text
Codex / OpenClaw / 本机
        │  autodl … --format json
        ▼
compute-cli
        │  ORCH_BASE=http://127.0.0.1:8090
        │  ssh -L 8090 → 算力机 127.0.0.1:8090
        ▼
算力机编排 :8090
        │  同机 127.0.0.1:8188
        ▼
ComfyUI（MiniMax H3）
```

`autodl tunnel start` 只转发 `8188`（ComfyUI）和 `8088`（llama），不转发编排。对接编排要单独做 `8090` 转发。

## 1. 安装

```bash
cd "/Volumes/Lexar/git/10 baseTools/AutoDL/compute-cli"
pip install -e .
autodl --version
```

`compute-cli/.env` 至少有：

```text
AUTODL_MOCK=true
ORCH_BASE=http://127.0.0.1:8090
COMFYUI_SSH_HOST=connect.westd.seetacloud.com
COMFYUI_SSH_PORT=
COMFYUI_SSH_USER=root
```

`COMFYUI_SSH_PORT` 开机后填写。密码放 `COMFYUI_SSH_PASSWORD` 或本机 `sshpass`，不要提交，不要出现在 Agent 能读的 stdout。

## 2. 先确认打到哪一台编排

本机 `8090` 若已被 Mac 上的编排占用，转发绑不上去，CLI 会打到 Mac 而不是算力机。

```bash
lsof -nP -iTCP:8090 -sTCP:LISTEN
```

有进程就停掉本机编排（结果墙 `:3190` 可留着），再转发：

```bash
ssh -N -L 8090:127.0.0.1:8090 -p <控制台端口> root@connect.westd.seetacloud.com
```

不想停本机编排时，改绑别的本地端口，并让 CLI 跟过去：

```bash
ssh -N -L 18090:127.0.0.1:8090 -p <控制台端口> root@connect.westd.seetacloud.com
ORCH_BASE=http://127.0.0.1:18090
```

算力机上的编排没在跑时，在本机执行 `platform/scripts/deploy-remote.sh`。它会同步代码并在远端以 `SKIP_WEB=1` 启动。日志在 `platform/logs/deploy-remote.log`。

## 3. 调用

离线（不连算力机，Codex / OpenClaw / MCP 用这条）：

```bash
autodl config check --format json
autodl job submit --modality video --play text --prompt "海边日落" --demo --format json
autodl service list --exposed --demo --format json
```

真任务（转发已经通，且人已授权）：

```bash
AUTODL_MOCK=false autodl compute health --format json
AUTODL_MOCK=false autodl service list --exposed --format json
AUTODL_MOCK=false autodl job submit --modality video --play text --prompt "海边日落" --format json
AUTODL_MOCK=false autodl job get job_xxx --format json
AUTODL_MOCK=false autodl job wait job_xxx --format json
AUTODL_MOCK=false autodl job file job_xxx -o ./out.mp4 --format json
```

| 情况 | exit | Agent 怎么做 |
|------|------|----------------|
| 成功 | 0 | 读 stdout 的 `items` |
| 参数或配置缺 | 1 | 停，看 stderr |
| 关机、8090 没转发、编排没起 | 2 | 停。开机和转发要人做，不要自己循环 `power-on` |
| 任务失败 | 3 | 记下 `job_id` 和 `error` |
| Token 或余额不足 | 4 | 停，通知人 |

视频 `job wait` 最长约 30 分钟，放到后台，不要堵在 Agent 会话里。

当前算力机：视频走 ComfyUI（`AI_MOCK_MODE=false`）。文本、文生图仍是 Mock。图生图会 `422`。

## 4. Codex / OpenClaw

两边都只自动调用 A 级命令。真算力提交、开机、`tunnel start` 不进 MCP。

| 平台 | 接法 |
|------|------|
| Codex / Cursor | MCP stdio：`python -m autodl_cli.mcp_server`，工作目录 `compute-cli/`。只用于 `--demo` |
| OpenClaw | 安装 `compute-cli/` 这套 Skill，用 Bash 调 `autodl … --format json` |
| 真视频 | 人先开好 `8090` 转发，再显式执行不带 `--demo` 的 `job submit` |

Agent 不保存 SSH 密码，不自己登录算力机，不调用 `POST /prompt`。

## 5. 不要这样做

- 把 `ORCH_BASE` 写成算力机公网地址或 SSH 主机名
- 用 `autodl tunnel start` 代替 `8090` 转发
- 本机 `8090` 仍是 Mac 编排时，把 live 任务当成已经打到算力机
- 让 Agent 自动开机或自动打隧道
- 把 ComfyUI `:8188` 登记成对外服务
