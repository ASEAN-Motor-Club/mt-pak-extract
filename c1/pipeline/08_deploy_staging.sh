#!/usr/bin/env bash
# C1 stage 8 — put a pak on the staging instance and (optionally) restart it.
#
#   $1 pak
#   $2 target filename inside .mod-cache/paks (default: constants server_pak)
#
# The filename is kept STABLE while iterating: the operator approves paks by
# name, so a new name means a new approval every build. Version the name only
# at publish time.
#
# Restarting drops whoever is testing and re-runs the pre-start that wipes
# non-base paks in Content/Paks/. It is therefore gated: set RESTART=1.
set -euo pipefail
source "$(dirname "$0")/00_env.sh"

PAK="${1:?pak required}"
NAME="${2:-$(c1_const '["pack"]["server_pak"]')}"
CACHE_DIR="/var/lib/$MT_INSTANCE/.mod-cache/paks"
RESTART="${RESTART:-0}"

[ -f "$PAK" ] || { echo "FAIL: pak missing: $PAK" >&2; exit 2; }

SIZE=$(stat -c%s "$PAK")
SHA=$(sha256sum "$PAK" | cut -c1-24)
ssh -o StrictHostKeyChecking=no "$STAGING" "install -D -m 0664 '$PAK' '$CACHE_DIR/$NAME'"

GET=$(ssh -o StrictHostKeyChecking=no "$STAGING" "sha256sum '$CACHE_DIR/$NAME' | cut -c1-24")
[ "$GET" = "$SHA" ] || { echo "FAIL: cache copy sha mismatch ($GET != $SHA)" >&2; exit 3; }
echo "STAGED $NAME bytes=$SIZE sha=$SHA"

if [ "$RESTART" != "1" ]; then
    echo "STAGED_ONLY — set RESTART=1 to activate (this drops connected players)"
    exit 0
fi

ssh -o StrictHostKeyChecking=no "$STAGING" "systemctl restart $MT_INSTANCE"
ssh -o StrictHostKeyChecking=no "$STAGING" "systemctl is-active $MT_INSTANCE"
echo "RESTARTED $MT_INSTANCE"
