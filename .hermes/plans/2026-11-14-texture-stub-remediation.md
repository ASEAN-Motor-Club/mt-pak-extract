# C1 texture stub remediation — plan

Status: blocked on one measurement (see "Decisive measurement"); gates already landed
Owner: Yumemi (for freeman)
Repo: `mt-pak-wt-c1commit`, branch `feat/c1-nav-guards`

## Problem

`zzz_AMC_C1Base_v3_P.pak` ships **220 Texture2D assets with no pixel data**. Materials
referencing them (reported via `mat_kbd02_001_5`) render as the engine checkerboard.

Stub signature, verified by `UAssetTool --dump` and by `verify_textures.classify()`:

- `.uasset` ~834 B, `.uexp` 159–491 B, no `.ubulk`
- only properties `ImportedSize` and `LightingGuid`; **no `SizeX`, no `PlatformData`, no mips**

## Pipeline review — measured at every hop

1. **BeamNG original mod** — `art/textures/`, `art/ck_art/` DDS + `*.materials.json`
   (1,643 definitions). The only real source of pixel data.
2. **Extraction into `c1/mod_full/textures/<folder>/`** — over the 220 stub names:
   - **160 absent entirely** (no DDS): the whole `*_ao_data` family + `T_UVTest`
   - **52 present but degenerate** (<2 KB: 8×8, 16×16, 8×16, 32×8 masks)
   - **8 present and real** (>=2 KB, 648,504 B total), incl. `mat_kbd02_001_5_file0` 87,560 B
3. **Editor import into `Content\Mods\C1\Textures\<folder>/`** — 220/220 exist as editor
   packages (18,712,481 B total), including the 160 with no source. The importer created an
   asset for every name in the list whether or not art existed.
4. **Windows cook** — `glass/building_window28` cooked to 1,071 B `.uasset` + 491 B `.uexp`;
   classified **empty** (no `SizeX`, no `PlatformData`). That asset is one of the 52
   *degenerate* sources, so this proves the degenerate case, not the class.
5. **Pak assembly** — ships whatever the cook produced; matches Base_v3 exactly.

## Decisive measurement (next action)

Cook `mat_kbd02_001_5` and classify the output. It is the reported checkerboard, it has a real
87 KB DDS and a 63 KB editor package, so it is the only asset that separates the two possible
root causes:

- **cooked output empty** → import/cook settings are dropping pixel data; the class is
  recoverable centrally, and the fix is an import-settings change plus rebuild.
- **cooked output real** → the paks are assembled from a stale cook; the fix is packaging
  only (assemble Base_v4 from the current cooked tree).

Do not plan remediation detail beyond this point until it is answered.

## Remediation by group (independent of the measurement)

- **160 no-source assets** — unrecoverable as pixels. Drop them from the pak, or generate AO
  if the shading needs it. "Re-import" is not an option; there is no art.
- **52 degenerate masks** — 8–32 px. If the cook drops them, test one asset with explicit
  import settings (no mip generation, compression off) before writing off the group.
- **8 real-source textures** — `mat_kbd02_001_5`, `mat_kbd02_001`, `mat_kbf01_016`,
  `mat_kbf01_017`, `mat_ikegaki_2_sh`, plus three others: expect these to work once the root
  cause is fixed; they are the acceptance test for the fix.

## Gates already landed (done, verified)

- `c1/tools/verify_textures.py` — tree/pak scanner, hard-fails on data-less Texture2D,
  `--write-list` emits a work list, server paks auto-detected and skipped.
- `c1/tools/check_texture_coverage.py` — a resolved-but-empty asset now counts as an
  `EMPTY-ASSET` hard gap; verified against the shipped pak (63 hard gaps, rc=1).
- `c1/tools/prune_empty_textures.py` — **report-only** in `07b`; deleting by name would have
  discarded 170 assets that only need re-sourcing.
- `pipeline/07b_build_release_paks.sh` — orphan report + texture gate on the client tree
  before packing; `pipeline/09_verify.sh` — same gate on any client pak.
- `c1/docs/C1_PIPELINE.md` — stub signature documented with the three checkpoints.

Net effect: **a build can no longer ship this silently.** That part of "permanent" is done.

## Not to be repeated

- `tools/ue4-dds-tools` cannot inject into Motor Town packages (`UnicodeDecodeError` in
  `archive.py` on stubs and on known-good textures alike). Don't retry it.
- Don't judge a texture by file size — a cooked 16×16 mask is legitimately ~1 KB. Run
  `classify()`.
- Don't mass-import into `Textures\other\`: all 220 names live in their proper subfolders
  (`glass`, `lamp`, `bridge`, …). The 10 throwaway imports made during this investigation were
  removed.

## Rollback

`Base_v3` stays published; the client can be pointed back by restoring its `CustomPak.ini`
line. No pak is deleted during remediation.

---

# Revision — 2026-11-14 (after the PIL/PNG experiments)

## Where the numbers really stand

| stage | result |
|---|---|
| stubs in `Base_v3` | 220 |
| fixed by overlaying the **current** cooked output (166 assets, 25,022,890 B) | 165 |
| `t_asphalt_old_b_color` fixed separately (cooked 1,392,640 B `.ubulk`) | +1 |
| **remaining** | **54** |
| of the 54: DDS present in `c1_src.zip` | 52 (all 8–32 px) |
| of the 54: no DDS by name (even with suffix fallback) | 2 — `mat_jimen_01_color`, `mat_jimen_02_color` |

