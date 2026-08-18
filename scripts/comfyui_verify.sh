#!/usr/bin/env bash
# 验证 AutoDL 实例内 ComfyUI 健康状态
set -euo pipefail

PORT="${COMFYUI_PORT:-8188}"
URL="http://127.0.0.1:${PORT}/system_stats"
export PATH=/root/miniconda3/bin:${PATH:-/usr/bin:/bin}

echo "===== $(date -Iseconds) verify comfyui ====="
if [ -f /root/autodl-tmp/logs/comfyui.pid ]; then
  pid=$(cat /root/autodl-tmp/logs/comfyui.pid)
  echo "pid_file=$pid alive=$(kill -0 "$pid" 2>/dev/null && echo yes || echo no)"
fi
ss -ltnp 2>/dev/null | grep ":${PORT}" || echo "WARN: port $PORT not listening"

code=$(curl -sS -m 8 -o /tmp/comfyui-stats.json -w "%{http_code}" "$URL" || true)
echo "http=$code url=$URL"
if [ "$code" != "200" ]; then
  echo "FAIL system_stats" >&2
  tail -30 /root/autodl-tmp/logs/comfyui.log 2>/dev/null || true
  exit 1
fi
python - <<'PY'
import json
d=json.load(open("/tmp/comfyui-stats.json"))
sys=d.get("system") or {}
devs=d.get("devices") or []
print("comfyui_version=", sys.get("comfyui_version"))
print("pytorch=", sys.get("pytorch_version") or sys.get("pytorch"))
if devs:
    d0=devs[0]
    print("device=", d0.get("name"), "vram_total=", d0.get("vram_total"))
print("ok")
PY
echo "PASS"
