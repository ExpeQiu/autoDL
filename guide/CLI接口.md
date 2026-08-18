# AutoDL CLI 接口（智能体调用契约）

选模板 **6**。参考 `/Volumes/Lexar/git/15CLI/po-monitor-CLI`；规范 `/Volumes/Lexar/git/15CLI/CLI标准.md`。决策见 `ADR/ADR-002-CLI接口.md`。

命令名：`autodl`。数据走 stdout（默认 JSON 给 Agent），日志走 stderr。

## 目标 / 非目标

| 做 | 不做 |
|----|------|
| 实例探活 / 按需开关机 / 打隧道 / 提交生成任务 | 再做一套画布或对话 Agent |
| `--format json` + 稳定 exit code，可被 OpenClaw / Hermes / Cursor 直接 exec | 让 Agent 去 curl 编排或抄 SSH 密码 |
| `--demo` 离线闭环 | 24h 挂 GPU；默认自动开机 |

## 命令面

```text
autodl [--format json|table] [-v|-q] <group> <action>
```

```
智能体 / Skill
      │  autodl … --format json
      ▼
compute-cli (autodl)
      ├── instance  → AutoDL OpenAPI  https://api.autodl.com
      ├── tunnel    → ssh -L 8188/8088
      ├── compute   → 本机 :8188 / :8088 健康
      ├── job       → orchestrator :8090
      └── llm       → 本机 :8088 OpenAI 兼容
```

| 命令 | 说明 | agent_safe | 超时 |
|------|------|------------|------|
| `config check` | 配置齐全、密钥脱敏 | A `true` | 10s |
| `instance list` | 实例列表 | A | 30s |
| `instance status [--uuid]` | 开关机与 SSH 端口 | A | 30s |
| `instance power-on --wait` | 有卡开机并等到可 SSH | C `write_with_confirm` | 180s |
| `instance power-off` | 关机（任务会断） | C | 60s |
| `wallet balance` | 余额（分/1000=元） | A | 15s |
| `tunnel start` | 后台 SSH 转发 | B `background_only` | 0 |
| `tunnel stop` | 停转发 | A | 10s |
| `tunnel status` | 本机 8188/8088 是否在听 | A | 10s |
| `compute health` | ComfyUI + llama 探活 | A | 15s |
| `job submit --modality --prompt` | 提交；`--demo` 不碰 GPU | A（仅 `--demo`）；C（真算力） | 60s 提交；视频 wait 见下 |
| `job get <id>` | 查任务 | A | 10s |
| `job list [--modality]` | 列表 | A | 10s |
| `job wait <id>` | 等到终态 | B | 图 180s / 视频 1800s |
| `job file <id> -o PATH` | 拉产物 | A | 60s |
| `llm chat --prompt` | 文本一轮 | A（`--demo`）；C（真模型） | 180s |

禁止 Agent 自动调用：改 SSH 密码、写 Cookie、释放/销毁实例、交互式登录。

## JSON 信封

所有 `--format json` 共用：

```json
{
  "module": "job.submit",
  "version": "0.1.0",
  "data_source": "demo",
  "ok": true,
  "run_id": "run_...",
  "job_id": "job_...",
  "count": 1,
  "items": []
}
```

| 字段 | 必须 | 说明 |
|------|------|------|
| `module` | ✓ | `{group}.{action}` |
| `data_source` | ✓ | `demo` \| `live` \| `cache` |
| `ok` | ✓ | 与 exit 0 对齐 |
| `run_id` / `job_id` | 任务类 | 与编排契约一致 |
| `items` | ✓ | 列表或单元素 |

`job.submit` 的 `items[0]` 对齐编排 Job：`id, run_id, modality, status, provider, output_uri, error`。

`instance.status` 的 `items[0]`：`uuid, name, status, ssh_host, ssh_port, gpu`。`status=shutdown` 时 exit **2**。

## Exit code

