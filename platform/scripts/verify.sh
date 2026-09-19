#!/usr/bin/env bash
# 验收：编排健康 + Mock 三模态出结果。失败非 0。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  cp .env.example .env
fi
# shellcheck disable=SC1091
set -a
source .env
set +a

HOST="${ORCH_HOST:-127.0.0.1}"
PORT="${ORCH_PORT:-8090}"
BASE="http://${HOST}:${PORT}"

echo "===== $(date -Iseconds) verify gen-test-platform ====="

for f in README.md .env.example ADR/ADR-001-测试平台架构.md ADR/ADR-003-服务暴露目录.md guide/架构与契约.md suites/demo.json workflows/minimax_h3_txt2vid.json; do
  if [[ ! -f "$ROOT/$f" ]]; then
    echo "FAIL missing $f" >&2
    exit 1
  fi
done

if ! curl -sS -m 3 "$BASE/health" >/dev/null; then
  echo "orchestrator down, starting..."
  bash "$ROOT/scripts/start.sh"
fi

health="$(curl -sS -m 5 "$BASE/health")"
echo "$health" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('ok') is True, d"
echo "PASS /health"

compute="$(curl -sS -m 8 "$BASE/v1/compute/health")"
echo "$compute" | python3 -c "import json,sys; d=json.load(sys.stdin); llm=(d.get('llm') or {}); comfy=(d.get('comfyui') or {}); assert llm.get('ok') or comfy.get('ok') or d.get('ok') is True, d"
echo "PASS /v1/compute/health"

if [[ "${GENLAB_VENV:-}" != "" ]]; then
  ORCH_PY="$GENLAB_VENV/bin/python"
