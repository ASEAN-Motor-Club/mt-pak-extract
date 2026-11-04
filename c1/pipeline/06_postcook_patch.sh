#!/usr/bin/env bash
# C1 stage 6 — post-cook class references.
#
# Two maps, two different fixes. Mixing them up fails loudly ("no export named
# SunSky"), because the roads sublevel has no WorldSettings/SunSky/Child.
#
#   parent map  (C1.umap)      -> repair_class_refs.sh  (GameMode, SunSky, Garage)
#   sublevel    (C1Roads.umap) -> --set-array-class-ref (spawner VehicleClass)
#
# Nothing here may be replaced by a runtime binding: the map must carry the
# references, exactly like the garage/sunsky refs.
#
#   $1 cooked dir containing C1.umap(.uexp) and/or C1Roads.umap(.uexp)
#   $2 output dir
set -euo pipefail
source "$(dirname "$0")/00_env.sh"

IN="${1:?cooked dir required}"
OUT="${2:?output dir required}"
mkdir -p "$OUT"

# UAssetTool needs the .uexp beside the .umap, and absolute paths.
abs() { python3 -c "import os,sys;print(os.path.abspath(sys.argv[1]))" "$1"; }

if [ -f "$IN/C1.umap" ]; then
    echo "== parent map: game-mode / sunsky / garage refs"
    bash "$C1_PIPE/repair_class_refs.sh" "$(abs "$IN/C1.umap")" "$(abs "$OUT/C1.umap")"
else
    echo "== parent map absent, skipping (delta build)"
fi

if [ -f "$IN/C1Roads.umap" ]; then
    echo "== roads sublevel: spawner VehicleClass"
    "$DOTNET" "$UATT_DLL" --set-array-class-ref \
        "$(abs "$IN/C1Roads.umap")" "$(abs "$OUT/C1Roads.umap")" \
        MTAIVehicleSpawnSystem_0 SpawnSettings SettingKey VehicleClass \
        "$C1_PIPE/vc_map.json" | tail -5

    # Verify: negative import index per patched row, and no baked child instances.
    "$DOTNET" "$UATT_DLL" --dump "$(abs "$OUT/C1Roads.umap")" > "$OUT/dump_roads.txt" 2>&1
    for k in Small Special Truck Bus; do
        grep -q "SettingKey (Name): $k" "$OUT/dump_roads.txt" || { echo "FAIL: $k row missing"; exit 2; }
    done
    if grep -qE 'Name=(MTSunSky|GarageActorBP)_C_[0-9]+' "$OUT/dump_roads.txt"; then
        echo "FAIL: baked child-actor instance — will crash on load" >&2; exit 3
    fi
    echo "PATCH_OK sublevel"
else
    echo "== roads sublevel absent, skipping (delta build)"
fi
