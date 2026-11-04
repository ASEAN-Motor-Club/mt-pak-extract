#!/usr/bin/env bash
# C1 stage 2 — author the road actors into the roads sublevel (editor side).
#
# Runs the authoring script inside the mirror project's editor via the Windows
# relay. Idempotent: the script destroys its own outputs (label prefix list)
# before spawning, so a second run does not double the network.
#
#   $1  optional script path override (default: tools/author_decal_roads.py)
set -euo pipefail
source "$(dirname "$0")/00_env.sh"

SRC="${1:-$C1_C1/tools/author_decal_roads.py}"
REMOTE="$WIN_PROJ/Scripts/$(basename "$SRC")"
TAG="${TAG:-author_$(date +%H%M%S)}"

bash "$WIN_PUT" "$SRC" "$REMOTE" >/dev/null
bash "$WIN_PS" "$WIN_PROJ/Scripts/run_py_generic.ps1 $REMOTE $TAG" 2>&1 | tail -1

# Acceptance: the authoring script prints AUTHORED= / FAILED= / VERIFIED=
bash "$WIN_PS" "D:/greplog.ps1 $TAG AUTHORED" 2>&1 | grep -E 'AUTHORED=|VERIFIED=' | tail -2
