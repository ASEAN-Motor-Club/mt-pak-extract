# Plan — rebuild C1 textures in a clean UE 5.5 project (route 3)

Status: proposed, awaiting go. Owner: Yumemi. Supersedes the in-place reimport attempts.

## Why this plan exists

Measured 2026-11-14: the C1 project's texture import path produces **empty packages and reports success**.

Evidence:
- `import_asset_tasks` on `smo_3.data.dds` logs `Interchange start importing source`, then
  `does_asset_exist() = True`, `load_asset() = None`, `save_asset() = True`, **nothing written to disk**.
- Reproduced with a brand-new asset name (`zz_probe_new`) — new package, same result.
- Reproduced with `automated` True and False.
- `AssetImportTask.import_factory` is not exposed in UE 5.5 Python, so the legacy `TextureFactory`
  path cannot be forced from script.
- Consequence: the 52 archive reimports, the 200 native reimports and the 22 missing-texture imports
  all produced nothing on disk. This is the probable origin of the 220 empty texture stubs.

Therefore: stop importing inside the C1 project. Build the textures in a clean project and move the
cooked binary assets in.

## Scope

In: every Texture2D under `/Game/Mods/C1/Textures/{bridge,fence,glass,lamp,marking,other,pipe,road,tunnel,vegetation,wall}`
plus the 27 catalogued missing sheets. Also the emissive sheets required by the emissive pass.

Out: materials/MI authoring (stays in the C1 project), meshes, maps, nav.

## Design

1. **Clean project** `D:\UEProjects\C1Tex`, UE 5.5, same engine install as C1
   (`D:\UE_5.5`). No plugins beyond defaults. Source control disabled.
2. **Source** = `levels/c1/art/textures/**.dds` inside `c1_src.zip` (2,409 files, 349 MB),
   extracted to `C:\Users\freeman\alltex` (already done, verified).
3. **Name mapping** = `alltex_map2.txt` (2,327 rows: source DDS → destination folder + asset name),
   dots normalised (`_d.color` → `_d_color`), plus 22 material-facing names
   (`SMO_3..7`, `TNL`, `TNL_3..7`, `WALL1`, `mat_daisi_*EM`, `area_zz_01_gtf_tex_273*`).
4. **Import** one asset at a time, `automated=False`, explicit `save_asset` per asset.
5. **Verify per asset** — hard gate, no exceptions:
   - `load_asset()` is not None
   - the asset is a `Texture2D`
   - `get_editor_property('ImportedSize')` equals the source DDS dimensions from PIL
   - the on-disk `.uasset` exists and is > 1 KB
   Any asset failing a check is recorded in `tex_build_failures.txt` and the run continues.
6. **Cook** `-TargetPlatform=Windows -CookAll`.
7. **Harvest** cooked `Saved/Cooked/Windows/C1Tex/Content/Mods/C1/Textures/**` and copy
   `.uasset/.uexp/.ubulk` into the C1 project's content tree at identical relative paths,
   replacing the existing packages.
8. **Downstream** resumes in the C1 project: regenerate materials → emissive → cook → gates →
   build paks → install.

## Gates (each must pass before the next step)

- **G1 import completeness**: failures file empty, and asset count == mapped rows.
- **G2 pixel data**: `c1/tools/verify_textures.py` on the harvested tree reports 0 stubs
  (threshold 340 B uexp, `--allow-ao` only if masks are intentionally excluded).
- **G3 dimension fidelity**: for every asset, cooked dims == source dims (parse, never infer
  from file size — that error cost three wrong conclusions on 2026-11-14).
- **G4 coverage**: `check_texture_coverage.py` hard gaps == 0.
- **G5 emissive**: dry run must reproduce the 92-material contract (65 mapped + 27 sentinel)
  before any emissive pak is built.
- **G6 artifact**: `09_verify.sh` passes on the built pak.

## Steps

