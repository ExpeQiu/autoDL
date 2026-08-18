# ADR-002：AutoDL CLI 接口（供智能体平台调用）

## 状态

| 字段 | 值 |
|------|-----|
| 状态 | Accepted |
| 决策日期 | 2026-08-18 |
| 决策者 | Architect |
| 适用范围 | `AutoDL/compute-cli`；被 OpenClaw / Hermes / Cursor / Skill 中台调用 |

---

## 背景（Context）

- ADR-001 已定测试平台走模板 **1 + 6→1**，并写明「隧道/健康脚本先放 `scripts/`，长大再升 `compute-cli/`」。
- 编排层是 FastAPI `:8090`，Web 是结果墙。其他智能体平台（OpenClaw、Hermes、Cursor、Skill 中台）需要的是 **一条可脚本化命令**，不是 HTTP 客户端。
- GPU 会按需开机；SSH 端口会变；密钥不能进 stdout。命令必须可分级：只读可自动调，开机/关机需授权。

## 选项（Options Considered）

| # | 选项 | 优势 | 劣势 |
|---|------|------|------|
| A | 只暴露 HTTP，让 Agent 自己 curl | 零新代码 | 各平台各写一遍；无 agent_safe；易把密钥打进日志 |
| B | 仓内 `compute-cli/`，命令 `autodl`，对齐 CLI标准 §15 | 人机双友好；SKILL + manifest 可被各平台发现 | 多一层包装 |
| C | 新开 `15CLI/autodl-CLI` 独立仓 | 与采集 CLI 并列 | 与 orchestrator / 隧道强耦合，拆仓成本高 |

## 决策（Decision）

**选 B：仓内 `compute-cli/`，入口命令 `autodl`。** 架构模板 **6**（CLI 工具集），参考仓只读：`/Volumes/Lexar/git/15CLI/po-monitor-CLI`；规范：`/Volumes/Lexar/git/15CLI/CLI标准.md`。

模板 6 必答：

| # | 问题 | 决策 |
|---|------|------|
| 1 | 包名 / 入口 | 包 `autodl_cli`；命令 **`autodl`**（`console_scripts`） |
| 2 | 配置分层 | CLI 参数 > 环境变量 > `~/.autodl/config.yaml` > `compute-cli/.env` > 默认。密钥不进 stdout |
| 3 | 是否依赖兄弟 CLI | **否**。本 CLI 调：① 编排 HTTP；② AutoDL OpenAPI；③ 本机隧道进程 |
| 4 | 主仓位置 | **留在 AutoDL 仓** `compute-cli/`，不迁 15CLI |
| 5 | Mock | 默认 `--demo` / `AUTODL_MOCK=true`；verify 不依赖 GPU 与外网 |

划界：

| 层 | 职责 |
|----|------|
| `autodl` CLI | 智能体唯一入口；JSON stdout；exit code 稳定 |
| `platform/orchestrator` | 任务排队、Mock/ComfyUI/LLM 适配 |
| AutoDL OpenAPI | 实例 list / 开机 / 关机 / 余额 |
| SSH 隧道 | 只映射本机 `8188`/`8088`，业务永不写公网 IP |

不把 CLI 做成常驻 HTTP 服务。MCP 为可选薄适配，只暴露 `agent_safe: true` 命令。

## 理由（Rationale）

- 智能体平台的通用能力是 **Bash / terminal**，不是各写一套 SDK。
- 开机计费、关机断任务、扫码登录必须用 `agent_safe` 四级拦住。
- Mock First 保证离线 verify；真算力走既有隧道 + 编排，不另开协议。

## 后果（Consequences）

### 正面

- cyberspaceAI / Hermes / OpenClaw 用同一套命令提交生成任务或探活。
- 关机、断隧道、余额不足有明确 exit code，Agent 可分支，不必解析中文报错。

### 负面 / 风险

- 实例开机后 SSH 端口可能变化，`power-on --wait` 仍需人工或配置更新端口（P1 用 OpenAPI 拉最新 SSH）。
- Agent 误调 `instance power-on` 会产生费用 → 默认 `write_with_confirm`，需 `AUTODL_ALLOW_POWER=true` 才允许非交互。

---

*最后更新：2026-08-18*
