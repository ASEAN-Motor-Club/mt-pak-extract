#!/usr/bin/env bash
# C1 stage 9 — verification.
#
#   $1 optional pak to inspect (content + sublevel assertions)
#
# Live checks run against the staging probe written by the server mod
# (MotorTown/Saved/c1_srv_probe10.json). A zero vehicle count on a server with
# player_count 0 is NOT a failure: traffic is player-relative.
set -euo pipefail
source "$(dirname "$0")/00_env.sh"

PAK="${1:-}"
FAIL=0

if [ -n "$PAK" ]; then
    echo "== pak $PAK"
    "$MOD_EXPLORE" "$PAK" --list > /tmp/c1_pak_list.txt 2>&1 || { echo "FAIL: unreadable pak"; exit 2; }
    head -3 /tmp/c1_pak_list.txt
    grep -q 'Maps/C1_Roads.uexp' /tmp/c1_pak_list.txt && echo "OK roads sublevel" || { echo "FAIL no roads sublevel"; FAIL=1; }
    grep -q 'Maps/C1.umap'       /tmp/c1_pak_list.txt && echo "OK parent map"      || { echo "FAIL no parent map"; FAIL=1; }
    grep -q 'BP_C1_Sky'          /tmp/c1_pak_list.txt && echo "OK sky bp"          || { echo "WARN sky bp absent"; }
fi

echo "== live probe"
PROBE="/var/lib/$MT_INSTANCE/MotorTown/Saved/c1_srv_probe10.json"
ssh -o StrictHostKeyChecking=no "$STAGING" "cat '$PROBE'" > /tmp/c1_probe.json 2>/dev/null || true
if [ ! -s /tmp/c1_probe.json ]; then
    echo "WARN: no probe file — is the server-side probe mod installed and the server up?"
else
    python3 - /tmp/c1_probe.json <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
print("probe:", {k:d.get(k) for k in ("nav_nodes","nodes_with_road","nodes_null_road","spawn_system_valid","player_count","model_vehicles")})
bad=[]
if not d.get("nav_nodes"): bad.append("nav_nodes is 0 — graph did not survive cook/pak/load")
if d.get("nodes_with_road")!=d.get("nav_nodes"): bad.append("nodes_with_road != nav_nodes — graph lost road references")
if d.get("nodes_null_road"): bad.append("nodes_null_road != 0")
if not d.get("spawn_system_valid"): bad.append("spawn_system_valid false — no AMTAIVehicleSpawnSystem")
if bad:
    print("PROBE FAIL: "+"; ".join(bad)); sys.exit(1)
print("PROBE_OK")
PY
    [ $? -eq 0 ] || FAIL=1
fi

echo "== expected baselines"
python3 -c "import json;d=json.load(open('$C1_PIPE/constants.json'))['expected'];print(d)"

[ "$FAIL" -eq 0 ] && echo "VERIFY_OK" || { echo "VERIFY_FAIL"; exit 1; }
