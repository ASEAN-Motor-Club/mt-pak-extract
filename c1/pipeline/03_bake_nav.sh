#!/usr/bin/env bash
# C1 stage 3 — bake the traffic graph into the roads sublevel.
#
# Deterministic: roads are sampled sorted by actor label, so node indices and
# edge sets are reproducible for a given level + constants. Do not remove that
# sort or every rebuild silently renumbers the graph.
#
#   $1  optional bake config override (default: pipeline/nav_bake_config.json)
set -euo pipefail
source "$(dirname "$0")/00_env.sh"

# Baseline set: corridor (54 roads) is the default; C1FULL builds must pass
# C1_BAKE_SET=c1full or the gate compares against the wrong numbers and always drifts.
BASELINE="${C1_BAKE_SET:-corridor}"
case "$BASELINE" in
  corridor) KEY=expected ;;
  c1full)   KEY=expected_c1full ;;
  *) echo "FAIL: C1_BAKE_SET must be corridor|c1full" >&2; exit 2 ;;
esac
echo "bake baseline: $BASELINE ($KEY)"

CFG="${1:-$C1_PIPE/nav_bake_config.json}"
[ -f "$CFG" ] || { echo "FAIL: bake config missing: $CFG" >&2; exit 2; }

# keep the config the baker reads next to the script it reads it from
python3 - "$CFG" "$C1_WORK/nav_bake_config.json" <<'PY'
import json,sys,pathlib
src,dst=sys.argv[1],sys.argv[2]
pathlib.Path(dst).parent.mkdir(parents=True,exist_ok=True)
json.dump(json.load(open(src)),open(dst,"w"),indent=1)
print("bake config ->",dst)
PY

TAG="${TAG:-bake_$(date +%H%M%S)}"
bash "$WIN_PUT" "$C1_C1/tools/c1_bake_nav.py" "$WIN_PROJ/Scripts/c1_bake_nav.py" >/dev/null
bash "$WIN_PUT" "$C1_WORK/nav_bake_config.json" "$WIN_PROJ/Scripts/nav_bake_config.json" >/dev/null

bash "$WIN_PS" "$WIN_PROJ/Scripts/run_py_generic.ps1 $WIN_PROJ/Scripts/c1_bake_nav.py $TAG" 2>&1 | tail -1

REPORT="$(bash "$WIN_PS" "D:/greplog.ps1 $TAG C1BAKE_DONE" 2>&1 | grep -o 'C1BAKE_DONE {.*}' | tail -1)"
[ -n "$REPORT" ] || { echo "FAIL: no C1BAKE_DONE line — the bake did not run or raised" >&2; exit 3; }
echo "$REPORT"

python3 - "$REPORT" "$C1_PIPE/constants.json" "$KEY" <<'PY'
import json,sys,re
rep=json.loads(sys.argv[1].split(" ",1)[1])
exp=json.load(open(sys.argv[2]))[sys.argv[3]]
checks={"roads":"roads","nodes":"nodes","cross_links":"cross_links","lane_change":"lane_change","dead_ends":"dead_ends"}
bad=[]
for k,field in checks.items():
    want,got=exp.get(k),rep.get(field)
    if want!=got: bad.append("%s want=%s got=%s"%(k,want,got))
print("BAKE counts:", {k:rep.get(v) for k,v in checks.items()})
if rep.get("dead_ends")!=0:
    bad.append("dead_ends must be 0")
if bad:
    print("BAKE DRIFT: "+"; ".join(bad))
    print("BAKE_NOTE: drift is expected after a road-set change — re-record constants.json:%s and re-run" % sys.argv[3])
    sys.exit(4)
print("BAKE_OK")
PY
