# engine-13b-v6-test — "Test" rotary engine part

A self-contained engine **parts** pack: one engine row, its `MHEngineDataAsset`, and a
custom `SoundCue` that layers a rotating-engine idle bed under the V6 samples. No other
mod is required — the only third-party content is the audio it ships inside itself.

In game it appears in the engine list as **Test** (row `TestEngine_13bV6`).

## What it contains

| Pak path | What |
|---|---|
| `DataAsset/VehicleParts/Engines` | **vanilla** 0.7.19 table (36 rows) + `TestEngine_13bV6` = 37 |
| `Cars/Parts/Engine/Test_13bV6_180HP` | engine asset: rotary-style rpm ceiling/idle/blip numbers, cue repointed |
| `Cars/Parts/Engine/Sound/13bV8/SC_V8Engine` | the cue, built from the vanilla V8 cue |
| `Cars/Parts/Engine/Sound/13b/idle` | 13B idle loop (third-party audio, see notes) |
| `Cars/Parts/Engine/Sound/26b/idle` | 26B idle loop (third-party audio, see notes) |

## Cue graph

Built from the vanilla `SC_V8Engine`, in three layers:

- **idle**: `13b/idle` wave player (was the V8 `idling_and_turnover`) through
  `SoundNodeParamCrossFade` on **RPM**, fading out 8000 → 11000.
- **low / high**: vanilla V8 loops replaced by the V6Sport samples
  (`3000rpm_Engine`, `5320rpm_Engine`), keeping the vanilla crossfade scaffolding.
- **26B brap layer** (added by this mod): a fourth mixer input —
  `26b/idle` wave player → `SoundNodeParamCrossFade` on **RPM** with
  fade-in 10/10 and **fade-out 1600 → 2200**, mixer volume 0.9. It is at full
  volume through idle (~1500 rpm) and gone above ~2200, so the 26B "brap"
  texture only exists off-throttle at idle.

Pitch: the idle modulator runs 900 → 9000 rpm → 0.55× → 2.6×.

## Engine numbers

Copied from the 13B rotor (`13b.uasset`), and only the sound-relevant ones —
`MaxRPM 9000`, `IdleThrottle 0.0017`, `BlipThrottle 10`, `BlipDurationSeconds 1.0`,
`AfterFireProbability 1.0`. Inertia, friction, `MaxTorque`, `StarterTorque` and the
torque curve stay at the 180HP V8 values, so it **drives** like the V8 and **sounds**
like the rotor.

`BlipDurationSeconds` matters: it is absent from the V8 donor, defaults to 0, and
`BlipThrottle` does nothing at 0 — the idle never blips.

## Build

Third-party audio is **not committed**. Point the builder at an extracted MoreTuning
copy and at extracted vanilla assets for the target version:

```bash
nix develop --command bash -c '
MAPPINGS=versions/v0.7.19/Mappings.usmap \
MODPACK_LD=$(echo $LIBRARY_PATH | tr : "\n" | sed "s|$|/lib|" | tr "\n" :) \
bash mods/engine-13b-v6-test/build.sh \
  --out versions/v0.7.19/out \
  --mt  /path/to/moretuning-extracted/mod_out \
  --output mods/engine-13b-v6-test/builds/zzz_ASEAN_TestEngine_v0.1.0_0.7.19_P.pak'
```

`build.sh` needs the `csharp/UAssetAPI` submodule initialised (`git submodule update --init`).
It runs, in order: clone cue → repoint idle → V6 swaps → add 26B layer → widen pitch →
clone engine asset → apply rotor numbers → add table row → `mod_pack`.

`scripts/mods.py build` does **not** drive this mod yet — there is no
`create_enginepack.py`, only `build.sh`.

## Notes / constraints

- **The pak owns the `Engines` DataTable.** Only one pak can own it at runtime and
  the last one to load wins silently, so this pack conflicts with MoreTuning or any
  other engine-table mod unless their rows are merged in at build time. The shipped
  table is the vanilla one on purpose: no external mod is required, and no rows point
  into another mod's assets.
- **`TestEngine_13bV6` is the item identity in saves.** Renaming the row orphans
  already-fitted engines.
- The two idle loops are third-party mod audio and live only in the built pak; they
  are not part of this repo.
- Rebuild after any game version bump — the table and the donor assets are
  version-specific.
