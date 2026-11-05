#!/usr/bin/env bash
# C1 stage 7c — build the MATERIAL override pak from the source material definitions.
#
#   $1  material family prefix to rebuild (default: mat_mj)
#   $2  output pak (default: $C1_WORK/zzzzz_AMC_C1Mats_<family>_P.pak)
#
# Why this exists as a pipeline stage and not as shell history: every material family has the
# same three questions (is it alpha-tested, does it carry a separate opacity map, what is its
# threshold), and the answers live in the source map's own JSON. Doing it by hand produced six
# paks that changed nothing; this stage derives each instance's contract and applies it.
#
# The stage needs the geometry pak extracted (MATSRC) and the source material definitions
# (MATJSON). Both default to where the port already keeps them.
set -euo pipefail
source "$(dirname "$0")/00_env.sh"

FAMILY="${1:-mat_mj}"
OUT="${2:-$C1_WORK/zzzzz_AMC_C1Mats_${FAMILY}_P.pak}"

MATJSON="${MATJSON:-$C1_WORK/../beamng/x/levels/c1/art/models/merged.materials.json}"
MATSRC="${MATSRC:-$C1_WORK/geom_unpack/MotorTown/Content/Mods/C1Full/Materials}"
TEXSRC="${TEXSRC:-$C1_WORK/geom_unpack/MotorTown/Content/Mods/C1/Textures}"
WORK="${MATWORK:-$C1_WORK/matbuild_$FAMILY}"
# opacity_bake needs texture2ddecoder + etcpak; point PYTHONPATH at the venv that has them.
BAKE_SITE="${BAKE_SITE:-/opt/data/cache/scratch/c1/.bctex/lib/python3.11/site-packages}"

for p in "$MATJSON" "$MATSRC" "$TEXSRC"; do
    [ -e "$p" ] || { echo "FAIL: missing input $p" >&2; exit 2; }
done

export PYTHONPATH="$BAKE_SITE${PYTHONPATH:+:$PYTHONPATH}"
export DOTNET_ROLL_FORWARD=Major
export DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1

python3 "$C1_C1/tools/build_materials.py" \
    --source "$MATJSON" \
    --materials "$MATSRC" \
    --textures "$TEXSRC" \
    --tool "$UATT_DLL" \
    --dotnet "$DOTNET" \
    --family "$FAMILY" \
    --work "$WORK" \
    --pak "$OUT"
