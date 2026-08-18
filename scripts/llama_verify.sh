#!/usr/bin/env bash
# 验证 AutoDL 实例内 llama.cpp OpenAI 兼容服务
set -euo pipefail

PORT="${LLM_PORT:-8088}"
URL="http://127.0.0.1:${PORT}"
export PATH=/root/miniconda3/bin:${PATH:-/usr/bin:/bin}

echo "===== $(date -Iseconds) verify llama.cpp ====="
code=$(curl -sS -m 8 -o /tmp/llama-models.json -w "%{http_code}" "$URL/v1/models" || true)
echo "http=$code $URL/v1/models"
if [ "$code" != "200" ]; then
  echo "FAIL models" >&2
  tail -30 /root/autodl-tmp/logs/llama.log 2>/dev/null || true
  exit 1
fi
python3 - <<'PY'
import json
d=json.load(open("/tmp/llama-models.json"))
ids=[m.get("id") for m in (d.get("data") or [])]
print("models=", ids)
assert ids, "empty model list"
PY

body='{"model":"qwen3.8-27b","messages":[{"role":"user","content":"只回复：pong"}],"max_tokens":32,"temperature":0,"chat_template_kwargs":{"enable_thinking":false}}'
code=$(curl -sS -m 60 -o /tmp/llama-chat.json -w "%{http_code}" \
  -H 'Content-Type: application/json' -d "$body" "$URL/v1/chat/completions" || true)
echo "chat_http=$code"
python3 - <<'PY'
import json,sys
d=json.load(open("/tmp/llama-chat.json"))
text=((d.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
print("reply=", text[:200].replace("\n"," "))
if not text.strip():
    print(d)
    sys.exit(1)
print("ok")
PY
echo "PASS"
