# 生成测试平台

选架构 **模板 1（分层数据流）+ 6→1**。管道对照 `/Volumes/Lexar/git/03T/Uni-SIM`；ComfyUI 协议对照 cyberspaceAI，本仓只做测试台，不做画布。

```bash
cp .env.example .env
# 真视频：AI_MOCK_MODE=false，并先打通 :8188 隧道
./scripts/start.sh
# 打开 http://127.0.0.1:3190/  → 选「视频」生成
./scripts/verify.sh
./scripts/stop.sh
```

前端 `http://127.0.0.1:3190/`，编排 `http://127.0.0.1:8090`。视频工作流 `workflows/minimax_h3_txt2vid.json`（`t2v.u03`）。本卡无文生图，保持 `AI_MOCK_IMAGE=true`。

外置盘上 venv 会落到 `~/.cache/autodl-genlab/venv`（可用 `GENLAB_VENV` 覆盖）。

契约与增量见 `guide/架构与契约.md`，决策见 `ADR/ADR-001-测试平台架构.md`。
