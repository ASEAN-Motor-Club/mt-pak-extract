#!/usr/bin/env bash
# C1 map edits applied to the SHIPPED cooked map (no recook) — P22.
#
# Every step reads the previous step's output, so the order matters. The tool ops used here
# (--move-actor, --clone-actor) both write .umap + .uexp pairs; ship them together or the
# level loads with no roads.
#
#   $1  extracted cooked map dir (MotorTown/Content/Mods/C1Full/Maps)
#   $2  output dir
#
# Coordinates are UE cm; the map's Y is inverted relative to the BeamNG source, hence the
# +180 in the headings (source-derived yaw for Shibaura is 270, Tatsumi 255.57).
set -euo pipefail
IN="${1:?cooked Maps dir required}"
OUT="${2:?output dir required}"
TOOL="${TOOL:-$HOME/uassettool}"

SHIBAURA="110237 -470902 87411"     # spawn_default (Shibaura PA)
TATSUMI="593234 -466784 87449"      # spawn_parking (Tatsumi 1st PA)

mkdir -p "$OUT"
cp -f "$IN/C1Full.umap" "$OUT/s0.umap"
cp -f "$IN/C1Full.uexp" "$OUT/s0.uexp"

# 1. player spawn -> Shibaura
"$TOOL" --move-actor "$OUT/s0.umap" "$OUT/s1.umap" PlayerStart_0 $SHIBAURA 90
# 2. the single existing garage -> Shibaura (its components ride along; the transform lives
#    in the root DefaultSceneRoot)
"$TOOL" --move-actor "$OUT/s1.umap" "$OUT/s2.umap" BP_C1_Prop_C_0 $SHIBAURA 90
# 3. clone that garage structure verbatim -> Tatsumi
"$TOOL" --clone-actor "$OUT/s2.umap" "$OUT/s3.umap" BP_C1_Prop_C_0 BP_C1_Prop_C_1 $TATSUMI 75.57

echo "MAP_EDITS_OK -> $OUT/s3.umap (+s3.uexp)"
