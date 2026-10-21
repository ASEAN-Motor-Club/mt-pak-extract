# Custom Engine Audio (AMC EngineSound) — Status & Findings

Goal: replace the I4 50HP engine sound with custom audio recorded by Hamster
(idle/low/high loops layered from a recording + a 2-stroke reference clip).

## Status: blocked on wave-format acceptance

Every structural piece of the mod pipeline is proven working by pak bisect
tests (T-series below). The single missing link is the runtime **audio codec**
for custom wave data.

## What works (proven by in-game bisects)

| Test | Pak content | Result |
|---|---|---|
| T4b/T5 | I4_50HP DataAsset override → `SC_Backfire` cue (one-shot) | **Plays** — override mechanism works |
| T7 | Pristine vanilla wave re-shipped at its original path | **Plays** — wave pak-override works |
| T9 | Renamed clone of a vanilla wave at the original path | **Plays** — rename/clone of waves works |
| T11 | Same paths, payload re-tagged raw PCM | Silent — PCM rejected |
| T12 | Same paths, payload Vorbis (OGG) | Silent — our OGG wrapper rejected |

Notes:
- The engine DataAsset override (`EnginesSound` → cloned cue) loads fine **only
  when no import entries are appended**; appended imports on this asset break
  loading (T4b/T5 vs earlier tests were confounded — final attribution above).
- Vanilla `SC_I4SportEngine` is shared by I4_50HP / I4_90HP / I4Sport_150HP;
  a cue-path override therefore affects all three. 50HP-only isolation needs a
  per-engine DataAsset (mechanism works, see import-append caveat).

## The codec wall

- Every vanilla `SoundWave` in MotorTown is **BINKA** (RAD Bink Audio) —
  proprietary, no public encoder exists.
- Cooked shipping builds do not ship a raw-PCM decoder path (T11 silent).
- Vorbis exists in the shipping exe (`findstr` hit) but our ffmpeg-encoded OGG
  payload is rejected (T12) — likely the engine expects its own cooked Vorbis
  layout (UE's `FSoundWaveData`-style header/metadata around the OGG stream),
  not a bare `.ogg`.
- ADPCM (Microsoft/UE variant) is compiled into the exe and is the most likely
  workable format; UE5's ADPCM uses fixed blocks (header + packed nibbles).
  Requires writing an encoder that matches UE's block layout exactly.

## Audio content (done, user-approved by ear)

Built with ffmpeg (+ Rubber Band for stretch, equal-power crossfades for
looping) from Hamster's recordings:

- **Idle** = `ham_idle_plus_low_lp.wav` (4.0s) — idle loop + low-passed (250 Hz)
  pops layer underneath
- **Low/mid** = `ham_low_plus_mid_lp.wav` (6.5s) — pops/low layer on top +
  low-passed 2-stroke mid loop underneath
- **High** = `ham2s_high_plus_low.wav` (3.5s) — steady-160Hz-core 2-stroke
  scream (surge-flattened) + pops layer underneath

Layer recipe (validated by ear): full-band character loop on top + low-passed
250 Hz support layer underneath, normalized, seam-crossfaded.

## Tooling built (worktree `mt-pak-extract-wt-0719`, uncommitted)

- `csharp/UAssetTool/Program.cs`: occurrence-based export matching
  (`match_occurrence`) — cooked UE5.5 exports share bare names (e.g. three
  exports all named `SoundNodeWavePlayer`), so refs must be patched by index.
- `wavebuild/Test/Program.cs` (scratch): wave cloner that overrides a vanilla
  wave at its original path with a new payload — patches tagged props
  (SampleRate/TotalSamples/Duration), the inline `ABEU` blob (sample rate +
  total samples), trailing bulk-size fields, and DataResources; codec name and
  payload are parameterized (`keep|OGG|PCM`, samples arg for compressed input).

## Next steps

1. Write an IMA/UE-ADPCM encoder matching UE5's block format, ship as T13.
2. If ADPCM plays: wire the full custom set (waves → cloned cue → DataAsset
   override), then narrow to I4_50HP only.
3. Fallback if nothing but BINKA plays: investigate BINKA container structure
   for a possible passthrough encoder (long shot, no public tooling).
