#!/usr/bin/env bash
# Wait for frontend, open C1Full, then probe the live material instance.
set -u
BR=/opt/data/skills/modding/ue4ss-remote-dev-bridge/scripts/uebridge.sh
E=/opt/data/cache/scratch/emis
sleep "${1:-15}"
echo "=== OPEN LEVEL"
timeout 60 bash "$BR" "$E/open_level.lua" 2>&1 | tail -4
echo "=== WAIT LOAD"
sleep "${2:-50}"
echo "=== PROBE"
timeout 60 bash "$BR" "$E/probe_mat.lua" 2>&1 | tail -12
echo "=== AUTOLOAD_DONE"
