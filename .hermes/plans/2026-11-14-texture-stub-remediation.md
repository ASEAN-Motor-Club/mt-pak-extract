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
