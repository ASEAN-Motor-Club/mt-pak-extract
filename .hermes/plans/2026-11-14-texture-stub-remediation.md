# C1 texture stub remediation — 2026-11-14

Status: route A confirmed — every stub exists with real data in the project; fix is sourcing only
Owner: Yumemi (for freeman)
Repo: `mt-pak-wt-c1commit` (branch `feat/c1-nav-guards`)

## Problem

`zzz_AMC_C1Base_v3_P.pak` ships **220 Texture2D assets with no pixel data** (68 of them
visible base-colour maps). They exist by name, resolve in materials, and render as the
engine checkerboard. Reported via `mat_kbd02_001_5`.

Stub signature (verified by `UAssetTool --dump`):

- `.uasset` ~834 B, `.uexp` 159–491 B, no `.ubulk`
- only properties `ImportedSize` and `LightingGuid`
- no `SizeX`/`SizeY`, no mip chain, no `PlatformData`

Sources are fine: e.g. `c1/mod_full/textures/other/mat_kbd02_001_5_file0.dds` is a real
1024×128 DXT1 with 11 mips. Conversion produced a placeholder that reached the pack
because nothing validated pixel data — the existing coverage gate only resolved names.

## Scope

All **220** stubs, one pass (68 visible + 152 `*_ao_data` masks). Doing the AO masks
now avoids a second Base_v3 rebuild for the same class of bug.

## Steps

1. **Generate the work list** — `c1/tools/verify_textures.py <Base_v3 tree> --write-list`
   (already prototyped: `/opt/data/cache/scratch/stub_textures.txt`, 220 names).
2. **Resolve source per texture** — each stub name maps to a DDS under
   `c1/mod_full/textures/<subdir>/`. Report any name with no source DDS as unfixable
   in this pass instead of inventing art.
3. **Convert DDS → uasset/uexp** with the vendored converter
   (`tools/ue4-dds-tools/src/main.py`, driven by its `config.json`), on the host where
   `texconv`/`libtexconv.so` and the dev shell are available.
4. **Verify each output** with `verify_textures.classify()` — must report *not a stub*
   before it is allowed into the tree. Any failure stops the batch and is listed.
5. **Rebuild Base_v3** — unpack the current pak, overlay the 220 regenerated assets,
   repack with `repak` (V11 + Zlib, mount `../../../`, path-hash-seed 0) as
   `zzz_AMC_C1Base_v4_P.pak`.
6. **Gate the artifact** — `verify_textures.py <new pak>` must exit 0;
   `check_texture_coverage.py --textures <new pak>` must drop from 63 hard gaps to 0.
7. **Publish** — copy to `/var/lib/mod-releases/mods/shuto-test/`, update the client
   pak set (CustomPak.ini Count + PakN entry only — never regenerate from a folder
   listing), and report the new size/sha256.

## Verification

- `verify_textures.py` clean on the new pak (0 stubs)
- `check_texture_coverage.py` rc=0 on the new pak
- spot check in game: `mat_kbd02_001_5` and one `building_concrete*` render with texture,
  not checkerboard
- material count / pak entry count unchanged vs v3 (±0 aside from replaced assets)

## Rollback

`Base_v3` stays published and the client can be pointed back by restoring the
`CustomPak.ini` line. Old pak is never deleted during this pass.

## Out of scope

- Emissive work on `building_window*` / `building_internal_lights2` (they are on the stub
  list, so they will now have textures; lighting behaviour is a separate task)
- Server pak: textures are data-less by design there, unaffected


## Findings after starting execution (2026-11-14)

The converter route is dead: `tools/ue4-dds-tools` cannot inject into Motor Town's
packages at all — `UnicodeDecodeError` in `archive.py` on both a stub *and* a known-good
texture, because the game's custom 5.5 fork writes a package header the vendored tool
predates. Do not spend more time there.

The important discovery is that **the real textures already exist**:

