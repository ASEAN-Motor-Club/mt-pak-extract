#!/usr/bin/env bash
# Build the whole-map lights pak: persistent level + the C1Full_Lights sublevel.
#
#   build_lightspak.sh <cooked-maps-dir> <out.pak>
#
# Ships TWO assets and deliberately NOT a third:
#   C1Full.umap        - the persistent level, because it is the only place the reference that
#                        loads the lights sublevel can live. A sublevel nobody references is
#                        dead content that fails silently.
#   C1Full_Lights.umap - the 10,474 light actors.
#   ...and C1Full_Roads is EXCLUDED on purpose: the nav bake owns that asset. Shipping our copy
#   would evict the nav graph again (one pak per asset, last-alphabetical-wins), which is the
#   exact bug this sublevel split exists to end.
set -euo pipefail

SRC="${1:?cooked maps dir (…/Saved/Cooked/Windows/MotorTown/Content/Mods/C1Full/Maps)}"
OUT="${2:?output pak}"
REPAK="${REPAK:-/opt/data/workspace/mt-pak-wt-c1commit/target/release/repak}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

MAPS="$WORK/MotorTown/Content/Mods/C1Full/Maps"
mkdir -p "$MAPS"

for stem in C1Full C1Full_Lights; do
    for ext in umap uexp; do
        f="$SRC/$stem.$ext"
        [ -f "$f" ] || { echo "FAIL: missing $f" >&2; exit 2; }
        cp "$f" "$MAPS/"
    done
done

if [ -e "$MAPS/C1Full_Roads.umap" ]; then
    echo "FAIL: C1Full_Roads leaked into the lights pak" >&2; exit 3
fi

if find "$WORK" -name 'ShaderArchive-*' | grep -q .; then
    echo "FAIL: shader archive in lights pak" >&2; exit 8
fi

chmod -R 644 "$MAPS"/*

cd "$WORK"
RAYON_NUM_THREADS=1 "$REPAK" pack -m "../../../" --version V11 --compression Zlib -q . "$OUT"
echo "LIGHTS_PAK_OK $OUT $(stat -c%s "$OUT") $(sha256sum "$OUT" | cut -c1-16)"
