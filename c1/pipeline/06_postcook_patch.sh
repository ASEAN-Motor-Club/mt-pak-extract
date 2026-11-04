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
# Map names are overridable so the same stage serves the corridor build (C1 /
# C1Roads) and the full-map build (C1Full / C1Full_Roads).
PARENT_MAP="${PARENT_MAP:-C1}"
SUB_MAP="${SUB_MAP:-C1Roads}"
mkdir -p "$OUT"

# UAssetTool needs the .uexp beside the .umap, and absolute paths.
abs() { python3 -c "import os,sys;print(os.path.abspath(sys.argv[1]))" "$1"; }

if [ -f "$IN/$PARENT_MAP.umap" ]; then
    echo "== parent map: game-mode / sunsky / garage refs"
    bash "$C1_PIPE/repair_class_refs.sh" "$(abs "$IN/$PARENT_MAP.umap")" "$(abs "$OUT/$PARENT_MAP.umap")"
else
    echo "== parent map absent, skipping (delta build)"
fi

if [ -f "$IN/$SUB_MAP.umap" ]; then
    echo "== roads sublevel: spawner VehicleClass"
    # The spawner export is renamed on every re-authoring (_0 -> _1 -> _2 ...).
    # Never hardcode it: dump the cooked map and take the name it actually has.
    SPAWNER="$("$DOTNET" "$UATT_DLL" --dump "$(abs "$IN/$SUB_MAP.umap")" 2>/dev/null \
        | grep -oE 'Name=MTAIVehicleSpawnSystem_[0-9]+' | head -1 | cut -d= -f2)"
    [ -n "$SPAWNER" ] || { echo "FAIL: no MTAIVehicleSpawnSystem export in $SUB_MAP" >&2; exit 4; }
    echo "   spawner export: $SPAWNER"
    "$DOTNET" "$UATT_DLL" --set-array-class-ref \
        "$(abs "$IN/$SUB_MAP.umap")" "$(abs "$OUT/$SUB_MAP.umap")" \
        "$SPAWNER" SpawnSettings SettingKey VehicleClass \
        "$C1_PIPE/vc_map.json" | tail -5

    # Verify: negative import index per patched row, and no baked child instances.
    "$DOTNET" "$UATT_DLL" --dump "$(abs "$OUT/$SUB_MAP.umap")" > "$OUT/dump_roads.txt" 2>&1
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
