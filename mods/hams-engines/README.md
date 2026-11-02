# hams-engines — all custom engines in ONE pak

Supersedes the separate `engine-13b-v6-test` and `engine-330-kart` paks, which each
shipped their own copy of the vanilla `Engines` DataTable and therefore deleted each
other's rows at load time (only one pak can own a DataTable; the last to load wins
silently).

One table = vanilla 36 rows + 4 custom rows = **40**:

| Row | Menu label | What it is |
|---|---|---|
| `TestEngine_13bV6` | **Hams Rotary 180HP** | rotary idle bed + V6Sport low/high + 26B brap (9000 rpm) |
| `TestEngine_330Kart` | **Test 330 Kart** | MediumDuty 330 diesel with the kart 10HP chainsaw layered under it (3500 rpm) |
| `TestEngine_Thumper` | **Test Thumper** | 1,800 rpm lugger, 3,000 Nm @ 756 |
| `TestEngine_AMCI4Sounder` | **Binka 500cc 50hp** | own BINKA-encoded loops, 8500 rpm, 50.0 hp @ ~7900 (see `sounder/`) |

The **HD TDI V-Twin** was removed from this pak on the owner's request (its configs
remain in the repo, unbuilt).

Built by `build.sh`; the sounder section is driven by `sounder/build_sounder.py`, which
stages its waves/cue/engine into the same pak stage and appends its row to the table.

## Pak contents (16 files)

| Pak path | What |
|---|---|
| `DataAsset/VehicleParts/Engines` | vanilla 0.7.19 table + both rows |
| `Cars/Parts/Engine/Test_13bV6_180HP` | rotary hybrid engine asset |
| `Cars/Parts/Engine/Test_330Kart_330HP` | 330/2-stroke hybrid engine asset |
| `Cars/Parts/Engine/Sound/13bV8/SC_V8Engine` | rotary hybrid cue (V8 host, 26B layer added) |
| `Cars/Parts/Engine/Sound/13b/idle`, `26b/idle` | third-party rotary loops (MoreTuning), shipped inside |
| `Cars/Parts/Engine/Sound/MediumDuty330_Kart/SC_Truck_02` | 330/2-stroke hybrid cue (truck host, 4 mixer inputs) |

## Row names are save identity

`TestEngine_13bV6` was deliberately **not** renamed when the label became
"Hams Rotary 180HP" — the RowName is what a save stores for a fitted engine.
Only the menu text changed. Same for `TestEngine_330Kart`.

## Build

```bash
nix develop --command bash -c '
MAPPINGS=versions/v0.7.19/Mappings.usmap \
MODPACK_LD=$(echo $LIBRARY_PATH | tr : "\n" | sed "s|$|/lib|" | tr "\n" :) \
bash mods/hams-engines/build.sh \
  --out versions/v0.7.19/out \
  --mt  /path/to/moretuning-extracted/mod_out \
  --output mods/hams-engines/builds/zzz_AMC_HamsEngines_v0.2.0_0.7.19_P.pak'
```

`--out` needs `SC_V8Engine`, `SC_Truck_02`, `FordSmalBlock302_V8_5L_180HP`,
`MediumDuty_250HP` and `Engines`. `--mt` supplies the two rotary idle loops (not
committed). Absolute paths only — UAssetTool/cuepatch run with their own cwd.

## Notes

- Only one `Engines`-table pak may sit in `Paks`. MoreTuning's engine rows are *not*
  merged here, so installing both still collides.
- Rebuild after any game version bump — the table and every wave reference are
  version-specific.

## Naming rule (standing, set 2026-11-01)

The owner wants these engines flagged as TEST until further notice: menu labels are
`Test Dorito 250` and `Test Diesel Two Stroke 340`, the pak is
`zzz_AMC_HamsEngines_Test_v<ver>_0.7.19_P.pak`. Keep the `zzz_` prefix (load order,
not branding). Do not drop the Test flag on a rebuild unless explicitly told to —
the owner has unreleased plans for these engines.
