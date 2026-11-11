#!/usr/bin/env bash
# Build the GEOMETRY pak: cell meshes plus the no-collision meshes, and nothing else.
#
#   build_meshpak.sh <out.pak> <expected-mesh-count> <src-dir>:<relpath> [...]
#
#   build_meshpak.sh out/zzzzz_AMC_C1Mesh_v8_P.pak 792 \
#       /scratch/cooked3/Meshes:Meshes \
#       /scratch/cooked3/Meshes_NoCollision:Meshes_NoCollision
#
# Why meshes-only: the old geometry pak also carried C1Full.umap and C1Full_Roads.umap, so every
# mesh rebuild shipped a raw-cooked persistent level (no game mode, no sunsky, no P22 spawn/garage)
# and a roads level with no nav bake. Those levels were only harmless because the map and nav paks
# happened to sort later — the same silent-eviction trap build_levelpak.sh exists to prevent.
# Level assets are owned exclusively by the map, lights and nav paks; a mesh pak must never carry one.
set -euo pipefail

OUT="${1:?output pak}"
EXPECT="${2:?expected total mesh count}"
shift 2
[ "$#" -gt 0 ] || { echo "FAIL: no <src-dir>:<relpath> pairs" >&2; exit 2; }

REPAK="${REPAK:-/opt/data/workspace/mt-pak-wt-c1commit/target/release/repak}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

MODS="$WORK/MotorTown/Content/Mods/C1Full"
mkdir -p "$MODS"
n=0
for pair in "$@"; do
    src="${pair%%:*}"
    rel="${pair##*:}"
    [ -d "$src" ] || { echo "FAIL: no such dir $src" >&2; exit 2; }
    mkdir -p "$MODS/$rel"
    shopt -s nullglob
    files=("$src"/*.uasset)
    [ "${#files[@]}" -gt 0 ] || { echo "FAIL: no .uasset in $src" >&2; exit 2; }
    for f in "${files[@]}"; do
        e="${f%.uasset}.uexp"
        [ -f "$e" ] || { echo "FAIL: missing sidecar $e" >&2; exit 2; }
        cp "$f" "$MODS/$rel/"
        cp "$e" "$MODS/$rel/"
        n=$((n + 1))
    done
    echo "staged $rel: ${#files[@]} meshes"
done

[ "$n" -eq "$EXPECT" ] || { echo "FAIL: $n meshes staged, expected $EXPECT" >&2; exit 3; }

# Material gate: verify the COOKED assets, not the editor's memory. Runs on the staged
# tree so what is checked is exactly what gets packed. The editor readback in
# import_split.py cannot be trusted for this (it re-reads the cached UObject, which is
# how v13 shipped with no materials and v14/v15 shipped an invisible NoCollision layer).
# Skip only for a deliberate forensics build: ALLOW_UNBOUND_MATERIALS=1.
if [ "${ALLOW_UNBOUND_MATERIALS:-0}" != "1" ]; then
    VERIFY_SLOTMAP="${VERIFY_SLOTMAP:-/opt/data/cache/scratch/slotmap.json}"
    if ! bash "$(dirname "${BASH_SOURCE[0]}")/verify_cooked.sh" "$MODS" "$VERIFY_SLOTMAP"; then
        echo "FAIL: cooked asset verification failed -- refusing to pack" >&2
        exit 7
    fi
else
    echo "WARNING: ALLOW_UNBOUND_MATERIALS=1 -- skipping the material gate"
fi

# Single-owner gate: level assets and materials belong to their own paks.
if find "$WORK" -name '*.umap' | grep -q .; then
    echo "FAIL: a .umap leaked into the mesh pak" >&2; exit 4
fi
if [ -d "$MODS/Materials" ]; then
    echo "FAIL: materials leaked into the mesh pak" >&2; exit 5
fi
if find "$WORK" -name 'ShaderArchive-*' | grep -q .; then
    echo "FAIL: shader archive in mesh pak" >&2; exit 6
fi

find "$MODS" -type f -exec chmod 644 {} +
cd "$WORK"
RAYON_NUM_THREADS=1 "$REPAK" pack -m "../../../" --version V11 --compression Zlib -q . "$OUT"
echo "MESH_PAK_OK $n meshes $OUT $(stat -c%s "$OUT") $(sha256sum "$OUT" | cut -c1-16)"
