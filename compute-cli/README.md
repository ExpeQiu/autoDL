# autodl CLI

选模板 **6**。智能体入口命令 `autodl`。契约见仓根 `guide/CLI接口.md`。

```bash
cp .env.example .env
pip install -e ".[dev]"
autodl --version
autodl job submit --modality image --prompt "一只猫" --demo --format json
./scripts/verify.sh
```

默认 Mock。`AUTODL_MOCK=false` 时：任务打编排 `:8090`，实例/余额打 AutoDL OpenAPI，`tunnel start` 转发本机 `8188/8088`。

## Agent 接入

见 `SKILL.md` 与 `agent/manifest.json`。Hermes：`hermes skills install` 本目录。

SkillForge / MCP stdio（只暴露 `agent_safe: true`）：

```bash
pip install -e .
autodl-mcp
# 或 python agent/mcp_server.py
```

Tool 名形如 `autodl_job_submit_demo`。不暴露 `instance-power-on/off`、`job-submit-live`、`tunnel-start`。
