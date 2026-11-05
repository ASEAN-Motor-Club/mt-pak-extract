#!/usr/bin/env bash
# Build the repak CLI (packing with compression) into target/release.
#
# mod_pack/mod_explore in this tree cannot compress, so full-content paks are
# built with repak. repak is a git dependency of this crate, already vendored in
# the Cargo.lock; build the CLI from that checkout so the version matches.
#
# Run on the host (needs the nix dev shell):
#   ssh root@host.docker.internal "$(pwd)/make_repak.sh"
set -euo pipefail
source "$(dirname "$0")/00_env.sh"

CARGO_GIT="${CARGO_GIT:-/root/.cargo/git/checkouts/repak-*/*}"
SRC=$(ls -d $CARGO_GIT 2>/dev/null | head -1)
[ -n "$SRC" ] || { echo "FAIL: repak checkout not found (cargo has not fetched it yet)" >&2; exit 2; }

cd "$SRC"
/run/current-system/sw/bin/nix develop "$C1_REPO" --command cargo build --release -p repak_cli
install -m 0755 "$SRC/target/release/repak" "$C1_REPO/target/release/repak"
"$C1_REPO/target/release/repak" --version
