#!/usr/bin/env bash
# Post-cook edits: spawn, six garages at the BeamNG spawn sites, one fuel pump,
# and the three game-class references every cooked C1 map needs.
#
# WHY post-cook: DriveGameModeBP / MTSunSky / GarageActorBP / FuelPump_01A are
# GAME assets. The C1 editor project does not contain them, so the cook cannot
# reference them -- they must be written as property references afterwards.
# Never set ChildActorClass on the Blueprint template: that bakes a child-actor
# export and the game dies on load (RF_NeedLoad). Verified by the v14 crash.
#
# Usage: apply_map_edits_v17.sh <cooked .umap> <out .umap>
# Tool ops used (this UAssetTool build): --move-actor, --clone-actor,
#   --set-class-ref (first matching export), --set-child-class-refs (all matching
#   components on actors whose name starts with a prefix).
set -euo pipefail
IN="$1"; OUT="$2"
TOOL="${TOOL:-$HOME/uassettool}"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

# 1. Spawn + Shibaura garage (default spawn in the BeamNG source).
"$TOOL" --move-actor "$IN" "$TMP/s1.umap" PlayerStart_0 110237 -470902 87411 90 | tail -1
"$TOOL" --move-actor "$TMP/s1.umap" "$TMP/s2.umap" BP_C1_Prop_C_0 110237 -470902 87411 90 | tail -1

# 2. Remaining spawn sites (source: c1/source/c1_source_spawns_pois.json).
#    Yaw = source yaw + 180 (the map's Y axis is inverted).
#    spawn_garage is excluded: it is a BeamNG runtime placeholder at the origin.
"$TOOL" --clone-actor "$TMP/s2.umap" "$TMP/s3.umap" BP_C1_Prop_C_0 BP_C1_Prop_C_1 593234 -466784 87449 75.57 | tail -1  # Tatsumi 1st PA
"$TOOL" --clone-actor "$TMP/s3.umap" "$TMP/s4.umap" BP_C1_Prop_C_0 BP_C1_Prop_C_2 83167 406270 84990 13.4 | tail -1     # Yotsuyakamicho
"$TOOL" --clone-actor "$TMP/s4.umap" "$TMP/s5.umap" BP_C1_Prop_C_0 BP_C1_Prop_C_3 381965 511319 85216 154.0 | tail -1   # Hanedakuko (on deck)
"$TOOL" --clone-actor "$TMP/s5.umap" "$TMP/s6.umap" BP_C1_Prop_C_0 BP_C1_Prop_C_4 -844349 1606825 86672 259.1 | tail -1  # Shin-yamashita (on deck)

"$TOOL" --clone-actor "$TMP/s6.umap" "$TMP/s6b.umap" BP_C1_Prop_C_0 BP_C1_Prop_C_5 -13950 146710 85530 0 | tail -1  # Heiwajima

# 3. Fuel pump. A distinct actor name so the class-ref pass below touches ONLY
#    this actor -- the prefix match is the only targeting mechanism available.
"$TOOL" --clone-actor "$TMP/s6b.umap" "$TMP/s7.umap" BP_C1_Prop_C_0 BP_C1_Fuel_C_0 -10260 155550 85540 0 | tail -1

# 4. Class references on the map INSTANCES (never on the Blueprint).
"$TOOL" --set-class-ref "$TMP/s7.umap" "$TMP/s8.umap" WorldSettings DefaultGameMode \
    /Game/GameMode/DriveGameModeBP DriveGameModeBP_C | tail -1
"$TOOL" --set-class-ref "$TMP/s8.umap" "$TMP/s9.umap" SunSky ChildActorClass \
    /Game/Blueprints/MTSunSky MTSunSky_C | tail -1
"$TOOL" --set-child-class-refs "$TMP/s9.umap" "$TMP/s10.umap" BP_C1_Prop Child \
    /Game/Objects/GarageActorBP GarageActorBP_C | tail -1
"$TOOL" --set-child-class-refs "$TMP/s10.umap" "$OUT" BP_C1_Fuel Child \
    /Game/Objects/Fuel/FuelPump_01A FuelPump_01A_C | tail -1

# 5. Gate: a baked child-actor export means the map will crash on load.
"$TOOL" --dump "$OUT" > "$TMP/dump.txt" 2>&1
for cls in DriveGameModeBP MTSunSky GarageActorBP FuelPump_01A; do
    grep -q "$cls" "$TMP/dump.txt" || { echo "FAIL: $cls ref missing" >&2; exit 1; }
done
if grep -qE 'Name=(MTSunSky|GarageActorBP|FuelPump_01A)_C_[0-9]+' "$TMP/dump.txt"; then
    echo "FAIL: baked child-actor instance present -- map will crash on load" >&2
    exit 1
fi
echo "EDITS_OK $OUT  (6 garages + 1 fuel pump, drive game mode, sun sky)"
