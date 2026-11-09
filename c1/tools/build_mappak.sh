#!/usr/bin/env bash
# Build the MAP pak: the persistent level plus the sublevels it owns.
#
#   build_mappak.sh <cooked-maps-dir> <out.pak> <stem> [...]
#
#   build_mappak.sh /scratch/maps_final out/zzzzzz_AMC_C1Map_v9_P.pak C1Full C1Full_NoCollision
#
# C1Full_NoCollision is a sublevel of C1Full and is always cooked in the same run, so it ships in
# the same pak: the persistent level is the sole owner of its sublevel references, and a sublevel
# that is not next to its parent is a map that loads with a hole in it.
#
# Everything else keeps one asset per pak (C1Full_Lights, C1Full_Roads). A stem this pak was not
# asked to ship and that appears in the tree anyway is a bug, not a bonus.
set -euo pipefail

SRC="${1:?cooked maps dir}"
OUT="${2:?output pak}"
shift 2
[ "$#" -gt 0 ] || { echo "FAIL: no level stems given" >&2; exit 2; }

REPAK="${REPAK:-/opt/data/workspace/mt-pak-wt-c1commit/target/release/repak}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

MAPS="$WORK/MotorTown/Content/Mods/C1Full/Maps"
mkdir -p "$MAPS"

wanted=" "
for stem in "$@"; do
    for ext in umap uexp; do
        f="$SRC/$stem.$ext"
        [ -f "$f" ] || { echo "FAIL: missing $f" >&2; exit 2; }
        cp "$f" "$MAPS/"
    done
    wanted="$wanted$stem "
done
echo "staged:$wanted"

# A cooked persistent map carries NO game-mode/sunsky/garage class reference until
# c1/pipeline/06_postcook_patch.sh restores them, and no P22 spawn/garage edit until
# c1/scripts/apply_map_edits_p22.sh runs. Ship the raw cook and the map loads with
# "missing game mode", no sky, no garage, and the player spawns in the sea.
for token in DriveGameModeBP MTSunSky GarageActorBP; do
    if ! grep -qa "$token" "$MAPS/C1Full.umap"; then
        echo "FAIL: C1Full.umap has no $token reference — run 06_postcook_patch.sh first" >&2
        exit 4
    fi
done

# The no-collision sublevel must actually carry the two no-collision mesh families, or the split
# shipped a level that points at nothing.
if [ -f "$MAPS/C1Full_NoCollision.umap" ]; then
    grep -qa "C1_NoCollision_Paint" "$MAPS/C1Full_NoCollision.umap" ||
        { echo "FAIL: NoCollision level has no paint mesh reference" >&2; exit 5; }
    grep -qa "Meshes_NoCollision" "$MAPS/C1Full_NoCollision.umap" ||
        { echo "FAIL: NoCollision level has no foliage mesh references" >&2; exit 6; }
fi

if find "$WORK" -name 'ShaderArchive-*' | grep -q .; then
    echo "FAIL: shader archive in map pak" >&2; exit 8
fi

chmod -R 644 "$MAPS"/*
cd "$WORK"
RAYON_NUM_THREADS=1 "$REPAK" pack -m "../../../" --version V11 --compression Zlib -q . "$OUT"
echo "MAP_PAK_OK $wanted$OUT $(stat -c%s "$OUT") $(sha256sum "$OUT" | cut -c1-16)"
