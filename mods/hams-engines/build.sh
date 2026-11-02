#!/usr/bin/env bash
# Build ONE pak carrying both custom engines, so they stop fighting over the Vanilla
# `Engines` DataTable (only one pak can own it; last to load silently wins).
#
#   1. Hams Rotary 180HP  - rotary idle bed + V6Sport low/high + 26B brap  (was: "Test")
#   2. Test 330 Kart      - MediumDuty 330 diesel with the kart 10HP chainsaw layered under it
#
# Inputs:
#   --out     extracted vanilla assets for the target game version (flat dir is fine).
#             Needs SC_V8Engine.*, SC_Truck_02.*, FordSmalBlock302_V8_5L_180HP.*,
#             MediumDuty_250HP.*, Engines.*
#   --mt      extracted MoreTuning copy (third-party rotary audio, deliberately not committed):
#             Cars/Parts/Engine/Sound/13b/idle.* and .../26b/idle.*
#   --output  pak path
#
# Env:
#   MAPPINGS  path to Mappings.usmap (defaults to <repo>/Mappings.usmap)
#   MODPACK   path to mod_pack (defaults to <repo>/target/release/mod_pack)
#   MODPACK_LD  lib dir for mod_pack when not inside `nix develop`
#
# Deps: .NET 8 + initialised csharp/UAssetAPI submodule.
set -euo pipefail

OUT_ASSETS=""; MT_SRC=""; PAK_OUT=""; GAME_VERSION="0.7.19"; COMPAT_ENGINES=""
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT_ASSETS="$2"; shift 2 ;;
    --mt) MT_SRC="$2"; shift 2 ;;
    --output) PAK_OUT="$2"; shift 2 ;;
    --game-version) GAME_VERSION="$2"; shift 2 ;;
    --compat-engines) COMPAT_ENGINES="$2"; shift 2 ;;
    *) echo "unknown arg $1" >&2; exit 2 ;;
  esac
done
[ -n "$OUT_ASSETS" ] && [ -n "$MT_SRC" ] || {
  echo "usage: build.sh --out <vanilla-assets-dir> --mt <moretuning-extract-dir> [--output pak]" >&2; exit 2; }

# UAssetTool is invoked from csharp/UAssetTool and cuepatch from its own dir, so every
# path handed to them must be absolute.
abspath() { ( cd "$(dirname "$1")" && printf '%s/%s\n' "$(pwd)" "$(basename "$1")" ); }
OUT_ASSETS=$(abspath "$OUT_ASSETS")
MT_SRC=$(abspath "$MT_SRC")
if [ -n "$PAK_OUT" ]; then PAK_OUT=$(abspath "$PAK_OUT"); fi
if [ -n "$COMPAT_ENGINES" ]; then COMPAT_ENGINES=$(abspath "$COMPAT_ENGINES"); fi

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
MOD_DIR="$REPO_ROOT/mods/hams-engines"
WORK="$MOD_DIR/build"
UATOOL="$REPO_ROOT/csharp/UAssetTool"
MODPACK="${MODPACK:-$REPO_ROOT/target/release/mod_pack}"
MAPPINGS="${MAPPINGS:-$REPO_ROOT/Mappings.usmap}"
CUEPATCH="$MOD_DIR/tooling/cuepatch"
[ -n "$PAK_OUT" ] || PAK_OUT="$MOD_DIR/builds/zzz_AMC_HamsEngines_v0.2.0_${GAME_VERSION}_P.pak"

for f in "$MAPPINGS" "$OUT_ASSETS/SC_V8Engine.uasset" "$OUT_ASSETS/SC_Truck_02.uasset" \
         "$OUT_ASSETS/FordSmalBlock302_V8_5L_180HP.uasset" "$OUT_ASSETS/MediumDuty_250HP.uasset" \
         "$OUT_ASSETS/Engines.uasset" "$OUT_ASSETS/TorqueCurve_SmallBlock.uasset" \
         "$MT_SRC/MotorTown/Content/Cars/Parts/Engine/Sound/13b/idle.uasset" \
         "$MT_SRC/MotorTown/Content/Cars/Parts/Engine/Sound/26b/idle.uasset"; do
  [ -f "$f" ] || { echo "missing input: $f" >&2; exit 1; }
