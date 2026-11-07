#!/usr/bin/env bash
# Build the GEOMETRY pak: the cell meshes and nothing else.
#
#   build_meshpak.sh <cooked-meshes-dir> <out.pak> [expected-mesh-count]
#
# Why meshes-only: the old geometry pak also carried C1Full.umap and C1Full_Roads.umap, so every
# mesh rebuild shipped a raw-cooked persistent level (no game mode, no sunsky, no P22 spawn/garage)
# and a roads level with no nav bake. Those levels were only harmless because the map and nav paks
# happened to sort later — the same silent-eviction trap build_levelpak.sh exists to prevent.
# Level assets are owned exclusively by the map, lights and nav paks; a mesh pak must never carry one.
set -euo pipefail

SRC="${1:?cooked meshes dir}"
OUT="${2:?output pak}"
EXPECT="${3:-554}"

REPAK="${REPAK:-/opt/data/workspace/mt-pak-wt-c1commit/target/release/repak}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

MESHES="$WORK/MotorTown/Content/Mods/C1Full/Meshes"
mkdir -p "$MESHES"

shopt -s nullglob
files=("$SRC"/*.uasset)
[ "${#files[@]}" -gt 0 ] || { echo "FAIL: no .uasset in $SRC" >&2; exit 2; }

for f in "${files[@]}"; do
    cp "$f" "$MESHES/"
    e="${f%.uasset}.uexp"
    [ -f "$e" ] || { echo "FAIL: missing sidecar $e" >&2; exit 2; }
    cp "$e" "$MESHES/"
done

n=${#files[@]}
[ "$n" -eq "$EXPECT" ] || { echo "FAIL: $n meshes staged, expected $EXPECT" >&2; exit 3; }

# Single-owner gate: level assets and materials belong to their own paks.
if find "$WORK" -name '*.umap' | grep -q .; then
    echo "FAIL: a .umap leaked into the mesh pak" >&2; exit 4
fi
if [ -d "$WORK/MotorTown/Content/Mods/C1Full/Materials" ]; then
    echo "FAIL: materials leaked into the mesh pak" >&2; exit 5
fi
if find "$WORK" -name 'ShaderArchive-*' | grep -q .; then
    echo "FAIL: shader archive in mesh pak" >&2; exit 6
fi

chmod -R 644 "$MESHES"/*
cd "$WORK"
RAYON_NUM_THREADS=1 "$REPAK" pack -m "../../../" --version V11 --compression Zlib -q . "$OUT"
echo "MESH_PAK_OK $n meshes $OUT $(stat -c%s "$OUT") $(sha256sum "$OUT" | cut -c1-16)"
