#!/usr/bin/env bash
# C1 stage 4 — author the AI spawn system into the roads sublevel.
#
# Rows live EMBEDDED in tools/author_traffic_spawner.py (ROWS = json.loads(r"""...""")).
# A sibling JSON file is not read, and mutating the struct array in the editor
# does not persist. Edit the script, not the level.
#
# Non-traffic rows must stay at MaxCount = 0 (Getaway and every service row).
set -euo pipefail
source "$(dirname "$0")/00_env.sh"

SRC="$C1_C1/tools/author_traffic_spawner.py"
TAG="${TAG:-spawn_$(date +%H%M%S)}"

# Guard: refuse to run if a non-traffic row has a non-zero MaxCount.
python3 - "$SRC" <<'PY'
import re,sys
src=open(sys.argv[1]).read()
m=re.search(r'ROWS\s*=\s*json\.loads\(r"""(.*?)"""\)', src, re.S)
if not m: sys.exit("FAIL: cannot find embedded ROWS in the spawner script")
import json
rows=json.loads(m.group(1))
keep={"Small","Special","Truck","Bus"}
bad=[r for r in rows if r.get("SettingKey") not in keep and int(r.get("MaxCount",0))!=0]
if bad:
    sys.exit("FAIL: non-traffic rows with MaxCount!=0: %s" % [r.get("SettingKey") for r in bad])
print("SPAWNER rows=%d keep=%s all_other_rows_zero=True" % (len(rows), sorted(keep & {r.get("SettingKey") for r in rows})))
PY

bash "$WIN_PUT" "$SRC" "$WIN_PROJ/Scripts/author_traffic_spawner.py" >/dev/null
bash "$WIN_PS" "$WIN_PROJ/Scripts/run_py_generic.ps1 $WIN_PROJ/Scripts/author_traffic_spawner.py $TAG" 2>&1 | tail -1

# Acceptance: the script logs per-setting readback; require the 4 traffic rows
# present and every other row at zero.
bash "$WIN_PS" "D:/greplog.ps1 $TAG SPAWN" 2>&1 | grep -E 'MaxCount|SPAWN' | tail -20
