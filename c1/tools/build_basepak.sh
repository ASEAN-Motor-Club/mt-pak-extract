#!/usr/bin/env bash
# Build the BASE pak: shared legacy content (/Game/Mods/C1 textures) + the two level BPs,
# with every asset class that another pak owns stripped out.
#
#   build_basepak.sh <source-pak> <out.pak>
#
# Why: the old base/geometry pak shipped Meshes, Materials AND Maps alongside the textures, so it
# overlapped four other paks and pak mount order — not intent — decided which copy was live. One
# asset, one pak is enforced here by removing the other owners' trees before packing.
#
# Ownership (see c1/tools/pakset.py check for the machine-verified version):
#   base   /Game/Mods/C1/**            textures referenced by the MIs (+ BP_C1_Prop, BP_C1_Sky)
#   meshes /Game/Mods/C1Full/Meshes
#   mats   /Game/Mods/C1Full/Materials
#   map    C1Full.umap        nav  C1Full_Roads.umap      lights  C1Full_Lights.umap
set -euo pipefail

SRC="${1:?source pak to split}"
OUT="${2:?output pak}"

REPAK="${REPAK:-/opt/data/workspace/mt-pak-wt-c1commit/target/release/repak}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Selective extraction: only the trees this pak owns. Unpacking the whole 700 MB pak to throw
# most of it away costs minutes and disk; `-i` takes exactly what survives the strip.
RAYON_NUM_THREADS=1 "$REPAK" unpack -q -f -o "$WORK/x" \
    -i "MotorTown/Content/Mods/C1" \
    -i "MotorTown/Content/Mods/C1Full/BP_C1_Prop.uasset" \
    -i "MotorTown/Content/Mods/C1Full/BP_C1_Prop.uexp" \
    -i "MotorTown/Content/Mods/C1Full/BP_C1_Sky.uasset" \
    -i "MotorTown/Content/Mods/C1Full/BP_C1_Sky.uexp" \
    "$SRC"

ROOT="$WORK/x/MotorTown/Content/Mods/C1Full"
[ -d "$ROOT" ] || { echo "FAIL: unexpected pak layout, no $ROOT" >&2; exit 2; }

# Strip the trees other paks own. Each of these was a live override before the split.
for owned in Meshes Materials Maps; do
    if [ -d "$ROOT/$owned" ]; then
        n=$(find "$ROOT/$owned" -type f | wc -l)
        rm -rf "$ROOT/$owned"
        echo "stripped $owned ($n files)"
    fi
done

# Gate: nothing the other paks own may survive the strip.
for bad in Meshes Materials Maps; do
    if [ -d "$ROOT/$bad" ]; then echo "FAIL: $bad still present" >&2; exit 3; fi
done
if find "$WORK/x" -name '*.umap' | grep -q .; then
    echo "FAIL: a level asset leaked into the base pak" >&2; exit 4
fi

# Gate: the legacy texture tree must survive, it is what the MIs point at.
[ -d "$WORK/x/MotorTown/Content/Mods/C1" ] || { echo "FAIL: /Game/Mods/C1 textures missing" >&2; exit 5; }
n=$(find "$WORK/x/MotorTown/Content/Mods/C1" -type f | wc -l)
[ "$n" -gt 1000 ] || { echo "FAIL: /Game/Mods/C1 only $n files, expected thousands" >&2; exit 6; }

cd "$WORK/x"
RAYON_NUM_THREADS=1 "$REPAK" pack -m "../../../" --version V11 --compression Zlib -q . "$OUT"
echo "BASE_PAK_OK legacy=$n $OUT $(stat -c%s "$OUT") $(sha256sum "$OUT" | cut -c1-16)"