done
mkdir -p "$(dirname "$PAK_OUT")"

rm -rf "$WORK"; mkdir -p "$WORK"

CLEANUP_MAPPINGS=0
if [ ! -e "$REPO_ROOT/Mappings.usmap" ]; then
  ln -s "$MAPPINGS" "$REPO_ROOT/Mappings.usmap"
  CLEANUP_MAPPINGS=1
fi
trap '[ "$CLEANUP_MAPPINGS" = 1 ] && rm -f "$REPO_ROOT/Mappings.usmap"' EXIT

uatool() { ( cd "$UATOOL" && dotnet run -c Release --project . -- "$@" ); }
cuepatch() { ( cd "$CUEPATCH" && dotnet run -c Release --project . -- "$1" "$2" "$3" "$MAPPINGS" "${4:-}" ); }

echo "==== Hams Rotary 180HP ===="
echo "== 1/9 clone the vanilla V8 cue into /Game/Cars/Parts/Engine/Sound/13bV8"
uatool --clone-asset "$MOD_DIR/cue_clone.json" "$OUT_ASSETS/SC_V8Engine.uasset" "$WORK/r1_cue_clone"
echo "== 2/9 point the always-on idle wave player at 13b/idle"
uatool --patch-named-exports "$MOD_DIR/cue_patch.json" "$WORK/r1_cue_clone/SC_V8Engine/SC_V8Engine.uasset" "$WORK/r2_cue_13bidle"
echo "== 3/9 V6Sport low/high swap + hot idle crossfade"
cuepatch v6swap "$WORK/r2_cue_13bidle/SC_V8Engine.uasset" "$WORK/r3a_cue_v6"
echo "== 4/9 layer the 26B idle as a 4th input, gated to idle (fade 1600 -> 2200 rpm)"
cuepatch layer26b2 "$WORK/r3a_cue_v6/SC_V8Engine.uasset" "$WORK/r3_cue_layer26b"
echo "== 5/9 widen the pitch curve for the 9000 rpm redline"
cuepatch wide9000 "$WORK/r3_cue_layer26b/SC_V8Engine.uasset" "$WORK/r4_cue_wide"
echo "== 6/9 clone the 180HP V8 as Test_13bV6_180HP, cue repointed"
uatool --clone-asset "$MOD_DIR/engine_clone.json" "$OUT_ASSETS/FordSmalBlock302_V8_5L_180HP.uasset" "$WORK/r5_engine"
echo "== 7/10 copy the sound-relevant rotary numbers"
cuepatch soundonly "$WORK/r5_engine/Test_13bV6_180HP/Test_13bV6_180HP.uasset" "$WORK/r6_engine_sound"
echo "== 7a/10 clone the SmallBlock curve asset as TorqueCurve_Rotary"
uatool --clone-asset "$MOD_DIR/curve_clone.json" "$OUT_ASSETS/TorqueCurve_SmallBlock.uasset" "$WORK/r5b_curve_clone"
echo "== 7b/10 replace its keys with the rotary torque shape"
cuepatch rotarycurve "$WORK/r5b_curve_clone/TorqueCurve_Rotary/TorqueCurve_Rotary.uasset" "$WORK/r5c_curve_keys"
echo "== 7c/10 repoint the engine at the new curve + rescale MaxTorque for 250 hp"
cuepatch rotaryspec "$WORK/r6_engine_sound/Test_13bV6_180HP.uasset" "$WORK/r6b_engine_curve"
echo "== 8/9 add row TestEngine_13bV6 (label 'Hams Rotary 180HP') to the base table"
BASE_ENGINES="$OUT_ASSETS/Engines.uasset"
if [ -n "$COMPAT_ENGINES" ]; then
  [ -f "$COMPAT_ENGINES" ] || { echo "missing compat table: $COMPAT_ENGINES" >&2; exit 1; }
  BASE_ENGINES="$COMPAT_ENGINES"
  echo "   (compat base: $BASE_ENGINES)"
