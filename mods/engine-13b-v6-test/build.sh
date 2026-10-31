#!/usr/bin/env bash
# Build the ASEAN Test Engine pack: a standalone rotary engine part, no external mod deps.
#
# Inputs (NOT committed here):
#   --out   extracted vanilla assets for the target game version. Needs
#           SC_V8Engine.*, FordSmalBlock302_V8_5L_180HP.*, Engines.* (flat dir is fine).
#   --mt    extracted MoreTuning copy (third-party audio, deliberately not committed):
#           Cars/Parts/Engine/Sound/13b/idle.* and .../26b/idle.*
#
# Env:
#   MAPPINGS  path to Mappings.usmap (defaults to <repo>/Mappings.usmap)
#
# Deps: .NET 8 + initialised csharp/UAssetAPI submodule, cargo-built mod_pack.
set -euo pipefail

OUT_ASSETS=""; MT_SRC=""; PAK_OUT=""; GAME_VERSION="0.7.19"
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT_ASSETS="$2"; shift 2 ;;
    --mt) MT_SRC="$2"; shift 2 ;;
    --output) PAK_OUT="$2"; shift 2 ;;
    --game-version) GAME_VERSION="$2"; shift 2 ;;
    *) echo "unknown arg $1" >&2; exit 2 ;;
  esac
done
[ -n "$OUT_ASSETS" ] && [ -n "$MT_SRC" ] || {
  echo "usage: build.sh --out <vanilla-assets-dir> --mt <moretuning-extract-dir> [--output pak]" >&2; exit 2; }

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
MOD_DIR="$REPO_ROOT/mods/engine-13b-v6-test"
WORK="$MOD_DIR/build"
UATOOL="$REPO_ROOT/csharp/UAssetTool"
MODPACK="$REPO_ROOT/target/release/mod_pack"
MAPPINGS="${MAPPINGS:-$REPO_ROOT/Mappings.usmap}"
CUEPATCH="$MOD_DIR/tooling/cuepatch"
[ -n "$PAK_OUT" ] || PAK_OUT="zzz_ASEAN_TestEngine_v0.1.0_${GAME_VERSION}_P.pak"

for f in "$MAPPINGS" "$OUT_ASSETS/SC_V8Engine.uasset" "$OUT_ASSETS/Engines.uasset" \
         "$OUT_ASSETS/FordSmalBlock302_V8_5L_180HP.uasset" \
         "$MT_SRC/MotorTown/Content/Cars/Parts/Engine/Sound/13b/idle.uasset" \
         "$MT_SRC/MotorTown/Content/Cars/Parts/Engine/Sound/26b/idle.uasset"; do
  [ -f "$f" ] || { echo "missing input: $f" >&2; exit 1; }
done

rm -rf "$WORK"; mkdir -p "$WORK"

# UAssetTool resolves Mappings.usmap relative to the repo root (gitignored, version-pinned),
# so expose the caller's mapping file there for the run and clean it up afterwards.
CLEANUP_MAPPINGS=0
if [ ! -e "$REPO_ROOT/Mappings.usmap" ]; then
  ln -s "$MAPPINGS" "$REPO_ROOT/Mappings.usmap"
  CLEANUP_MAPPINGS=1
fi
trap '[ "$CLEANUP_MAPPINGS" = 1 ] && rm -f "$REPO_ROOT/Mappings.usmap"' EXIT

uatool() { ( cd "$UATOOL" && dotnet run --project . -- "$@" ); }
cuepatch() { ( cd "$CUEPATCH" && dotnet run -- "$1" "$2" "$3" "$MAPPINGS" ); }

echo "== 1/7 clone the vanilla V8 cue into /Game/Cars/Parts/Engine/Sound/13bV8"
uatool --clone-asset "$MOD_DIR/cue_clone.json" "$OUT_ASSETS/SC_V8Engine.uasset" "$WORK/1_cue_clone"

echo "== 2/7 point the always-on idle wave player at 13b/idle"
uatool --patch-named-exports "$MOD_DIR/cue_patch.json" "$WORK/1_cue_clone/SC_V8Engine/SC_V8Engine.uasset" "$WORK/2_cue_13bidle"

echo "== 3/7 swap the V8 high/low loops for the V6Sport samples, hot idle crossfade"
cuepatch v6swap "$WORK/2_cue_13bidle/SC_V8Engine.uasset" "$WORK/3a_cue_v6"

echo "== 3b/7 layer the 26B idle as a 4th mixer input, gated to idle (fade 1600 -> 2200 rpm)"
cuepatch layer26b2 "$WORK/3a_cue_v6/SC_V8Engine.uasset" "$WORK/3_cue_layer26b"

echo "== 4/7 widen the pitch curve for a 9000 rpm redline"
cuepatch wide9000 "$WORK/3_cue_layer26b/SC_V8Engine.uasset" "$WORK/4_cue_wide"

echo "== 5/7 clone the 180HP engine as Test_13bV6_180HP and repoint its cue to 13bV8"
uatool --clone-asset "$MOD_DIR/engine_clone.json" "$OUT_ASSETS/FordSmalBlock302_V8_5L_180HP.uasset" "$WORK/5_engine"

echo "== 6/7 copy the sound-relevant engine numbers from the 13b rotor"
cuepatch soundonly "$WORK/5_engine/Test_13bV6_180HP/Test_13bV6_180HP.uasset" "$WORK/6_engine_sound"

echo "== 7/7 add the row to the VANILLA Engines table (36 -> 37) and pack"
uatool --add-rows "$MOD_DIR/add_row.json" "$OUT_ASSETS/Engines.uasset" "$WORK/7_engines"

S="$WORK/stage/MotorTown/Content"
mkdir -p "$S/DataAsset/VehicleParts" "$S/Cars/Parts/Engine/Sound/13bV8" \
         "$S/Cars/Parts/Engine/Sound/13b" "$S/Cars/Parts/Engine/Sound/26b"
cp "$WORK/7_engines/Engines.uasset" "$WORK/7_engines/Engines.uexp" "$S/DataAsset/VehicleParts/"
cp "$WORK/6_engine_sound/Test_13bV6_180HP.uasset" "$WORK/6_engine_sound/Test_13bV6_180HP.uexp" \
   "$S/Cars/Parts/Engine/"
cp "$WORK/4_cue_wide/SC_V8Engine.uasset" "$WORK/4_cue_wide/SC_V8Engine.uexp" "$S/Cars/Parts/Engine/Sound/13bV8/"
for d in 13b 26b; do
  cp "$MT_SRC/MotorTown/Content/Cars/Parts/Engine/Sound/$d/idle."{uasset,uexp,ubulk} \
     "$S/Cars/Parts/Engine/Sound/$d/"
done

# mod_pack dlopens libstdc++ from the nix devshell; pass its lib dir via MODPACK_LD
# when building outside `nix develop`. Do NOT export LD_LIBRARY_PATH globally: it
# shadows the ICU libraries the .NET SDK needs.
if [ -n "${MODPACK_LD:-}" ]; then
  LD_LIBRARY_PATH="$MODPACK_LD" "$MODPACK" "$WORK/stage" "$PAK_OUT"
else
  "$MODPACK" "$WORK/stage" "$PAK_OUT"
fi
echo "built: $PAK_OUT"
