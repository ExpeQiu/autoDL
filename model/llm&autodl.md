# AutoDL 对接 llama.cpp（Qwen3.8-27B）文本服务

> 平台文本任务走 OpenAI 兼容接口。本机只访问隧道后的 `http://127.0.0.1:8088`，不写 AutoDL 公网 IP。

## 权重

| 项 | 值 |
|----|----|
| 仓 | `JonathanColetti/Qwen3.8-27B-Uncensored-GGUF` |
| 档 | `Qwen3.8-27B-Uncensored-Q4_K_M.gguf`（约 16.8GB，**带 MTP**，不是 noMTP） |
| 落盘 | `/root/autodl-tmp/models/Qwen3.8-27B-Uncensored-Q4_K_M.gguf` |
| 下载 | hf-mirror |

```bash
bash /root/autodl-tmp/src/scripts/llama_install.sh
bash /root/autodl-tmp/src/scripts/llama_download.sh
bash /root/autodl-tmp/src/scripts/llama_start.sh
bash /root/autodl-tmp/src/scripts/llama_verify.sh
```

服务：`0.0.0.0:8088`，别名 `qwen3.8-27b`。

## 本机

```bash
AI_MOCK_TEXT=false
LLM_BASE_URL=http://127.0.0.1:8088
LLM_MODEL=qwen3.8-27b

cd "/Volumes/Lexar/git/10 baseTools/AutoDL/platform"
./scripts/tunnel.sh
./scripts/start.sh
```