| Code | 含义 | Agent 建议 |
|------|------|------------|
| `0` | 成功 | 解析 `items` |
| `1` | 参数 / 配置缺失 | 停，读 stderr |
| `2` | 未就绪（关机、隧道断、无数据） | 可走 `power-on` + `tunnel start`（需授权） |
| `3` | 算力/任务失败 | 记 `job_id` + `error`，勿重开实例死循环 |
| `4` | Token / 余额不足 | 停，通知人 |

## 智能体推荐调用

只读探活：

```bash
autodl config check --format json
autodl compute health --format json
autodl instance status --format json
```

离线生成（verify / CI / 未授权 GPU）：

```bash
autodl job submit --modality image --prompt "一只猫" --demo --format json
```

真算力（需 `AUTODL_ALLOW_POWER=true` 才允许开机；提交真任务需明确授权）：

```bash
autodl instance power-on --wait --format json
autodl tunnel start
autodl compute health --format json
autodl job submit --modality image --prompt "一只猫" --workflow t2i.demo --format json
autodl job wait job_xxx --format json
```

长任务（视频、隧道）禁止前台阻塞 Agent 会话，用 spawn / 后台。

## 配置（`.env.example`）

```
AUTODL_MOCK=true
AUTODL_ALLOW_POWER=false
AUTODL_TOKEN=
AUTODL_INSTANCE_UUID=
ORCH_BASE=http://127.0.0.1:8090
COMFYUI_ENDPOINT=http://127.0.0.1:8188
LLM_BASE_URL=http://127.0.0.1:8088
COMFYUI_SSH_HOST=connect.westc.seetacloud.com
COMFYUI_SSH_PORT=
COMFYUI_SSH_USER=root
```

优先级：CLI 参数 > 环境变量 > `~/.autodl/config.yaml` > 仓库 `.env`。Token / SSH 密码永不打印。

## 接入文件（实现时必交）

```
compute-cli/
├── SKILL.md                 # Agent Skills frontmatter
├── agent/manifest.json      # 命令 Schema + agent_safe
├── agent/mcp_server.py      # MCP stdio 薄入口
├── autodl_cli/cli.py
├── pyproject.toml           # autodl / autodl-mcp
└── scripts/verify.sh
```

平台映射：OpenClaw / Cursor → Bash；Hermes → `hermes skills install compute-cli/`；SkillForge → 仅包装 A 级命令为 MCP Tool `autodl_{command}`。

## 增量 DoD

| 增量 | ≤2 天 | 完成即 |
|------|--------|--------|
| **P0** | 脚手架 + Mock job | `autodl --help/--version`；`job submit --demo` JSON 信封过；`scripts/verify.sh` 离线绿 |
| **P1** | 接编排 | `AUTODL_MOCK=false` 时 `compute health` / `job *` 打到 `:8090`；编排挂了 exit 2；日志带 `run_id` |
| **P2** | 隧道 | `tunnel start` 后台 ssh；`status` 探本机端口，断了 exit 2；密码不进 stdout |
| **P3** | OpenAPI | `AUTODL_MOCK=false` 时 `instance *` / `wallet balance` 打 `api.autodl.com`；无 Token exit 4；开机需 `AUTODL_ALLOW_POWER`；快照不含密码 |
| **P4** | 可选 MCP | `agent/mcp_server.py` / `autodl-mcp` 只暴露 A 级；`instance-power-on/off`、`job-submit-live`、`tunnel-start` 不进 Tool 列表 |

P0 验收：

```bash
cd "/Volumes/Lexar/git/10 baseTools/AutoDL/compute-cli"
./scripts/verify.sh
```

## 观测

stderr JSON 行：`run_id` / `job_id` / `module` / `instance_uuid`。落 `compute-cli/logs/`。

## 反模式

- Agent 同步等待视频或 `tunnel start` 前台
- stdout 混日志；默认自动 `power-on`
- 业务代码写 AutoDL 公网 IP
- 无 `--demo` 导致 verify 依赖 GPU
