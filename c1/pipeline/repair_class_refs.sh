#!/usr/bin/env bash
# Restore the three game-class references that a cooked mod map must carry as
# property references only (never as actors -- that crashes the game).
#
#   $1 cooked .umap   $2 output .umap
set -euo pipefail

IN="$1"; OUT="$2"
TOOL="${TOOL:-csharp/UAssetTool/bin/Release/net8.0/UAssetTool.dll}"
DOTNET="${DOTNET:-dotnet}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

"$DOTNET" "$TOOL" --set-class-ref "$IN" "$TMP/a.umap" WorldSettings DefaultGameMode \
    /Game/GameMode/DriveGameModeBP DriveGameModeBP_C | tail -1
"$DOTNET" "$TOOL" --set-class-ref "$TMP/a.umap" "$TMP/b.umap" SunSky ChildActorClass \
    /Game/Blueprints/MTSunSky MTSunSky_C | tail -1
"$DOTNET" "$TOOL" --set-class-ref "$TMP/b.umap" "$OUT" Child ChildActorClass \
    /Game/Objects/GarageActorBP GarageActorBP_C | tail -1

# Verify: all three present, and no baked child-actor instances.
"$DOTNET" "$TOOL" --dump "$OUT" > "$TMP/dump.txt" 2>&1
grep -q 'DriveGameModeBP' "$TMP/dump.txt"
grep -q 'MTSunSky' "$TMP/dump.txt"
grep -q 'GarageActorBP' "$TMP/dump.txt"
if grep -qE 'Name=(MTSunSky|GarageActorBP)_C_[0-9]+' "$TMP/dump.txt"; then
    echo "FAIL: baked child-actor instance present -- this map will crash on load" >&2
    exit 1
fi
echo "REPAIR_OK $OUT"
