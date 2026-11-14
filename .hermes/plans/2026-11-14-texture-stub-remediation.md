# C1 texture stub remediation — 2026-11-14

Status: investigating (re-import route blocked, source-of-truth route found)
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
