# sounder — custom I4 engine with BINKA-encoded custom loops

A complete custom engine row, **Binka 500cc 50hp** (`TestEngine_AMCI4Sounder`), whose exhaust note is three
user-supplied recordings streamed out of the pak. No vanilla asset is modified: our
waves, our cue and our engine asset all live under `/Game/Cars/Parts/Engine/.../AMC/`,
and only the `Engines` DataTable is shared (one pak may own it — see the parent README).

Build: `python3 mods/hams-engines/sounder/build_sounder.py` (env vars in the module
docstring; `VANILLA` is required) for a standalone pak, or let `mods/hams-engines/build.sh`
call it with `SOUNDER_STAGE`/`SOUNDER_BASE_TABLE`/`SOUNDER_NO_PACK=1` so the engine ships
inside the main hams-engines pak as one of its rows.

## What ships

| Pak path | What |
|---|---|
| `Cars/Parts/Engine/Sound/AMC/amc_i4_low` | 6.50 s loop, 96 kHz mono, single chunk |
| `Cars/Parts/Engine/Sound/AMC/amc_i4_mid` | 4.00 s loop, 96 kHz mono, single chunk |
| `Cars/Parts/Engine/Sound/AMC/amc_i4_high` | 3.50 s loop, 96 kHz mono, single chunk |
| `Cars/Parts/Engine/Sound/AMC/SC_AMC_I4Engine` | cue, cloned from `SC_I4SportEngine` |
| `Cars/Parts/Engine/AMC/Test_AMC_I4Sounder` | engine asset, `I4_50HP` clone, cue swapped |
| `DataAsset/VehicleParts/Engines` | base table + `TestEngine_AMCI4Sounder` row |

Row values: display name **Binka 500cc 50hp**, cost 5,000, `PartType Engine`,
`VehicleTypes Small + Pickup`. RowName `TestEngine_AMCI4Sounder` is save identity —
never rename it, only the display `Name`.

## The four rules this cost days to learn

1. **Encode at the vanilla wave's sample rate.** The I4Sport slots use 96 kHz. A
   48 kHz loop plays once and then goes silent at the loop point, on engine off/on,
   and after tabbing out — the audio device reset makes the game re-request the
   streamed wave, and a mismatched-rate wave is not re-served. Resampling fixed the
   loop, the off/on and the tab-out failures simultaneously.
2. **The cue must carry hard package imports for its waves.** Soft paths inside the
   wave-player nodes are not enough for streamed (`.ubulk`) audio; the RB26 pack in
   MoreTuning is the reference — its cue has package imports plus `SoundWave` imports
   whose Outer points at them.
3. **Never override a vanilla streamed wave at its own path.** Ship waves at your own
   package paths or re-request behaviour degrades (originally: total silence after an
   audio-device reset).
4. **The vanilla player order is not low/mid/high.** In `SC_I4SportEngine` player 1 is
   the 1.0k loop (idle layer), player 2 is the 1.6k loop (**high** layer), player 3 is
   the 1.3k loop (**mid** layer). Assigning waves in file order silently swaps the top
   two layers — which is exactly what it sounds like: the wrong clip playing at the
   top of the range.

## Layer map (8500 rpm build)

Four mixer inputs; all pitch maps share one law (1,308 → 11,769 rpm maps to 0.80 → 1.80×)
so the layers agree on pitch at any rpm. Vanilla gives each layer a *different* map
because each vanilla sample was recorded at a different rpm — with our three recordings
that compensation is wrong and the layers fight each other.

| # | Source clip | RPM window | Pitch | Mixer |
|---|---|---|---|---|
| 0 | `amc_i4_low` | idle, out 1,962 → 2,615 | shared law | 1.00 |
| 1 | `amc_i4_mid` | in 2,354 → 2,615, out 5,231 → 9,154 (undertone tail) | shared law | 1.40 |
| 2 | `amc_i4_high` | in 1,569 → 6,538, never out — the bed | shared law | 0.75 |
| 3 | `amc_i4_low` again | in 4,577 → 5,885 — the high section | shared law | 1.25 |

All of those numbers are vanilla's breakpoints scaled by 8500/6500, so the transitions
keep the shape they had at 6500 rpm.

The high layer's vanilla volume map boosted to **5×** at the top of the range; it is
capped at 0.6 → 2.0 here. That boost, not the pitch map, is what made the top end
sound blown out.

## Engine numbers

`MaxRPM 8,500`, `MaxTorque 593,000`, torque curve `TorqueCurve_SmallBlock`, everything
else stock `I4_50HP` (Inertia 1,200, StarterTorque 200,000, IdleThrottle 0.005,
FuelConsumption 90, BlipThrottle 3). Peak **50.0 hp @ ~7,900 rpm**, peak torque
**59.3 Nm @ ~3,480 rpm** — the stock I4 is 51.6 hp @ ~6,040 / 80 Nm, so the extra
2,000 rpm is paid for with torque.

## Audio provenance

`audio/amc_i4_{low,mid,high}.wav` are the owner's own recordings, supplied for this
engine and committed here so the pak is reproducible. They are processed only by
resampling to 96 kHz and BINKA encoding at quality 1 — no EQ, gain, normalisation,
trimming or loop crossfade. The loop seam is the recording's own seam.

Quality 1 is a low setting: measured SNR against the sources is 29.4 dB (low),
31.1 dB (mid), 26.3 dB (high). There is no size pressure at these lengths, so a higher
quality is the obvious next lever if the top end still sounds rough.

`binka/` holds the encoding toolchain: `binka.py` (container writer), `binkaenc.cpp`
and `binkadec.cpp` (thin wrappers over the RAD/UE encoder that ships inside the engine
SDK at `/var/lib/unreal-engine`).

## Known gaps

- Mid and high are still slightly quiet to the owner's ear at mixer 1.40 / 1.25.
- The starter crank is vanilla (`/Game/.../Sound/Starter`), as are `SC_Intake01` and
  `SC_Backfire`. None of them are ours.
- Pak is not published: it is a test build, deliberately in-thread only.
