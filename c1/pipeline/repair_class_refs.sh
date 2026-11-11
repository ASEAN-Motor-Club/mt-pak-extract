#!/usr/bin/env bash
# Restore the three game-class references that a cooked mod map must carry as
# property references only (never as actors -- that crashes the game).
#
#   $1 cooked .umap   $2 output .umap
#
# Two things about UAssetTool that are easy to get wrong:
#
#   * the flag is --set-object-class-ref. --set-class-ref no longer exists; it
#     falls through to single-file mode and dies parsing an unrelated asset
#     ("count ('-22843') must be a non-negative value"). A map built without
#     these three refs has no game mode, no sun, and a garage that never becomes
#     an interactive actor.
#
#   * the tool resolves Mappings.usmap as "../.." from its CWD, so it only finds
#     the mappings when run from a directory exactly two levels below the repo
#     root. Running it from the repo root looks for repo/../Mappings.usmap and
#     aborts. Hence the chdir into .uatt_run/w below.
set -euo pipefail

abs() { python3 -c "import os,sys;print(os.path.abspath(sys.argv[1]))" "$1"; }

IN="$(abs "$1")"; OUT="$(abs "$2")"
REPO="${C1_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
TOOL="${TOOL:-$REPO/csharp/UAssetTool/bin/Release/net8.0/UAssetTool.dll}"
DOTNET="${DOTNET:-dotnet}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

RUN="$REPO/.uatt_run/w"
mkdir -p "$RUN"
cd "$RUN"

"$DOTNET" "$TOOL" --set-object-class-ref "$IN" "$TMP/a.umap" WorldSettings DefaultGameMode \
    /Game/GameMode/DriveGameModeBP DriveGameModeBP_C | tail -1
"$DOTNET" "$TOOL" --set-object-class-ref "$TMP/a.umap" "$TMP/b.umap" SunSky ChildActorClass \
    /Game/Blueprints/MTSunSky MTSunSky_C | tail -1
"$DOTNET" "$TOOL" --set-object-class-ref "$TMP/b.umap" "$OUT" Child ChildActorClass \
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
