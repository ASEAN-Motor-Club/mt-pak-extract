#!/usr/bin/env bash
# C1 pipeline stage 0 — resolve every path once.
# Source this file; do not execute it.
#
# Override any value by exporting it before sourcing:
#   PIPE=/path/to/pipeline C1_WORK=/scratch bash run_all.sh

C1_PIPE="${C1_PIPE:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
C1_REPO="${C1_REPO:-$(cd "$C1_PIPE/../.." && pwd)}"
C1_C1="${C1_C1:-$C1_REPO/c1}"
C1_WORK="${C1_WORK:-/opt/data/cache/scratch/c1}"

# tools
UATT_DLL="${UATT_DLL:-$C1_REPO/csharp/UAssetTool/bin/Release/net8.0/UAssetTool.dll}"
DOTNET="${DOTNET:-/opt/data/dotnet10/dotnet}"
MOD_EXPLORE="${MOD_EXPLORE:-$C1_REPO/target/release/mod_explore}"
# repak (compression) lives next to mod_pack/mod_explore so the same binary works
# from the container and from the host; build it with pipeline/make_repak.sh.
REPAK="${REPAK:-$C1_REPO/target/release/repak}"

# desktop (editor / cook side) — reachable through the Windows relay
WIN_PS="${WIN_PS:-/opt/data/scripts/win_ps_file.sh}"
WIN_PUT="${WIN_PUT:-/opt/data/scripts/win_put.sh}"
WIN_GET="${WIN_GET:-/opt/data/scripts/win_get.sh}"
WIN_PROJ="${WIN_PROJ:-D:/UEProjects/C1}"
WIN_MIRROR="${WIN_MIRROR:-D:/C1Mirror}"

# staging host
STAGING="${STAGING:-root@host.docker.internal}"
MT_INSTANCE="${MT_INSTANCE:-motortown-server-c1v2}"

# UAssetTool needs these on .NET 10 or it dies on ICU / framework resolution
export DOTNET_ROLL_FORWARD=Major
export DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1
export TOOL="$UATT_DLL" DOTNET

c1_const() { python3 -c "import json,sys;d=json.load(open('$C1_PIPE/constants.json'));print(d$1)"; }