fi
uatool --add-rows "$MOD_DIR/add_row.json" "$BASE_ENGINES" "$WORK/r7_engines"

echo "==== Test 330 Kart ===="
echo "== 9a/9 clone SC_Truck_02 into /Game/Cars/Parts/Engine/Sound/MediumDuty330_Kart"
uatool --clone-asset "$MOD_DIR/cue_clone_330.json" "$OUT_ASSETS/SC_Truck_02.uasset" "$WORK/k1_cue_clone"
echo "== 9b/9 diesel sample swap + retune + chainsaw layer"
cuepatch kd330cue "$WORK/k1_cue_clone/SC_Truck_02/SC_Truck_02.uasset" "$WORK/k2_cue_mixed"
echo "== 9c/9 clone MediumDuty_250HP as Test_330Kart_330HP, cue repointed"
uatool --clone-asset "$MOD_DIR/engine_clone_330.json" "$OUT_ASSETS/MediumDuty_250HP.uasset" "$WORK/k3_engine"
echo "== 9d/9 copy the 330's engine numbers (MaxRPM 3500)"
cuepatch kd330engine "$WORK/k3_engine/Test_330Kart_330HP/Test_330Kart_330HP.uasset" "$WORK/k4_engine_330"
echo "== 9e/9 append row TestEngine_330Kart to the SAME table (37 -> 38)"
uatool --add-rows "$MOD_DIR/add_row_330.json" "$WORK/r7_engines/Engines.uasset" "$WORK/k5_engines"

echo "==== Test HD TDI V-Twin (Audi 5.5 TDI + Harley V-twin over a stock heavy duty) ===="
echo "== 10a clone the Harley cue into Sound/AMC/SC_HybridTDIVTwin"
uatool --clone-asset "$MOD_DIR/cue_hybrid.json" "$OUT_ASSETS/harley.uasset" "$WORK/h1_cue_clone"
echo "== 10b swap the idle/mid/high layers to the Audi TDI waves + rescale to 2900 rpm"
cuepatch hybridvtdi "$WORK/h1_cue_clone/SC_HybridTDIVTwin/SC_HybridTDIVTwin.uasset" "$WORK/h2_cue_hybrid"
echo "== 10c clone HeavyDuty_350HP as Test_HD_TDI_VTwin, cue repointed"
uatool --clone-asset "$MOD_DIR/engine_clone_hybrid.json" "$OUT_ASSETS/HeavyDuty_350HP.uasset" "$WORK/h3_engine"
echo "== 10d append row TestEngine_HDHybrid (38 -> 39)"
uatool --add-rows "$MOD_DIR/add_row_hybrid.json" "$WORK/k5_engines/Engines.uasset" "$WORK/k6_engines"

echo "==== Test Thumper (1,800 rpm lugger) ===="
echo "== 11a clone DieselTruck curve as TorqueCurve_Thumper"
uatool --clone-asset "$MOD_DIR/curve_clone_thumper.json" "$OUT_ASSETS/TorqueCurve_DieselTruck.uasset" "$WORK/t1_curve_clone"
echo "== 11b rewrite the keys: peak torque at half redline, hard decay after"
cuepatch thumpercurve "$WORK/t1_curve_clone/TorqueCurve_Thumper/TorqueCurve_Thumper.uasset" "$WORK/t2_curve"
echo "== 11c clone the Harley cue as SC_Thumper (hybrid layers, 1,800 rpm windows)"
uatool --clone-asset "$MOD_DIR/cue_clone_thumper.json" "$OUT_ASSETS/harley.uasset" "$WORK/t3_cue_clone"
cuepatch hybridvtdi "$WORK/t3_cue_clone/SC_Thumper/SC_Thumper.uasset" "$WORK/t4_cue" 1800
echo "== 11d clone HeavyDuty_350HP as Test_Thumper_1800 (numbers + curve only, sound = untouched HD hybrid cue)"
uatool --clone-asset "$MOD_DIR/engine_clone_thumper.json" "$OUT_ASSETS/HeavyDuty_350HP.uasset" "$WORK/t5_engine"
echo "== 11e Thumper engine numbers (3,000 Nm @ 900, 1,800 limiter)"
cuepatch thumperengine "$WORK/t5_engine/Test_Thumper_1800/Test_Thumper_1800.uasset" "$WORK/t6_engine"
echo "== 11f append row TestEngine_Thumper (39 -> 40)"
uatool --add-rows "$MOD_DIR/add_row_thumper.json" "$WORK/k6_engines/Engines.uasset" "$WORK/k7_engines"

