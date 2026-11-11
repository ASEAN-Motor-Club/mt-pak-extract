#!/usr/bin/env bash
# Verify a COOKED C1Full asset tree: the artifact that ships, not the editor's memory.
#
#   verify_cooked.sh <cooked-root> [slotmap.json] [report.json]
#
# <cooked-root> must contain Meshes/ and Meshes_NoCollision/. Checks:
#   * every asset has material slots at all
#   * no slot is left on WorldGridMaterial (that is an unbound slot, i.e. invisible)
#   * NC assets: every slot is bound
#   * cells: slot count and bound count match slotmap.json exactly
# Exit 0 = clean, 1 = problems (printed, and listed in the report if given).
#
# UAssetTool resolves Mappings.usmap as ../.. from its CWD, so it has to run from a
# directory exactly two levels below the repo root -- hence the cd into .uatt_run/w.
set -euo pipefail

ROOT="${1:?usage: verify_cooked.sh <cooked-root> [slotmap.json] [report.json]}"
SLOTMAP="${2:-}"
REPORT="${3:-$(mktemp)}"

REPO="${C1_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
TOOL="${TOOL:-$REPO/csharp/UAssetTool/bin/Release/net8.0/UAssetTool.dll}"
DOTNET="${DOTNET:-/opt/data/dotnet10/dotnet}"

[ -f "$TOOL" ] || { echo "FAIL: UAssetTool not built at $TOOL" >&2; exit 2; }

export DOTNET_ROLL_FORWARD=Major
export DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1

RUN="$REPO/.uatt_run/w"
mkdir -p "$RUN"
cd "$RUN"

set +e
"$DOTNET" "$TOOL" --verify-mesh-pak "$ROOT" "$SLOTMAP" "$REPORT"
rc=$?
set -e

if [ "$rc" -ne 0 ]; then
    echo "  report: $REPORT" >&2
fi
exit "$rc"
