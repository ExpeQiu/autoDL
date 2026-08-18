#!/usr/bin/env bash
# 离线验收：不依赖 GPU / 外网。失败非 0。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "===== $(date -Iseconds) verify autodl CLI ====="

for f in README.md .env.example SKILL.md agent/manifest.json agent/mcp_server.py pyproject.toml autodl_cli/cli.py autodl_cli/mcp_adapter.py autodl_cli/mcp_server.py; do
  if [[ ! -f "$ROOT/$f" ]]; then
    echo "FAIL missing $f" >&2
    exit 1
  fi
done

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

echo "[1] 安装"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -q -e ".[dev]"

echo "[2] CLI 基础"
autodl --version
autodl --help >/dev/null
autodl job --help >/dev/null

echo "[3] config check"
CHECK="$(autodl --demo config check --format json)"
echo "$CHECK" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('module')=='config.check' and d.get('ok') is True, d
assert 'token_set' in d['items'][0]
print('  PASS config.check')
"

echo "[4] job submit --demo"
SUBMIT="$(autodl job submit --modality image --prompt '一只猫' --demo --format json)"
echo "$SUBMIT" | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('module')=='job.submit', d
assert d.get('data_source')=='demo', d
assert d.get('ok') is True, d
assert d.get('run_id','').startswith('run_'), d
assert d.get('job_id','').startswith('job_'), d
item=d['items'][0]
assert item.get('status')=='succeeded'
assert item.get('provider')=='mock'
assert item.get('modality')=='image'
assert item.get('output_uri')
open('/tmp/autodl_verify_job_id','w').write(d['job_id'])
print('  PASS job.submit', d['job_id'])
"
JOB_ID="$(cat /tmp/autodl_verify_job_id)"

echo "[5] job get / wait / file"
autodl job get "$JOB_ID" --format json | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('module')=='job.get' and d.get('ok') is True, d
assert d['items'][0]['id']==sys.argv[1]
print('  PASS job.get')
" "$JOB_ID"
autodl job wait "$JOB_ID" --format json | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('ok') is True and d['items'][0]['status']=='succeeded', d
print('  PASS job.wait')
"
autodl job file "$JOB_ID" -o /tmp/autodl_verify.svg --format json | python3 -c "
import json,sys
from pathlib import Path
d=json.load(sys.stdin)
assert d.get('ok') is True, d
assert Path('/tmp/autodl_verify.svg').is_file()
assert Path('/tmp/autodl_verify.svg').stat().st_size>20
print('  PASS job.file')
"

echo "[6] compute health --demo"
autodl --demo compute health --format json | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('module')=='compute.health' and d.get('ok') is True, d
assert d['items'][0]['comfyui']['ok'] is True
print('  PASS compute.health')
"

echo "[7] 三模态 demo"
for m in text image video; do
  autodl job submit --modality "$m" --prompt "verify $m" --demo --format json | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d['ok'] and d['items'][0]['modality']==sys.argv[1], d
print('  PASS modality', sys.argv[1])
" "$m"
done

echo "[8] power-on 无授权应失败"
set +e
autodl --demo instance power-on --format json >/tmp/autodl_power.json
code=$?
set -e
python3 -c "
import json
d=json.load(open('/tmp/autodl_power.json'))
assert d.get('ok') is False, d
" 
if [[ "$code" -eq 1 ]]; then
  echo "  PASS power-on blocked"
else
  echo "FAIL power-on exit=$code" >&2
  exit 1
fi

echo "[8b] instance/wallet --demo"
autodl --demo instance list --format json | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('module')=='instance.list' and d['items'][0].get('uuid'), d
print('  PASS instance.list demo')
"
autodl wallet balance --demo --format json | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('module')=='wallet.balance' and 'yuan' in d['items'][0], d
print('  PASS wallet.balance demo')
"

echo "[9] pytest"
python -m pytest -q tests/

echo "[10] tunnel --demo"
autodl tunnel start --demo --format json | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('module')=='tunnel.start' and d.get('ok') is True, d
print('  PASS tunnel.start demo')
"
autodl --demo tunnel status --format json | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('module')=='tunnel.status' and d.get('ok') is True, d
print('  PASS tunnel.status demo')
"
autodl tunnel stop --demo --format json | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d['items'][0].get('stopped') is True, d
print('  PASS tunnel.stop demo')
"

echo "[11] tunnel live status（未打隧道则为 exit 2）"
set +e
AUTODL_MOCK=false autodl tunnel status --format json >/tmp/autodl_tunnel_status.json
tcode=$?
set -e
python3 -c "
import json
d=json.load(open('/tmp/autodl_tunnel_status.json'))
assert d.get('module')=='tunnel.status' and d.get('data_source')=='live', d
assert 'password' not in json.dumps(d).lower()
print('  PASS live tunnel.status ok=', d.get('ok'), 'exit=', $tcode)
"
if [[ "$tcode" -ne 0 && "$tcode" -ne 2 ]]; then
  echo "FAIL tunnel status exit=$tcode" >&2
  exit 1
fi

echo "[12] 编排 live（编排未启动则跳过）"
ORCH="${ORCH_BASE:-http://127.0.0.1:8090}"
if curl -fsS -m 2 "$ORCH/health" >/dev/null 2>&1; then
  AUTODL_MOCK=false autodl compute health --format json | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('module')=='compute.health' and d.get('data_source')=='live', d
print('  PASS live compute.health ok=', d.get('ok'))
"
  AUTODL_MOCK=false autodl job submit --modality image --prompt 'p1 live' --format json | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('module')=='job.submit' and d.get('data_source')=='live', d
assert d.get('job_id','').startswith('job_'), d
assert d.get('run_id','').startswith('run_'), d
print('  PASS live job.submit', d['job_id'], d['items'][0].get('status'))
"
else
  echo "  SKIP $ORCH 未就绪"
fi

echo "[13] AutoDL OpenAPI（无 Token 则跳过）"
if [[ -n "${AUTODL_TOKEN:-}" ]]; then
  AUTODL_MOCK=false autodl wallet balance --format json | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('module')=='wallet.balance', d
assert 'password' not in json.dumps(d).lower()
print('  PASS live wallet.balance yuan=', d['items'][0].get('yuan') if d.get('ok') else d.get('error'))
"
  AUTODL_MOCK=false autodl instance list --format json | python3 -c "
import json,sys
d=json.load(sys.stdin)
assert d.get('module')=='instance.list', d
print('  PASS live instance.list count=', d.get('count'), 'ok=', d.get('ok'))
"
else
  echo "  SKIP 未设置 AUTODL_TOKEN"
fi

echo "[14] MCP adapter（仅 A 级）"
python3 -c "
from autodl_cli.mcp_adapter import call_tool, list_tools
names = {t['name'] for t in list_tools()}
assert 'autodl_job_submit_demo' in names, names
for blocked in ('autodl_instance_power_on', 'autodl_instance_power_off', 'autodl_job_submit_live', 'autodl_tunnel_start'):
    assert blocked not in names, blocked
r = call_tool('autodl_job_submit_demo', {'prompt': 'verify mcp'})
assert r['ok'] is True and r['result']['data_source']=='demo', r
print('  PASS mcp tools', len(names), 'job_id=', r['result'].get('job_id'))
"

echo "PASS verify autodl CLI"
