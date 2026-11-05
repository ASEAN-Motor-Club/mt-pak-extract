#!/usr/bin/env bash
# C1 stage 1 — BeamNG DecalRoads -> road specs in the level's frame.
#
#   $1  items.level.json (source routing tree)
#   $2  output specs json (default: c1/road_specs_v2.json)
#
# The source routing layer is the ONLY source of lane geometry. An art-only
# extraction has no DecalRoad objects, so this stage legitimately fails rather
# than silently authoring an empty network.
set -euo pipefail
source "$(dirname "$0")/00_env.sh"

IN="${1:?items.level.json required}"
OUT="${2:-$C1_C1/road_specs_v2.json}"

[ -f "$IN" ] || { echo "FAIL: source not found: $IN" >&2; exit 2; }

python3 "$C1_C1/tools/build_decal_specs.py" "$IN" "$OUT"

python3 - "$OUT" <<'PY'
import json, sys, collections
d = json.load(open(sys.argv[1]))
roads = d["roads"] if isinstance(d, dict) else d
lanes = collections.Counter((r["forward_lanes"], r["backward_lanes"]) for r in roads)
widths = collections.Counter(r["lane_width"] for r in roads)
km = sum(r["length_m"] or 0 for r in roads) / 1000.0
print("SPECS roads=%d km=%.2f lanes=%s" % (len(roads), km, dict(lanes)))
print("SPECS lane_widths=%s" % dict(widths))
wide = [r["name"] for r in roads if r["lane_width"] > 400]
if wide:
    print("SPECS WARN lane_width>400cm on %d roads: %s" % (len(wide), wide[:8]))
print("SPECS_OK %s" % sys.argv[1])
PY