S="$WORK/stage/MotorTown/Content"
mkdir -p "$S/DataAsset/VehicleParts" "$S/Cars/Parts/Engine/Sound/13bV8" \
         "$S/Cars/Parts/Engine/Sound/13b" "$S/Cars/Parts/Engine/Sound/26b" \
         "$S/Cars/Parts/Engine/Sound/MediumDuty330_Kart" \
         "$S/Cars/Parts/Engine/Sound/AMC" \
         "$S/Cars/Parts/Engine/TorqueCurve"
cp "$WORK/k6_engines/Engines.uasset" "$WORK/k6_engines/Engines.uexp" "$S/DataAsset/VehicleParts/"
cp "$WORK/k7_engines/Engines.uasset" "$WORK/k7_engines/Engines.uexp" "$S/DataAsset/VehicleParts/"
cp "$WORK/t4_cue/SC_Thumper.uasset" "$WORK/t4_cue/SC_Thumper.uexp" "$S/Cars/Parts/Engine/Sound/AMC/"
cp "$WORK/t2_curve/TorqueCurve_Thumper.uasset" "$WORK/t2_curve/TorqueCurve_Thumper.uexp" \
   "$S/Cars/Parts/Engine/TorqueCurve/"
cp "$WORK/t6_engine/Test_Thumper_1800.uasset" "$WORK/t6_engine/Test_Thumper_1800.uexp" \
   "$S/Cars/Parts/Engine/"
cp "$WORK/h2_cue_hybrid/SC_HybridTDIVTwin.uasset" "$WORK/h2_cue_hybrid/SC_HybridTDIVTwin.uexp" \
   "$S/Cars/Parts/Engine/Sound/AMC/"
cp "$WORK/h3_engine/Test_HD_TDI_VTwin/Test_HD_TDI_VTwin.uasset" "$WORK/h3_engine/Test_HD_TDI_VTwin/Test_HD_TDI_VTwin.uexp" \
   "$S/Cars/Parts/Engine/"
cp "$WORK/r6b_engine_curve/Test_13bV6_180HP.uasset" "$WORK/r6b_engine_curve/Test_13bV6_180HP.uexp" \
   "$S/Cars/Parts/Engine/"
cp "$WORK/r5c_curve_keys/TorqueCurve_Rotary.uasset" "$WORK/r5c_curve_keys/TorqueCurve_Rotary.uexp" \
   "$S/Cars/Parts/Engine/TorqueCurve/"
cp "$WORK/k4_engine_330/Test_330Kart_330HP.uasset" "$WORK/k4_engine_330/Test_330Kart_330HP.uexp" \
   "$S/Cars/Parts/Engine/"
cp "$WORK/r4_cue_wide/SC_V8Engine.uasset" "$WORK/r4_cue_wide/SC_V8Engine.uexp" \
   "$S/Cars/Parts/Engine/Sound/13bV8/"
cp "$WORK/k2_cue_mixed/SC_Truck_02.uasset" "$WORK/k2_cue_mixed/SC_Truck_02.uexp" \
   "$S/Cars/Parts/Engine/Sound/MediumDuty330_Kart/"
for d in 13b 26b; do
  cp "$MT_SRC/MotorTown/Content/Cars/Parts/Engine/Sound/$d/idle."{uasset,uexp,ubulk} \
     "$S/Cars/Parts/Engine/Sound/$d/"
done

if [ -n "${MODPACK_LD:-}" ]; then
  LD_LIBRARY_PATH="$MODPACK_LD" "$MODPACK" "$WORK/stage" "$PAK_OUT"
else
  "$MODPACK" "$WORK/stage" "$PAK_OUT"
fi
echo "built: $PAK_OUT"