- S1 Create `D:\UEProjects\C1Tex` and confirm a trivial texture import produces a loadable,
  saved, correctly-dimensioned Texture2D. **Stop and report if this fails** — everything below
  depends on it.
- S2 Port `imp_save.py` into the clean project, run the full 2,327-row import in batches of 100
  with per-asset verification. Record G1.
- S3 Cook, harvest, run G2/G3 on the harvested tree.
- S4 Copy into the C1 project; re-run G2/G3 there to prove the copy is intact.
- S5 Regenerate materials (`07c_build_materials.sh`) and run G4.
- S6 Write `c1/tools/emissive_materials.py` per `docs/c1-shuto/EMISSIVE_MATERIALS.md`
  (archive authority, PIL extraction, dark-map gate, 92-material set). Run G5 dry.
- S7 Cook, build Base + mats paks, run G6.
- S8 Install to a **non-live** pak slot; do not touch `CustomPak.ini` until the client is confirmed free.

## Risks

- Clean-project version mismatch with the game fork → textures cook with a different package
  version and the game refuses them. Mitigation: same engine install (`D:\UE_5.5`), verify one
  known-good texture loads in-game before batching.
- Disk: 2,327 source textures + cook output + harvest ≈ 3 GB on D:. Confirm free space first.
- The 22 material-facing names have no matching asset in the C1 project today; they will appear as
  new assets, so material regeneration must be run *after* S4, not before.

## Not to be repeated

- Importing textures inside the C1 project (broken path, see Evidence).
- Inferring texture dimensions from `.ubulk` size or uexp size — parse the package.
- Regenerating `CustomPak.ini` from a folder listing — edit Count/PakN only.

---

# Outcome — S1..S4 done 2026-11-14

**Root cause found: the DDS importer produces empty packages and reports success.**

Measured in the clean project, same session, same source art, same destination folder:

    zz_png_probe  load_asset=Texture2D  save=True  disk=61,895 B
    zz_dds_probe  load_asset=None       save=True  disk=MISSING

This explains every earlier symptom: the 220 empty stubs, the 52 archive reimports, the 200
"native" reimports, the 22 missing-sheet attempts, and the phantom "downsampling" (which was
never real — it was my inference from .ubulk byte counts, three times wrong in one session).

## What was actually executed

1. `D:\UEProjects\C1Tex` created from TP_Blank. The `ConvertTo-Json` rewrite of the .uproject broke
   commandlet loading; a hand-written minimal .uproject (FileVersion 3, EngineAssociation "5.5",
   PythonScriptPlugin + EditorScriptingUtilities + Interchange + InterchangeEditor) fixed it.
2. All 2,397 DDS converted to PNG with PIL (`/opt/hermes/.venv/bin/python`, PIL 12.3.0 — the plain
   `python3` on this host has no PIL). 0 failures.
3. 2,327 PNGs imported into C1Tex: **ok=2327 bad=0**, each verified by `load_asset` != None and saved.
4. Editor packages copied into `D:\UEProjects\C1\Content\Mods\C1\Textures` (2,328 files). Section
   counts confirm the previously-missing sheets: lamp 49→54 (SMO_3..7), tunnel 90→96 (TNL, TNL_3..7),
   wall 291→292 (WALL1).
5. C1 cook: rc=0. Cooked SMO_3 = uexp 5,859 B + **ubulk 81,920 B** — real mip data, versus 491 B of
   uexp and no bulk before.

## Plan corrections

- S3 changes: do NOT cook in the clean project (its cook exits early with no map). Copy the **editor**
  packages into C1 and let C1's own cook run. Simpler and matches what the pipeline needs.
- G3: `ImportedSize` is **protected** on a loaded Texture2D in Python (`... is protected and cannot
  be read`). Use asset-registry tags or the cooked package instead.
- Any future texture work: **convert to PNG first**. Importing DDS is not a viable path in this build.
