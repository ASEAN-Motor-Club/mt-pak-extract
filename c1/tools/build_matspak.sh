#!/usr/bin/env bash
# Build a MATERIAL-ONLY pak that overrides the material instances of an installed map pak.
#
#   build_matspak.sh <materials-dir-with-uasset+uexp> <out.pak> [extra-content-dir]
#
# Why: material instances are separate assets referenced by path from the meshes, and
# pak loading is last-alphabetical-wins. A pak named zzzzz_* therefore overrides the
# copies inside the geometry pak (zzzz_*) without touching meshes, maps or textures.
# A material iteration is seconds, not a 20-minute cook.
#
# <extra-content-dir> maps directly onto MotorTown/Content (use it for assets the
# overridden materials import, e.g. the author's own master materials).
set -euo pipefail

SRC="${1:?materials dir with .uasset/.uexp}"
OUT="${2:?output pak}"
EXTRA="${3:-}"
REPAK="${REPAK:-/opt/data/workspace/mt-pak-wt-c1commit/target/release/repak}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$WORK/MotorTown/Content/Mods/C1Full/Materials"
cp "$SRC"/*.uasset "$SRC"/*.uexp "$WORK/MotorTown/Content/Mods/C1Full/Materials/"
[ -n "$EXTRA" ] && cp -r "$EXTRA"/. "$WORK/MotorTown/Content/"

chmod -R 644 "$WORK"/MotorTown/Content/Mods/*/Materials/* 2>/dev/null || true

# Gate: never ship shader archives (v11 crash), and never ship anything but materials.
if find "$WORK" -name 'ShaderArchive-*' | grep -q .; then
    echo "FAIL: shader archive in material pak" >&2; exit 8
fi

cd "$WORK"
RAYON_NUM_THREADS=1 "$REPAK" pack -m "../../../" --version V11 --compression Zlib -q . "$OUT"
echo "MATS_PAK_OK $OUT $(stat -c%s "$OUT") $(sha256sum "$OUT" | cut -c1-16)"