elif [[ "$ROOT" == /Volumes/* ]]; then
  ORCH_PY="$HOME/.cache/autodl-genlab/venv/bin/python"
else
  ORCH_PY="$ROOT/.venv/bin/python"
fi
if [[ ! -x "$ORCH_PY" ]]; then
  echo "FAIL missing orchestrator venv python: $ORCH_PY" >&2
  exit 1
fi

PYTHONPATH="$ROOT/orchestrator${PYTHONPATH:+:$PYTHONPATH}" "$ORCH_PY" - <<'PY'
from app.services_catalog import hydrate_services

items = hydrate_services(
    {
        "items": [
            {
                "id": "t2i.demo",
                "modality": "image",
                "label": "图",
                "provider": "comfyui",
                "workflow_id": "t2i.demo",
                "exposed": False,
            }
        ]
    }
)
by_id = {item.id: item for item in items}
assert by_id["t2i.demo"].exposed is False, by_id["t2i.demo"]
assert by_id["llm.chat"].exposed is True
assert by_id["t2v.u03"].modality == "video"
print("PASS hydrate keeps exposed=false")
from app.access_config import AccessConfig, hydrate_access
env = AccessConfig(
    mock_text=True,
    mock_image=True,
    mock_video=True,
    comfyui_endpoint="http://127.0.0.1:8188",
    llm_base_url="http://127.0.0.1:8088",
    llm_model="qwen",
)
got = hydrate_access({"mock_text": False, "llm_model": "saved-model"}, env=env)
assert got.mock_text is False
assert got.mock_image is True
assert got.llm_model == "saved-model"
assert got.comfyui_endpoint.endswith("8188")
print("PASS hydrate access keeps mock_text=false")
split = hydrate_access({"profile": "local", "local_llm_base_url": "http://127.0.0.1:9000"}, env=env)
assert split.profile == "local"
assert split.llm_base_url.endswith("9000")
assert split.autodl_llm_base_url == env.autodl_llm_base_url
print("PASS hydrate access keeps autodl path when switching local")
kept = hydrate_access({"autodl_ssh_password": ""}, env=env.model_copy(update={"autodl_ssh_password": "keep-secret"}))
assert kept.autodl_ssh_password == "keep-secret"
print("PASS hydrate access keeps ssh password when PUT empty")
lanes = hydrate_access(
    {
        "profile": "autodl",
        "autodl_text": {"enabled": True, "mock": False, "endpoint": "http://127.0.0.1:8088", "model": "qwen3.8-27b"},
        "autodl_image": {"enabled": False, "mock": True, "endpoint": "http://127.0.0.1:8188", "model": "t2i.demo"},
        "autodl_video": {"enabled": True, "mock": False, "endpoint": "http://127.0.0.1:8188", "model": "t2v.u03"},
    },
    env=env,
)
assert lanes.autodl_image.enabled is False
assert lanes.mock_image is True
assert lanes.mock_video is False
assert lanes.autodl_text.model == "qwen3.8-27b"
local_keep = hydrate_access({"profile": "local"}, env=lanes)
assert local_keep.autodl_video.mock is False
assert local_keep.autodl_text.model == "qwen3.8-27b"
print("PASS hydrate access keeps autodl lanes when switching local")
PY

python3 - "$BASE" <<'PY'
import json, sys, urllib.request
base = sys.argv[1]
catalog = json.loads(urllib.request.urlopen(base + "/v1/services", timeout=10).read().decode())
items = catalog.get("items") or []
modalities = {item.get("modality") for item in items}
assert {"text", "image", "video"} <= modalities, catalog
target = next(item for item in items if item.get("id") == "t2i.demo")
original = bool(target.get("exposed"))
req = urllib.request.Request(
    base + "/v1/services/t2i.demo",
    data=json.dumps({"exposed": False}).encode(),
    headers={"Content-Type": "application/json"},
    method="PATCH",
)
with urllib.request.urlopen(req, timeout=10) as resp:
    patched = json.loads(resp.read().decode())
assert patched.get("item", {}).get("exposed") is False, patched
again = json.loads(urllib.request.urlopen(base + "/v1/services", timeout=10).read().decode())
row = next(item for item in again["items"] if item["id"] == "t2i.demo")
assert row.get("exposed") is False, row
req2 = urllib.request.Request(
    base + "/v1/services/t2i.demo",
    data=json.dumps({"exposed": original}).encode(),
    headers={"Content-Type": "application/json"},
    method="PATCH",
)
urllib.request.urlopen(req2, timeout=10)
print("PASS /v1/services catalog+no overwrite", "count=", len(items))
PY

python3 - "$BASE" <<'PY'
import json, sys, urllib.request
base = sys.argv[1]
original = json.loads(urllib.request.urlopen(base + "/v1/access", timeout=10).read().decode())
body = {
    "mock_text": False,
    "mock_image": original["mock_image"],
    "mock_video": original["mock_video"],
    "profile": original.get("profile") or "autodl",
    "local_llm_base_url": original.get("local_llm_base_url") or original["llm_base_url"],
    "autodl_llm_base_url": original.get("autodl_llm_base_url") or original["llm_base_url"],
    "local_llm_model": original.get("local_llm_model") or original["llm_model"],
    "autodl_llm_model": original.get("autodl_llm_model") or original["llm_model"],
    "local_comfyui_endpoint": original.get("local_comfyui_endpoint") or original["comfyui_endpoint"],
    "autodl_comfyui_endpoint": original.get("autodl_comfyui_endpoint") or original["comfyui_endpoint"],
}
req = urllib.request.Request(
    base + "/v1/access",
    data=json.dumps(body).encode(),
    headers={"Content-Type": "application/json"},
    method="PUT",
)
with urllib.request.urlopen(req, timeout=10) as resp:
    saved = json.loads(resp.read().decode())
assert saved.get("mock_text") is False, saved
assert saved.get("autodl_llm_base_url") == body["autodl_llm_base_url"], saved
again = json.loads(urllib.request.urlopen(base + "/v1/access", timeout=10).read().decode())
assert again.get("mock_text") is False, again
restore = {k: original[k] for k in original if k not in ("ok", "orch_host", "orch_port")}
req2 = urllib.request.Request(
    base + "/v1/access",
    data=json.dumps(restore).encode(),
    headers={"Content-Type": "application/json"},
    method="PUT",
)
urllib.request.urlopen(req2, timeout=10)
print("PASS /v1/access no overwrite")
PY

python3 - "$BASE" "$ROOT/suites/demo.json" <<'PY'
import json, sys, time, urllib.request

base, suite_path = sys.argv[1], sys.argv[2]
health = json.loads(urllib.request.urlopen(base + "/health", timeout=5).read().decode())
suite = json.loads(open(suite_path, encoding="utf-8").read())
run_id = "run_verify_p0"
failed = []
for case in suite["cases"]:
    if case["modality"] == "video" and not health.get("mock"):
        print("SKIP live video enqueue (avoid GPU job in verify)")
        continue
    body = json.dumps({
        "modality": case["modality"],
        "prompt": case["prompt"],
        "suite_id": suite["id"],
        "case_id": case["id"],
        "workflow_id": case.get("workflow_id"),
        "run_id": run_id,
    }).encode("utf-8")
    req = urllib.request.Request(
        base + "/v1/jobs",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120 if case["modality"] == "text" else 15) as resp:
        job = json.loads(resp.read().decode("utf-8"))
    deadline = time.time() + (180 if case["modality"] == "text" else 15)
    while job.get("status") in ("queued", "running") and time.time() < deadline:
        time.sleep(1.5)
        job = json.loads(urllib.request.urlopen(base + "/v1/jobs/" + job["id"], timeout=10).read().decode())
    ok = job.get("status") == "succeeded" and job.get("output_uri")
    print(f"{'PASS' if ok else 'FAIL'} job {case['id']} status={job.get('status')} uri={job.get('output_uri')} elapsed_ms={job.get('elapsed_ms')}")
    if not ok:
        failed.append(case["id"])
if failed:
    sys.exit(1)
print("PASS suite", suite["id"], "mock_video=" + str(bool(health.get("mock"))))
PY

WEB_PORT="${WEB_PORT:-3190}"
if ! curl -sS -L -m 3 "http://127.0.0.1:${WEB_PORT}/" | grep -q "生成测试平台"; then
  echo "web down, starting..."
  bash "$ROOT/scripts/start.sh"
fi
if ! curl -sS -L -m 8 -o /tmp/genlab-web.html "http://127.0.0.1:${WEB_PORT}/"; then
  echo "FAIL web unreachable" >&2
  exit 1
fi
grep -q "生成测试平台" /tmp/genlab-web.html
echo "PASS web :$WEB_PORT"

if ! curl -sS -L -m 8 -o /tmp/genlab-services.html "http://127.0.0.1:${WEB_PORT}/services"; then
  echo "FAIL /services unreachable" >&2
  exit 1
fi
grep -q "服务配置" /tmp/genlab-services.html
echo "PASS web /services"

python3 - "$BASE" <<'PY'
import json, sys, urllib.error, urllib.request
base = sys.argv[1]
body = json.dumps({"modality": "image", "prompt": "verify score", "workflow_id": "t2i.demo"}).encode()
req = urllib.request.Request(base + "/v1/jobs", data=body, headers={"Content-Type": "application/json"}, method="POST")
with urllib.request.urlopen(req, timeout=10) as resp:
    job = json.loads(resp.read().decode())
jid = job["id"]
req2 = urllib.request.Request(
    base + f"/v1/jobs/{jid}/score",
    data=json.dumps({"score": 4}).encode(),
    headers={"Content-Type": "application/json"},
    method="PATCH",
)
with urllib.request.urlopen(req2, timeout=10) as resp:
    scored = json.loads(resp.read().decode())
assert scored.get("score") == 4, scored
req3 = urllib.request.Request(base + f"/v1/jobs/{jid}/file")
with urllib.request.urlopen(req3, timeout=10) as resp:
    data = resp.read()
assert len(data) > 20
assert job.get("elapsed_ms") is not None or scored.get("elapsed_ms") is not None
stats = json.loads(urllib.request.urlopen(base + "/v1/jobs/stats", timeout=10).read())
assert stats.get("total") >= 1, stats
assert "by_status" in stats and "avg_score" in stats, stats
req4 = urllib.request.Request(base + f"/v1/jobs/{jid}", method="DELETE")
with urllib.request.urlopen(req4, timeout=10) as resp:
    deleted = json.loads(resp.read().decode())
assert deleted.get("ok") is True, deleted
try:
    urllib.request.urlopen(base + f"/v1/jobs/{jid}", timeout=10)
    raise SystemExit("FAIL deleted job still exists")
except urllib.error.HTTPError as e:
    assert e.code == 404, e.code
print("PASS score+file+stats+delete", jid)
PY

llm_json="$(curl -sS -m 8 "$BASE/v1/llm/health" || true)"
echo "$llm_json"
python3 - "$BASE" "$llm_json" <<'PY'
import json, sys, urllib.request
base, raw = sys.argv[1], sys.argv[2]
try:
    d = json.loads(raw)
except Exception:
    print("SKIP llm health unreadable")
    raise SystemExit(0)
if d.get("provider") != "llamacpp" or not d.get("ok"):
    print("SKIP real llm", d.get("provider"), d.get("reason") or d.get("ok"))
    raise SystemExit(0)
body = json.dumps({"modality": "text", "prompt": "只回复：ok", "workflow_id": "llm.chat"}).encode()
req = urllib.request.Request(base + "/v1/jobs", data=body, headers={"Content-Type": "application/json"}, method="POST")
with urllib.request.urlopen(req, timeout=180) as resp:
    job = json.loads(resp.read().decode())
import time
deadline = time.time() + 180
while job.get("status") in ("queued", "running") and time.time() < deadline:
    time.sleep(1.5)
    job = json.loads(urllib.request.urlopen(base + "/v1/jobs/" + job["id"], timeout=10).read().decode())
assert job.get("provider") == "llm" and job.get("status") == "succeeded", job
print("PASS llama.cpp text", job.get("id"), job.get("output_uri"), "elapsed_ms=", job.get("elapsed_ms"), "tokens=", job.get("prompt_tokens"), job.get("completion_tokens"))
PY

echo "PASS verify"
