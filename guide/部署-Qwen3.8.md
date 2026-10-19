# Qwen3.8-27B 部署方案

在一台 GPU 服务器上用 llama.cpp 的 `llama-server` 提供 OpenAI 兼容文本接口。权重是带 MTP 的 `Qwen3.8-27B-Uncensored-Q4_K_M`，别名 `qwen3.8-27b`，监听 `0.0.0.0:8088`。本文自洽，不依赖 ComfyUI。

已验证组合：RTX 5090 32GB、CUDA 13.x、`CMAKE_CUDA_ARCHITECTURES=120`。脚本在本仓 `scripts/llama_{install,download,start,stop,verify}.sh`，路径写死为 `/root/autodl-tmp`。换机器时保持这个数据盘布局，或改脚本顶部目录后再跑。

## 1. 机器

| 项 | 要求 | 已验证 |
|----|------|--------|
| GPU | 能放下 Q4_K_M，约占 16.7GB 显存 | RTX 5090 32GB |
| 磁盘 | 权重大约 16.8GB，加上源码与编译建议 ≥30GB 空闲 | `/root/autodl-tmp` |
| 工具链 | CUDA toolkit、`cmake ≥ 3.28`、gcc、git | `/usr/local/cuda`，cmake 不够时脚本用 pip 装 |
| 架构 | 编译期写死，换卡必须重编 | 5090 = `120` |

| 卡 | `CMAKE_CUDA_ARCHITECTURES` |
|----|----------------------------|
| RTX 5090 | `120`（脚本默认） |
| RTX 4090 | `89` |
| RTX 3090 | `86` |

同一张 32GB 卡上，这个模型不能和已加载的 MiniMax H3 同时驻留。开文本服务前先停 ComfyUI。

权重必须用 **带 MTP** 的 `Qwen3.8-27B-Uncensored-Q4_K_M.gguf`，不要下文件名里带 `noMTP` 的那份。

## 2. 目录

```text
/root/autodl-tmp/
  llama.cpp/                         # ggml-org/llama.cpp
    build/bin/llama-server
  models/Qwen3.8-27B-Uncensored-Q4_K_M.gguf
  src/scripts/                       # 本仓 scripts/ 拷到这里
  logs/llama.log
  logs/llama.pid
```

## 3. 取源码并编译

`llama_install.sh` **不会** clone。先自己拉源码，再编译。UI 从源码编（`LLAMA_USE_PREBUILT_UI=OFF`），避免去 Hugging Face 拉预编译前端失败。

```bash
cd /root/autodl-tmp
git clone --depth 1 https://github.com/ggml-org/llama.cpp.git

export PATH=/usr/local/cuda/bin:$PATH
export CUDA_HOME=/usr/local/cuda
export CMAKE_CUDA_ARCHITECTURES=120    # 4090 改为 89，3090 改为 86
bash /root/autodl-tmp/src/scripts/llama_install.sh
```

脚本在二进制不存在时执行：

```bash
cmake -S /root/autodl-tmp/llama.cpp -B /root/autodl-tmp/llama.cpp/build \
  -DGGML_CUDA=ON \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CUDA_ARCHITECTURES="${CMAKE_CUDA_ARCHITECTURES:-120}" \
  -DLLAMA_BUILD_UI=ON \
  -DLLAMA_USE_PREBUILT_UI=OFF
cmake --build /root/autodl-tmp/llama.cpp/build --config Release -j"$(nproc)" --target llama-server
```

cmake 版本低于 3.28 时，脚本执行 `pip install 'cmake>=3.28'` 再用新 cmake。成功后打印 `llama-server --version`。

## 4. 权重

| 项 | 值 |
|----|----|
| 仓库 | `JonathanColetti/Qwen3.8-27B-Uncensored-GGUF` |
| 文件 | `Qwen3.8-27B-Uncensored-Q4_K_M.gguf` |
| 落盘 | `/root/autodl-tmp/models/Qwen3.8-27B-Uncensored-Q4_K_M.gguf` |
| 校验下限 | 16000000000 字节（约 16.8GB） |
| 地址 | `https://hf-mirror.com/JonathanColetti/Qwen3.8-27B-Uncensored-GGUF/resolve/main/Qwen3.8-27B-Uncensored-Q4_K_M.gguf` |

