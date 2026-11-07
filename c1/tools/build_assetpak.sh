#!/usr/bin/env bash
# Build a small pak that overrides individual assets inside a bigger content pak.
#
#   build_assetpak.sh <content-dir> <out.pak>
#
# <content-dir> mirrors MotorTown/Content, e.g.
#   <content-dir>/Mods/C1Full/Meshes/c3_17.uasset
# Pak loading is last-alphabetical-wins, so a zzzzz_* pak overrides the same path inside the
# 700 MB geometry pak (zzzz_*) without a full repack.
set -euo pipefail

SRC="${1:?content dir mirroring MotorTown/Content}"
OUT="${2:?output pak}"
REPAK="${REPAK:-/opt/data/workspace/mt-pak-wt-c1commit/target/release/repak}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$WORK/MotorTown/Content"
cp -r "$SRC"/. "$WORK/MotorTown/Content/"

# Gate: a shader archive here crashes the client the same way it does in a material pak.
if find "$WORK" -name 'ShaderArchive-*' | grep -q .; then
    echo "FAIL: shader archive in override pak" >&2; exit 8
fi

echo "--- files in pak:"
(cd "$WORK" && find . -type f | sed 's#^\./##')

cd "$WORK"
RAYON_NUM_THREADS=1 "$REPAK" pack -m "../../../" --version V11 --compression Zlib -q . "$OUT"
echo "ASSET_PAK_OK $OUT $(stat -c%s "$OUT") $(sha256sum "$OUT" | cut -c1-16)"