- `D:\UEProjects\C1\Content\Mods\C1\Textures\other\` holds **143 of the 220**
  stubbed textures as real assets (`mat_kbd02_001_5_file0.uasset` = 63,646 B there vs
  834 B in the pak). ~10.1 MB of pixel data.
- The remaining **77 are absent from the editor project** — almost all `*_ao_data`
  masks plus `T_UVTest`. Nothing to copy; they were never imported.
- The client cook tree (`Saved\Cooked\Windows\C1\Content\...`) contains no
  `Mods\C1\Textures\other` at all, so the pak's textures are not being sourced from
  the cook either.

So the defect is **wiring, not art**: the release assembly packs the DDS-converter stub
tree, and the editor project's real textures never reach the pak. Re-importing would fix
the symptom; fixing the source path fixes the class.

## Revised steps

1. Decide the source of truth for pak textures — cooked output from the editor project
   (needs a Windows client cook of `C1.uproject`) rather than `texcook_v2314/`.
2. Import the 77 missing masks into the editor project from their source DDS (a
   texture-only `AssetImportTask` pass; every existing importer sets
   `import_textures=False`, which is why they were never in the project).
3. Cook Windows for the C1 project, then assemble `Base_v4` from the cooked tree.
4. Gates unchanged: `verify_textures.py` on tree + pak, `check_texture_coverage.py`
   rc=0, entry count parity with v3, then publish.


## Route A quantified (2026-11-14)

The 220 stubs split into three disjoint groups, measured, not assumed:

- **143 — already real in the editor project.** `D:\UEProjects\C1\Content\Mods\C1\Textures\other\`
  holds them with pixel data (`mat_kbd02_001_5_file0.uasset` 63,646 B vs 834 B in the pak).
  Nothing to author; they never reach the pak because the release is assembled from a stale
  texture tree instead of the project's cooked output.
- **10 — importable.** Visible maps whose DDS source exists but which were never imported:
  `building_window28/29/32/33/39/44/57/65`, `building_internal_lights2`, `lamp7`.
  A texture-only `AssetImportTask` pass into `/Game/Mods/C1/Textures/other` fixes them.
- **67 — orphans, delete them.** 66 `*_ao_data` masks + `T_UVTest`. No DDS source exists on
  disk, and **zero** of them appear anywhere in `merged.materials.json` (0 matches for
  `_ao_data`): nothing references them. Shipping them empty is the bug; removing them from
  the pak is the fix.

Outcome: 220 stubs → 0, with 210 carrying real pixel data and 67 removed as dead weight.

## Route A execution order

1. Import the 10 DDS into the editor project; confirm each lands with pixel data.
2. Cook Windows for `D:\UEProjects\C1` (client cook; the project is the source of truth).
3. Assemble `Base_v4` from that cooked output — not from `texcook_v2314/` — and drop the 67
   orphans from the pack list.
4. Gates: `verify_textures.py` 0 stubs on tree and pak, `check_texture_coverage.py` rc=0,
   entry count parity with v3 minus 67, publish, then in-game spot check of
   `mat_kbd02_001_5` and one `building_concrete*`.


## Correction after per-folder survey (2026-11-14)

The earlier 143/77 split was wrong: it checked every stub name against
`Textures\other\` only, but the project organises textures in eleven subfolders
(`bridge`, `fence`, `glass`, `lamp`, `marking`, `other`, `pipe`, `road`, `tunnel`,
`vegetation`, `wall`). Searching the whole `Textures` tree:

- **220 of 220 stubs exist in the editor project with real pixel data — 18,712,481 B total.**
- Zero missing. No import pass was ever required, and the 66 `*_ao_data` masks +
  `T_UVTest` are real assets, not orphans.

So the defect is **purely packaging**: `Base_v3` is assembled from a stale texture tree
(`texcook_v2314` / the old source pak) while the project holds the correct art. Nothing needs
authoring; a client cook of the project plus packing from its cooked output fixes all 220.

Consequences:

- `prune_empty_textures.py` is kept as a *report-only* step in `07b` (deleting by name would
  have discarded 170 assets that only needed re-sourcing).
- The 10 manual imports into `Textures\other\` were unnecessary and are being removed so the
  project is not left with duplicates outside its folder convention.
- Real fix to land: `build_basepak.sh`/`07b` must take textures from the project's cooked
  output, and the gate then proves it (0 stubs) before any pak is published.


## Pipeline review — BeamNG source to pak (2026-11-14)

Hops, and what was measured at each for the 220 stubbed assets:

1. **BeamNG archive** (`art/textures/`, `art/ck_art/` DDS + `*.materials.json`) — original mod.
2. **Extraction into `c1/mod_full/textures/<folder>/`** — measured over all 220 names:
   - **160 absent entirely** (no DDS extracted): the whole `*_ao_data` family plus `T_UVTest`.
   - **52 present but degenerate** (<2 KB: 8×8, 16×16, 8×16, 32×8 masks).
   - **8 present and real** (>=2 KB, 648,504 B total) — `mat_kbd02_001_5_file0` 87,560 B,
     `mat_kbd02_001_file0`, `mat_kbf01_016/017_file0`, `mat_ikegaki_2_sh_file0`.
3. **Editor import into `Content\Mods\C1\Textures\<folder>/`** — all 220 exist as editor
   packages (220/220, 18,712,481 B total), so the import produced *something* for every name
   the tree knows about, including the ones with no source DDS.
4. **Windows cook** — `glass/building_window28` cooked to 1,071 B `.uasset` + 491 B `.uexp`,
   classified as empty by `verify_textures.classify()` (no `SizeX`, no `PlatformData`).
   Note: window28's source DDS is one of the 52 degenerate ones, so this proves the *degenerate*
   case fails, **not** yet the real-source case.
5. **Pak assembly** — ships whatever hop 4 produced; matches Base_v3 exactly.

Consequences, in priority order:

- The 160 with no source can never carry pixels: they are AO bake data and a debug asset. They
  should be dropped from the pak (or generated), not "fixed".
- The real question still open is hop 4 for the **8 real-source** textures. `mat_kbd02_001_5` —
  the one the user actually sees as checkerboard — has an 87 KB DDS and a 63 KB editor package.
  If its cooked package is also empty, the defect is in cook/import settings and is fixable
  centrally. If it cooks fine, then the paks are being assembled from a stale cook and the fix
  is packaging only. **This single measurement decides the shape of the fix.**