## The 54 — what has been tried, and what it did *not* prove

1. Re-imported the 52 from archive **DDS** into their real folders (`other`, `glass`, `lamp`):
   `TEX52 done 52/52`, saved, rc=0. Cook still reported `uexp=491 ubulk=0`.
2. Re-imported the same 52 as **PNG** (PIL reads the archive DDS fine — proven, 52/52 converted;
   this is the EMISSIVE doc's own extraction path). `TEX52 done 52/52`, saved, rc=0. Cook
   reported the **byte-identical** `1077/491/0`.

**Neither result is evidence yet.** The cooked files were not checked for `LastWriteTime`, and the
byte-identical output is exactly what stale files look like. Do not plan the next fix on top of
"PNG import doesn't work" — that claim is unsupported.

## Next actions, strictly in this order

1. **Timestamp check.** Read `LastWriteTime` on
   `Saved\Cooked\Windows\C1\Content\Mods\C1\Textures\other\building_concrete13.*` and compare with the
   cook start time. If older, the cook is not rewriting them and both experiments above are void.
2. If the cook *is* rewriting them and they stay 491 B: measure the imported **editor** asset properly —
   does it contain `SizeX` / a mip chain at all? That distinguishes "import silently failed" from
   "cook drops tiny textures". Use `UAssetTool --dump` on the editor package, not file sizes.
3. Only then choose: fix import settings (compression / mip generation / legacy importer) or re-source.
4. `mat_jimen_01_color` / `mat_jimen_02_color`: resolve by scanning the archive for `mat_jimen*` —
   if the sheets genuinely do not exist, they join the "author or drop" group.

## Rule carried forward

Anything measured from a cook must be timestamped against that cook. Two runs produced identical
bytes and I nearly reported that as a result.

---

# Emissive — corrections for `emissive_materials.py`

Source of truth: `docs/c1-shuto/EMISSIVE_MATERIALS.md` (in `mt-pak-extract-wt-0719`). The script does
not exist yet in `c1/tools/`; when written it must follow these, all of which the doc establishes and
`c1/source/merged.materials.json` gets wrong:

1. **Authority is `/opt/data/inbox/c1src/c1_src.zip`**, not the ported UE table. 16 `*.materials.json`,
   1,643 definitions, keyed by *definition* name and reached through `mapTo`. Resolve `mapTo` first or
   a minority of materials silently census as empty (e.g. `mat_road_01`).
2. **Read stage 0 only.** Fields that matter: `emissiveMap`, `emissive: true`, `emissiveFactor`
   (HDR colour, 1.0–16.06, no scalar strength), `sequenceSegmentSize` + `animFlags 16` (flipbook),
   `instanceEmissive`.
3. **`scalars.EmissiveStrength` in the UE table is a decoy** — `1.0` everywhere, always. Never read it.
4. **Ship filter, not "all 183".** Of 183 declared emitters, 65 with a real `emissiveMap` ship as-is;
   of the 118 self-emissive, keep only those whose colour map is dark (**mean ≤ 0.30**) or that carry
   an explicit HDR tint (`emissiveFactor` max > 1.5) — that keeps 27 and drops 91. Total **92**.
   Dropping the bright ones is the fix for "whole facades turned into lamps", not a regression.
5. **Two drawing paths:** `emissiveMap` materials take their own rect in the packed atlas; the 27
   sentinel materials reuse the albedo texel already sampled (`clamp(texel.rgb*2.0,0,1)` because the
   albedo atlas is stored at 0.5×). Sentinels cost no atlas space — do not allocate cells for them.
6. **Texture extraction: PIL from the archive**, case-insensitively (`_file0EM.dds` vs lowercase).
   Verified working in this container: PIL 12.3.0 reads BC1/BC2/BC3 DDS. The `mat_daisi_*` /
   `mat_singou_*` sheets were never extracted by the port and exist **only** in the archive.
7. **Exclusions:** `emissiveFactor` at `1e-06` (BeamNG's "dead" marker, e.g. `lamp1_tunnel`) and
   definitions never ported (`godray_emitter`, `thunderbolt`).
8. **Intensity per material** from `emissiveFactor`, Reinhard-compressed (`em/(1+em)`), with
   `emisGainUniform` (default 1.2) as the global level. A single white multiplier inverts the ordering
   — it overdrives the glass pages and flattens the tower/signals.

### Validation gates for the script

- dry-run must report `186 MIs / 154 opaque / 32 skipped_masked / 66 with map / 120 no-map / 69 factor`
  (the contract from the earlier session) and the same 8 unresolved maps;
- emitted set must be **92**, matching the doc's count; a different number is a bug in the filter;
- every shipped material must trace to an archive definition — print the `mapTo` key next to it;
- no material may take both an atlas rect and the sentinel path.

### Still unresolved from the doc

The doc describes the **web viewer** (`site/emis.png` + `emis.json`), not the UE material path. Whether
the engine side should ship emissive as MIs on `M_PolygonMaster` or as a packed atlas + one master is an
open decision: the atlas path is proven in the viewer, the MI path is unproven (`Use_Emissive` spike
never confirmed in-game). Do not assume the viewer's numbers transfer to the shipped pak.
