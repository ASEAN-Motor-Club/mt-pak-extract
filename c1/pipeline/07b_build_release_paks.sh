#!/usr/bin/env bash
# C1 stage 7b — assemble and pack BOTH release trees.
#
# Server pak and client pak are not the same artifact:
#
#   server : full tree from the current server pak + patched Maps/C1_Roads.*
#            (the AI graph matters here)
#   client : full tree from the current client pak + Maps/C1.umap (the one with
#            the C1_Roads streaming link) + Maps/C1_Roads.* + BP_C1_Prop/Sky
#
# The client pak cannot be produced by copying the server pak's map alone: it
# carries different content (10,039 files vs 8,056) and its own C1.umap. The
# overlay merge is done here, in code, instead of by hand.
#
#   $1  dir with patched cooked maps (C1.umap, C1_Roads.umap/.uexp, ...)
#   $2  output dir
#
# BASE_SERVER_PAK / BASE_CLIENT_PAK default to the currently published artifacts;
# they supply everything that did not change in this build.
set -euo pipefail
source "$(dirname "$0")/00_env.sh"

PATCHED="${1:?patched cooked dir required}"
OUTDIR="${2:-$C1_WORK/release}"
mkdir -p "$OUTDIR"

BASE_SERVER_PAK="${BASE_SERVER_PAK:-$C1_WORK/release/server_base.pak}"
BASE_CLIENT_PAK="${BASE_CLIENT_PAK:-$C1_WORK/release/client_base.pak}"
SERVER_NAME="$(c1_const '["pack"]["server_pak"]')"
CLIENT_NAME="$(c1_const '["pack"]["client_pak"]')"

for p in "$BASE_SERVER_PAK" "$BASE_CLIENT_PAK"; do
    [ -f "$p" ] || { echo "FAIL: base pak missing: $p (set BASE_SERVER_PAK/BASE_CLIENT_PAK)" >&2; exit 2; }
done

# mod_explore --extract-all IGNORES its output argument: it writes ./mod_out
# relative to the CWD. cd into a scratch dir per pak.
assemble() {   # $1 base pak, $2 tree dir name, $3 overlay-set
    local base="$1" tree="$2" set="$3"
    rm -rf "$OUTDIR/$tree"
    mkdir -p "$OUTDIR/$tree"
    ( cd "$OUTDIR/$tree" && "$MOD_EXPLORE" "$base" --extract-all >/dev/null )
    [ -d "$OUTDIR/$tree/mod_out/Maps" ] || { echo "FAIL: extract produced no Maps/ in $tree" >&2; exit 3; }
    case "$set" in
        server)
            cp -f "$PATCHED"/C1_Roads.umap "$PATCHED"/C1_Roads.uexp "$OUTDIR/$tree/mod_out/Maps/"
            [ -f "$PATCHED/C1.umap" ] && cp -f "$PATCHED"/C1.umap "$PATCHED"/C1.uexp "$OUTDIR/$tree/mod_out/Maps/"
            ;;
        client)
            cp -f "$PATCHED"/C1_Roads.umap "$PATCHED"/C1_Roads.uexp "$OUTDIR/$tree/mod_out/Maps/"
            # the client needs the parent map that registers the streaming level
            cp -f "$PATCHED"/C1.umap "$PATCHED"/C1.uexp "$OUTDIR/$tree/mod_out/Maps/"
            [ -f "$PATCHED/BP_C1_Prop.uasset" ] && cp -f "$PATCHED"/BP_C1_* "$OUTDIR/$tree/mod_out/" || true
            ;;
    esac
}

echo "== server tree"
assemble "$BASE_SERVER_PAK" srv server
bash "$C1_PIPE/07_pack.sh" "$OUTDIR/srv/mod_out" "$OUTDIR/$SERVER_NAME"

echo "== client tree"
assemble "$BASE_CLIENT_PAK" cli client
bash "$C1_PIPE/07_pack.sh" "$OUTDIR/cli/mod_out" "$OUTDIR/$CLIENT_NAME"

echo "== assertions"
python3 - "$OUTDIR/$SERVER_NAME" "$OUTDIR/$CLIENT_NAME" "$MOD_EXPLORE" <<'PY'
import subprocess, sys
srv, cli, ex = sys.argv[1:4]
def listing(p):
    out = subprocess.run([ex, p, "--list"], capture_output=True, text=True).stdout
    files = {l.strip() for l in out.splitlines() if l.strip() and not l.startswith(("Opening", "Version", "Mount", "Total"))}
    return out, files
s_out, s = listing(srv)
c_out, c = listing(cli)
bad = []
for name, files in (("server", s), ("client", c)):
    if "Maps/C1_Roads.uexp" not in files: bad.append(f"{name}: no Maps/C1_Roads.uexp")
    if "Maps/C1.umap" not in files:      bad.append(f"{name}: no Maps/C1.umap")
    if "BP_C1_Sky.uasset" not in files:  bad.append(f"{name}: no BP_C1_Sky")
print("server files=%d client files=%d" % (len(s), len(c)))
if len(c) < len(s) * 0.9: bad.append("client tree looks truncated vs server")
if bad:
    print("PAKS_FAIL: " + "; ".join(bad)); sys.exit(1)
print("PAKS_OK both artifacts carry the map layer")
PY