```bash
bash /root/autodl-tmp/src/scripts/llama_download.sh
```

`wget -c` 断点续传。已有文件达到下限则跳过。换路径用 `LLM_MODEL_PATH`。

## 5. 启动与停止

```bash
bash /root/autodl-tmp/src/scripts/llama_start.sh
bash /root/autodl-tmp/src/scripts/llama_verify.sh
bash /root/autodl-tmp/src/scripts/llama_stop.sh
```

启动参数：

```bash
/root/autodl-tmp/llama.cpp/build/bin/llama-server \
  -m /root/autodl-tmp/models/Qwen3.8-27B-Uncensored-Q4_K_M.gguf \
  --host 0.0.0.0 \
  --port 8088 \
  --alias qwen3.8-27b \
  -ngl 99 \
  -c 4096 \
  --jinja
```

| 变量 | 默认 | 含义 |
|------|------|------|
| `LLM_MODEL_PATH` | 上面的 gguf | 权重路径 |
| `LLM_PORT` | `8088` | 监听端口 |
| `LLM_ALIAS` | `qwen3.8-27b` | `/v1/models` 里的 id，调用时 `model` 填这个 |
| `LLM_CTX` | `4096` | 上下文长度 |

`-ngl 99` 把层尽量放上 GPU。`--jinja` 启用模型自带的对话模板。脚本最多等 180 秒，直到 `GET /v1/models` 成功。`/health` 或 `/v1/models` 已通则直接退出。停止时先杀 pid 文件里的进程，再用 `fuser -k 8088/tcp` 收口。

## 6. 调用

OpenAI 兼容，本机地址 `http://127.0.0.1:8088`。不要把公网 IP 写进业务。对外时用 SSH `-L 8088:127.0.0.1:8088` 或内网反代。

```bash
curl -sS http://127.0.0.1:8088/v1/models

curl -sS http://127.0.0.1:8088/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3.8-27b","messages":[{"role":"user","content":"只回复：pong"}],"max_tokens":32,"temperature":0,"chat_template_kwargs":{"enable_thinking":false}}'
```

`enable_thinking: false` 关掉思考段，否则短回复里 `content` 可能是空的、正文在 `reasoning_content`。业务侧环境变量：

```text
LLM_BASE_URL=http://127.0.0.1:8088
LLM_API_KEY=sk-local
LLM_MODEL=qwen3.8-27b
```

`LLM_API_KEY` 本地服务不校验，占位即可。

## 7. 验收

`llama_verify.sh` 做两件事：`GET /v1/models` 返回 200 且模型列表非空；上面的 chat 在 60 秒内返回非空 `content`。打印 `PASS` 即通过。

失败时看 `/root/autodl-tmp/logs/llama.log`。

## 8. 换服务器时改什么

| 变了 | 改 |
|------|----|
| 数据盘不是 `/root/autodl-tmp` | 五个 `llama_*.sh` 里的 `ROOT`，以及 clone 目录 |
| GPU 代数变了 | 设 `CMAKE_CUDA_ARCHITECTURES` 后删掉 `llama.cpp/build`，重跑 `llama_install.sh` |
| CUDA 不在 `/usr/local/cuda` | `CUDA_HOME` 和 `PATH` |
| 只想要更长上下文 | `LLM_CTX`，显存随上下文上升 |

## 9. 已知问题

| 现象 | 处理 |
|------|------|
| install 报未找到 llama.cpp | 先 `git clone`，脚本不负责拉源码 |
| 换了 4090/3090 仍用 sm_120 的二进制 | 删 `build/` 后按对应架构重编 |
| 模型列表为空或 chat 无 content | 确认 alias 是 `qwen3.8-27b`，请求带 `enable_thinking: false` |
| 下载文件小于 16GB | 再跑 download，`wget -c` 续传；不要换成 noMTP 文件 |
| OOM | 先停同卡上的 ComfyUI / H3 |
| 180 秒未就绪 | 看 `logs/llama.log`，常见是权重路径错误或 GPU 架构不匹配 |
| cmake 太旧 | 脚本会 pip 装 ≥3.28；机器禁止 pip 时自行装 cmake |
