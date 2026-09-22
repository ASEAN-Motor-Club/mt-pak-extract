#!/usr/bin/env bash
# Build schedule-i with the proven mixed-provenance template set (b1):
#   client pak:  delivery point assets + SmallBox/VolumeTypeCargo cargo BPs
#   server pak:  Cargos composite, Cargos_ScheduleI child, Items_Furnitures,
#                Buildings_Furnitures tables
# Both 0.7.19 paks must be present and MotorTown-Windows.pak symlinked to the
# client one when refreshing out/client (the extractor reads the symlink).
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
rm -rf out/mixb1
mkdir -p out/mixb1
cp out/client/*.uasset out/client/*.uexp out/mixb1/
for f in Cargos Cargos_Deprecated Items_Furnitures Buildings_Furnitures; do
  cp out/server/$f.uasset out/server/$f.uexp out/mixb1/
done
nix develop -c bash -c "export DOTNET_ROOT=$(dirname $(readlink -f $(which dotnet))); export PATH=$DOTNET_ROOT:$PATH; python3 scripts/create_cargopack.py --mod mods/schedule-i --config mods/schedule-i/cargo_entries.json --recipes mods/schedule-i/recipe_entries.json --output mods/schedule-i/builds/x.pak --template-root out/mixb1"
mv mods/schedule-i/builds/Schedule_I_v0.4.20_0.7.19_P.pak "mods/schedule-i/builds/Schedule_I_v${SCHEDULE_I_VERSION:-0.4.20}-b1_0.7.19_P.pak"
