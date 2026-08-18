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

for f in README.md .env.example ADR/ADR-001-测试平台架构.md guide/架构与契约.md suites/demo.json workflows/minimax_h3_txt2vid.json; do
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
