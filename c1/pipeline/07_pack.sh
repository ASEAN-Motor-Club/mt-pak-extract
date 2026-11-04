#!/usr/bin/env bash
# C1 stage 7 — pack a directory tree into a compressed UE5 pak.
#
# mod_pack in this tree has NO compression flag: it writes stored entries
# (~248 MB for the C1 content that packs to ~69 MB). Use repak.
#
#   $1  input dir (the tree to pack, relative paths inside it)
#   $2  output pak
#   $3  optional mount point (default from constants.json)
set -euo pipefail
source "$(dirname "$0")/00_env.sh"

IN="${1:?input dir required}"
OUT="${2:?output pak required}"
MOUNT="${3:-$(c1_const '["level"]["mount_point"]')}"
VER="$(c1_const '["pack"]["version"]')"
COMP="$(c1_const '["pack"]["compression"]')"

[ -d "$IN" ] || { echo "FAIL: input dir missing: $IN" >&2; exit 2; }
[ -x "$REPAK" ] || { echo "FAIL: repak not built at $REPAK" >&2; exit 2; }

# Deterministic input ordering; refuse empty trees (a silent empty pak is worse
# than a failure).
NUM=$(find "$IN" -type f | wc -l)
[ "$NUM" -gt 0 ] || { echo "FAIL: input dir has no files: $IN" >&2; exit 3; }

"$REPAK" pack -m "$MOUNT" --version "$VER" --compression "$COMP" -q "$IN" "$OUT"

[ -s "$OUT" ] || { echo "FAIL: pak not written" >&2; exit 4; }

echo "PACK files=$NUM bytes=$(stat -c%s "$OUT") mount=$MOUNT ver=$VER comp=$COMP"
sha256sum "$OUT" | cut -c1-64

# Content assertion: the roads sublevel must be inside, or the map ships without AI.
# Capture the listing first: `mod_explore --list | grep -q` makes grep exit at the
# first match, mod_explore takes SIGPIPE (141), and `set -o pipefail` turns a
# SUCCESSFUL match into a failure. Cost one false FAIL already.
if [ -f "$IN/Maps/C1_Roads.uexp" ]; then
    "$MOD_EXPLORE" "$OUT" --list > /tmp/c1_pack_list.txt 2>/dev/null || true
    grep -q 'Maps/C1_Roads.uexp' /tmp/c1_pack_list.txt \
        || { echo "FAIL: Maps/C1_Roads.uexp missing from pak" >&2; exit 5; }
    echo "PACK_OK roads sublevel present"
fi
