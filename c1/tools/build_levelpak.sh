#!/usr/bin/env bash
# Build a LEVEL pak that ships exactly ONE of the C1Full level assets.
#
#   build_levelpak.sh <cooked-map-dir> <out.pak> <C1Full|C1Full_Lights|C1Full_Roads>
#
# Why one asset per pak: pak mounting keeps exactly one copy of each asset (last-alphabetical
# filename wins) and silently drops the rest. Every time one pak shipped two level assets, whoever
# sorted last decided which feature existed and the other vanished with no error:
#   - nav pak shipped C1Full.umap + C1Full_Roads  -> lights sublevel reference disappeared
#   - lights pak shipped C1Full.umap + C1Full_Lights -> nav's persistent level competed with ours
# So the ownership is now split by asset, and this script enforces it:
#
#   C1Full.umap        -> the MAP pak        (persistent level; the only owner of the
#                                             sublevel references)
#   C1Full_Lights.umap -> the LIGHTS pak     (all 10,474 light actors)
#   C1Full_Roads.umap  -> the NAV pak        (roads + nav graph)
#
# A pak may be rebuilt at any time without touching the others, and filename sort no longer
# decides whether a feature exists.
set -euo pipefail

SRC="${1:?cooked maps dir}"
OUT="${2:?output pak}"
STEM="${3:?one of: C1Full | C1Full_Lights | C1Full_Roads}"

REPAK="${REPAK:-/opt/data/workspace/mt-pak-wt-c1commit/target/release/repak}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

case "$STEM" in
    C1Full|C1Full_Lights|C1Full_Roads) ;;
    *) echo "FAIL: unknown level asset '$STEM' (expected C1Full, C1Full_Lights or C1Full_Roads)" >&2; exit 2 ;;
esac

MAPS="$WORK/MotorTown/Content/Mods/C1Full/Maps"
mkdir -p "$MAPS"
for ext in umap uexp; do
    f="$SRC/$STEM.$ext"
    [ -f "$f" ] || { echo "FAIL: missing $f" >&2; exit 2; }
    cp "$f" "$MAPS/"
done

# Single-owner gate: any other level asset in the staging dir is a bug, not a bonus.
for other in C1Full C1Full_Lights C1Full_Roads; do
    [ "$other" = "$STEM" ] && continue
    if [ -e "$MAPS/$other.umap" ]; then
        echo "FAIL: $other leaked in alongside $STEM" >&2; exit 3
    fi
done

# Stage-6 gate: a cooked persistent map carries NO game-mode/sunsky/garage class reference until
# c1/pipeline/06_postcook_patch.sh restores them. Ship the raw cook and the map loads with
# "missing game mode", no sky and no garage.
if [ "$STEM" = "C1Full" ]; then
    for token in DriveGameModeBP MTSunSky GarageActorBP; do
        if ! grep -qa "$token" "$MAPS/C1Full.umap"; then
            echo "FAIL: C1Full.umap has no $token reference — run 06_postcook_patch.sh first" >&2
            exit 4
        fi
    done
fi

if find "$WORK" -name 'ShaderArchive-*' | grep -q .; then
    echo "FAIL: shader archive in level pak" >&2; exit 8
fi

chmod -R 644 "$MAPS"/*
cd "$WORK"
RAYON_NUM_THREADS=1 "$REPAK" pack -m "../../../" --version V11 --compression Zlib -q . "$OUT"
echo "LEVEL_PAK_OK $STEM $OUT $(stat -c%s "$OUT") $(sha256sum "$OUT" | cut -c1-16)"
