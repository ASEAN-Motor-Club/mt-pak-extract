#!/usr/bin/env bash
# C1 pipeline driver.
#
#   ./run_all.sh author      # stages 2-4 (editor): roads, graph, spawner
#   ./run_all.sh build       # stages 5-7 (cook, patch, pack)
#   ./run_all.sh deploy      # stage 8 (stage only; RESTART=1 to activate)
#   ./run_all.sh verify      # stage 9
#   ./run_all.sh all         # everything, stopping at the first failure
#
# Environment overrides live in 00_env.sh. Nothing here restarts a live server
# unless RESTART=1 is set explicitly.
set -euo pipefail
source "$(dirname "$0")/00_env.sh"

STAGE="${1:-all}"
COOKED="${COOKED:-$C1_WORK/cooked_maps}"
PATCHED="${PATCHED:-$C1_WORK/patched}"
STAGE_DIR="${STAGE_DIR:-$C1_WORK/stage}"
PAK_OUT="${PAK_OUT:-$C1_WORK/$(c1_const '["pack"]["server_pak"]')}"

run_author() {
    bash "$C1_PIPE/02_author_roads.sh"
    bash "$C1_PIPE/03_bake_nav.sh"
    bash "$C1_PIPE/04_author_spawner.sh"
}

run_build() {
    bash "$C1_PIPE/05_cook.ps1"          # Windows side, via the relay is caller's choice
    bash "$C1_PIPE/06_postcook_patch.sh" "$COOKED" "$PATCHED"
    # assemble the staging tree: existing pak contents + patched maps
    mkdir -p "$STAGE_DIR/Maps"
    cp -f "$PATCHED"/C1*.umap "$PATCHED"/C1*.uexp "$STAGE_DIR/Maps/" 2>/dev/null || true
    bash "$C1_PIPE/07_pack.sh" "$STAGE_DIR" "$PAK_OUT"
}

case "$STAGE" in
    author) run_author ;;
    build)  run_build ;;
    deploy) bash "$C1_PIPE/08_deploy_staging.sh" "${2:-$PAK_OUT}" ;;
    verify) bash "$C1_PIPE/09_verify.sh" "${2:-$PAK_OUT}" ;;
    all)    run_author; run_build; bash "$C1_PIPE/09_verify.sh" "$PAK_OUT" ;;
    *) echo "usage: $0 {author|build|deploy|verify|all}" >&2; exit 2 ;;
esac
