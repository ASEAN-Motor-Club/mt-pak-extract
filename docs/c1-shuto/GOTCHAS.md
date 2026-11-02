# C1 Shuto map — gotchas, root causes and fixes

Running log of every trap hit while porting the BeamNG C1 Shuto corridor into Motor
Town (UE 5.5.4) as a modded map. Each entry: **symptom → root cause → fix**, with
the measurement that proved it where one exists. Add to this instead of
re-deriving.

Toolchain paths
- Cook host: `D:\UEProjects\C1` (Win64, UE 5.5.4 at `D:\UE_5.5`)
- Level/asset patcher: `mt-pak-extract-wt-0719/csharp/UMapPatch`
- Scratch work: `/opt/data/cache/scratch/c1`
- Client paks: `D:\SteamLibrary\steamapps\common\Motor Town\MotorTown\Content\Paks`

---

## 1. OBJ units are metres; Unreal imports OBJ as centimetres

**Symptom:** map loads, world is empty/black, player falls forever.
**Cause:** cell OBJs are authored in metres (a 500 m tile spans ~520 units).
`FbxImportUI` defaults to `import_uniform_scale = 1.0`, so a 520-unit tile
becomes 520 cm — a 5.2 m diorama, invisible from spawn.
**Fix:** `static_mesh_import_data.import_uniform_scale = 100.0` in `import_win.py`.
**Verified by:** imported sample `c-1_10` bounds `[20944.5, 16080.9, 4896.0]` cm
after scaling, matching its 209 × 161 × 49 m OBJ extent.

## 2. 100× unit corruption inside the placement transforms

**Symptom:** cells contained geometry 900+ km away; nearest-point fitting against
the spline gave a 163 m median residual and never converged.
**Cause:** part of the BeamNG `TSStatic` placements were transformed with metres
while the rest used centimetres. In `c5_18`, 24,207 / 285,492 vertices sat
~900 km out; dividing that cluster's centre by 100 gave (2838, 9192, 862) =
the position of the good geometry (2885, 9218).
**Fix:** `fix_units.py` — classify vertices by distance from the tile's median
centre; divide by 100 (or multiply) when that lands them back in the tile.
**Result:** 486,720 of 4,957,233 vertices (9.8%) corrected, **0 unmatched**.
Worst tile span went from 993,000 units to 665 × 482 m; median 520 × 515 m.
**Lesson:** a 100% match rate on a unit test is the signature of an exact unit
bug, not a heuristic.

## 3. `--fix-level` does NOT patch the spline or gates

**Symptom:** tool prints `roads=2 gates=40`, output is byte-identical to input.
**Cause:** `PatchLevel()` only handles `stream` and `playerstarts` keys. The
roads/spline/gates patcher is `PatchRoads()`, which is the **default** mode
(no flag).
**Fix:** run UMapPatch with no mode flag to patch `spline` + `gates`.
**Verified by:** `spline MotorTownRoad: patched 1011/1011 gates=40`, `.uexp`
changed, `--verify` prints pt[0] matching the source JSON to the decimal.

## 4. The spline lives in the streamed level, not `C1.umap`

**Symptom:** patching `C1.umap` reports `roads=0 gates=0` — nothing to patch.
**Cause:** `MotorTownRoad` is in the streamed sub-level `C1_Roads.umap`.
**Fix:** patch `Maps/C1_Roads.umap`; the game world is `Maps/C1.umap`.

## 5. Import tables live in `.umap`, export data in `.uexp`

**Symptom:** a repoint reported success but the `.uexp` was unchanged, which
looked like another silent no-op.
**Cause:** import/name tables are serialised in the `.umap` header; property and
array data (spline points, transforms) live in the `.uexp`.
**Fix:** byte-diff the *right* file: repoints → `.umap`; spline/transforms →
`.uexp`. Check both when unsure.

## 6. Never trust printed counters — byte-compare

**Symptom:** `playerstarts moved=1` while the emitted `.uexp` had **0** differing
bytes.
**Cause:** the property write was a silent no-op; the counter incremented anyway.
**Fix:** every patch step must end with `cmp -s in out` on the file that carries
the data. Only report success when bytes actually differ (or when a `--verify`
dump reads back the new values).

## 7. PlayerStart is decorative — a transform-less child of `BP_NS_Prop`

**Symptom:** spawn point cannot be set; no coordinate anywhere in the chain.
**Cause:** `PlayerStart` export `[55]` has only
`CapsuleComponent, GoodSprite, BadSprite, RootComponent`. Its `RootComponent` is
a `ChildActorComponent` `[25]` whose `ChildActorClass` is `BP_NS_Prop_C`, attached
to a `SceneComponent` `[57]`. No `RelativeLocation` exists on any of them — the
original NS map is identical.
**Consequence:** spawn position comes from `BP_NS_Prop` at runtime; with that
class missing, spawn collapses to the origin.

## 8. Blueprint class repointing crashes the game

**Symptom:** `BP_NS_Sky → MTSunSky` and `BP_NS_Prop → ActorPreviewBP` repoints
(repointed packages=2 classnames=4, import table verified clean) crashed on load.
**Cause:** unlike meshes, a blueprint actor export serialises its **component
templates** (`SunSky_GEN_VARIABLE`, `LeftChild`, …) which are bound to that class's
layout. Re-classing leaves templates whose class lacks those components → hard
crash at level load. `ActorPreviewBP` additionally looks editor-only.
**Fix / rule:** never re-class a blueprint actor in a cooked level. Either supply
the original class or author a compatible one.

## 9. Supply the missing NS classes instead (the working approach)

**Symptom:** level references `/Game/Mods/Nordschleife/{Sky/BP_NS_Sky,Props/BP_NS_Prop}`
which nothing provides.
**Cause:** we cloned the level but not the actors it needs.
**Fix:** ship the assets from `ZZ_Nordschleife_P.pak` in a small companion pak.
Only three assets exist under those folders — `BP_NS_Sky`, `BP_NS_Prop`, `LS_Sky` —
so there are no residual sub-references.
**Result:** `zzz_AMC_C1NSDeps_P.pak`, 5,126 B, 6 files,
mount `../../../MotorTown/Content/Mods/Nordschleife/`. World loads after this.
**Note:** that is third-party content — fine locally, needs the author's permission
to publish.

## 10. Cooked unversioned properties are validated against the class schema

**Symptom:** `FormatException: No valid property "RelativeLocation" in class
/Script/Engine.PlayerStart` at save time, after a partial write.
**Cause:** adding a property that the class does not declare is rejected during
unversioned serialisation. `RelativeLocation` exists on scene **components**, not
on the `PlayerStart` actor.
**Fix:** only mutate properties that already exist in the class schema, and only
walk components (`*Component` classes) when positioning. The working spawn patch
writes to the `ChildActorComponent` and its parent `SceneComponent`
(`positioned=2`).

## 11. PowerShell through two ssh hops mangles quoting

**Symptom:** `'Measure-Object' is not recognized`, `-Command` help text printed,
`$_.Name` expanded by the wrong shell.
**Fix:** never inline `-Command` with `$`, backticks or `{}`. Write a `.ps1`,
scp it, run `powershell -NoProfile -ExecutionPolicy Bypass -File D:/x.ps1`.

## 12. `Set-Content` collapses response files → UnrealPak silently packs fewer files

**Symptom:** 12,413-byte pak containing only the `.uasset`, no error.
**Cause:** a 2-line response file was written as one line; UnrealPak parsed one entry.
**Fix:** build the list as a `List[string]` and assert `list_lines` equals the file
count before packing. Also verify a pak is non-trivial: an empty one is ~339 bytes.

## 13. `tar -C <dir>` fails if the directory does not exist

**Symptom:** `tar: could not chdir`, then an empty pak was built and installed.
**Fix:** `New-Item -ItemType Directory -Force -Path $src` before extracting, and
abort on failure instead of continuing.

## 14. `mod_explore` cannot read the encrypted game pak

**Symptom:** "pak is encrypted but no key was provided" regardless of `KEY` in env.
**Cause:** `mod_explore` is the mod-pak (unencrypted) tool. `pakdump` / `pakextract`
read `KEY` from the environment.
**Also:** `MotorTown-Windows.pak` in the repo is a 17-byte stub — the real client
pak is `client-0.7.19.pak`; the real server pak is `server-0.7.19.pak`.

## 15. FName number suffixes look like truncation

**Symptom:** "only 10 distinct `/Game/Mods/C1/Meshes/...` refs" and imports
displaying as `/Game/Mods/C1/Meshes/c-1` for every cell.
**Cause:** UE stores a trailing `_<digits>` as a separate FName number field.
Printing the base name only shows `c-1` for `c-1_10`, `c-1_11`, …
**Fix:** count distinct imports via the import table, not by grepping strings.

## 16. UnrealPak derives the mount point from the common prefix

Packaging `MotorTown/Content/Mods/Nordschleife/{Props,Sky}/…` yields mount
`../../../MotorTown/Content/Mods/Nordschleife/` with entries `Sky/BP_NS_Sky.uasset`
— which resolves to `/Game/Mods/Nordschleife/Sky/BP_NS_Sky`. Same shape as the
C1 pak (`…/Mods/C1/` + `Meshes/…`). Do not force a mount string; check the
reported one after packing.

## 17. Collision stage exits rc=1 but succeeds

**Symptom:** `SaveLoadedAsset failed: Asset is not registered. The object
'BodySetup_0' is not an asset.` plus `collision rc=1`.
**Cause:** BodySetup is a sub-object, not an asset; the save call is noise.
**Behaviour:** the marker still reports `C1COL_DONE meshes=75 changed=75 failed=0`
and cooked meshes carry per-triangle (complex) collision. Treat rc as advisory,
gate on the marker.

## 18. Everything must be installed AND verified from the installed pak

**Pattern:** build → copy to `Paks` → pull the installed pak back → extract the
entry → sha256 against the file that was built. Only then does "installed" mean
anything. Several rounds were wasted testing a pak that never contained the change.

---

## 19. The Nordschleife track lives near the world origin — ours did not

**Symptom:** world loads but everything is kilometres away; player spawns in empty
ground and sees the track in the distance.
**Cause:** the corridor geometry came from BeamNG's placement frame, which is not
Motor Town's. Measured:
- NS `MotorTownRoad` spline pt[0] = `(-51,627, 235,126, 13,975)` cm; the whole NS
  track spans roughly x −600…1200 m, y −1700…2400 m, z −54…141 m — around the origin.
- our corridor before the fix: x −762…2089 m, **y 5618…9672 m, z 838…887 m**.

MT spawns near the origin (the PlayerStart has no authored transform of its own),
so the map was always going to be 5–9 km from the player.
**Fix:** translate all 75 mesh components and the 1,011 spline points by
`NS_pt0 − our_pt0 = (-260583.46, -732139.39, -72599.88)` cm, so our road starts
exactly where the NS road starts. This is "match the mod that works", not an
arbitrary move to zero.
**Verified by:** `placed 75 components`, spline `patched 1011/1011`, and
`--verify` on `C1_Roads` printing `pt[0] = (-51627.0, 235126.0, 13974.9)` —
identical to NS.

## 20. Spline/road alignment is measurable — do it instead of eyeballing

**Question that kept recurring:** "are the splines actually on the roads?"
**Measurement:** distance from each of the 1,011 spline points to the nearest
`mat_road_01` face centroid, in the cells' own coordinates.
**Result:** median **1.0 m**, mean **1.6 m**, p90 **3.5 m**, max **14.1 m**.
The spline is on the road. When it *looks* wrong in game, suspect spawn/world
placement, not the spline.

## 21. Centre the corridor on the origin, don't start it there

**Symptom:** after aligning our road *start* to NS's road start
(`-51627, 235126, 13975`), the player still fell in mid-air with a building
nearby and the highways visible in the distance.
**Cause:** NS's track *surrounds* the origin (it spans y −1700…2400 m). Ours only
touched it at one end, so the spawn point still sat 2.4 km from the asphalt.
**Fix:** translate so the **spline centroid** lands on the origin, not the first
point. Total offset from the original cell frame:
`(-13870.33, -839210.51, -86515.89)` cm. Resulting spline bbox:
x −963…1951 m, y −2780…1625 m, z −12…15 m — origin is inside the corridor in all
three axes, and `pt[500]` = `(-1266, 22999, -412)` cm sits ~230 m from origin.
**Rule:** for a spawn that Motor Town chooses, the geometry must *contain* the
spawn area, not merely touch it.

## 22. Component `RelativeLocation` is ignored — bake offsets into vertices

**Symptom:** the spline moves every build; the 3D geometry never moves. Player
always spawns far from visible roads while the minimap shows a spline at their feet.
**Cause:** writing `RelativeLocation` onto those static-mesh components has **no
effect on what renders**. Verified the file was correct —
`comp[3847] mesh=c4_19 loc=(-272038.1,-743662.3,-82470.7)`, zero null meshes — and
the render still ignored it. These components came out of a blueprint actor chain
(the NS prop/actor hierarchy), so the parent transform, not the relative offset,
drives placement; and the mesh vertices already carry world-space coordinates.
**Fix:** translate the **OBJ vertices** before import (cell frame is metres, so
divide the cm offset by 100), leave components at `(0,0,0)`, and keep the spline
at the same target. Re-import → materials → collision → cook.
**Also learned:** a re-cook that changes geometry grows the pak noticeably
(169,952,457 → 171,345,589 B). Byte-identical pak sizes across placement changes
were the tell that nothing had moved.
**Verification trap:** patching and checking the *file* proves nothing about
*rendering*. Only `--comps` read-back plus a visible change in game closes the loop.

## 23. OBJ import MIRRORS the Y axis (the bug behind "nothing changed")

**Symptom:** geometry always appears hundreds of metres to kilometres from the spawn.
Offsets are applied, verified in the file, and make no difference. The spline (data)
sits at the right place; the meshes (imported) never do.
**Cause:** Unreal's OBJ importer negates **Y** while preserving X and Z. Measured on
`c-1_10`, source vs cooked asset bounds:
- X `-2920.3 … -2710.9` m → `-2920.2 … -2710.8` m (preserved)
- Z `25.5 … 74.4` m → `25.5 … 74.4` m (preserved)
- Y `-2085.7 … -1924.8` m → **`+1924.9 … +2085.7` m (negated)**
Because the mirror is applied *after* whatever offset we bake, every placement fix
was re-mirrored back out. It also silently reverses triangle winding.
**Fix:** pre-negate Y in the OBJ (`y = -y`) before import, so the importer's flip
cancels. Then verify the cooked asset bounds, not the source file:
`c4_19` must span Y `201658 … 259718` to contain the spawn at Y `223603`.
**Detection that works:** compare **cooked asset bounds** (`mesh.get_bounds()` /
`get_bounding_box()` in UE python) against the source OBJ bbox, axis by axis. Any
sign difference is a handedness bug. Comparing meshes to splines in source space can
never catch it — both are consistently mirrored.

---

## Current state (as of the last build)


- Map pak `zzz_AMC_C1_P.pak` — 169,952,630 B — 4 maps, 75 cells (1,651,570 tris),
  83 kit files, 568 MIs, 1,137 textures
- Deps pak `zzz_AMC_C1NSDeps_P.pak` — 5,126 B — `BP_NS_Sky`, `BP_NS_Prop`, `LS_Sky`
- Menu pak `zzz_AMC_C1Offline_P.pak` — 14,667 B — `C1Shuto` free-roam entry
- Geometry: corrected units, natural world coordinates, no origin shift
- Spline: 1,011 points derived from `mat_road_01` geometry (graph diameter of the
  rasterised road network), 40 gates, course `C1_Shuto`
- Open: spawn placement (PlayerStart has no authored transform), no terrain/ground
  beyond the road cells, no tunnel interiors, no signage

---

## 24. Cell actors were flagged bHidden — 67 of 75 invisible at runtime

**Symptom:** "only a few cells are imported, the rest is void" — a handful of tiles render,
most simply don't, at any distance. Not culling (distance culling hides far geometry, this
hides near geometry while distant geometry stays visible).

**Root cause:** an earlier `--drop-mod-actors` pass, intended to hide Nordschleife's leftover
actors, set `bHidden = true` on the owning `StaticMeshActor` of every component it touched —
including the 75 we had just repointed at our cells. The level then contained 75 valid cell
components, 67 of them on hidden actors.

**Measurement:** `UMapPatch <map> --owners` → `hidden=True` 67, `hidden=False` 8,
`distinct_owners=1` (all `StaticMeshActor`). After the fix: `hidden=True` 0.

**Fix:** `UMapPatch <map> <json> <out> --unhide` — sets `bVisible=true` on every component
whose mesh lives under `/Game/Mods/C1/`, and `bHidden=false` / `bActorHiddenInGame=false`
on its owning actor (creating `bHidden` when absent).
Result: `unhide components=75 actors=75`, pak 171,503,387 B.

**Lesson:** any pass that hides actors must be scoped by the actor's *current* mesh
ownership, not by actor class or by which actors were present before the repoint.
Always re-run `--owners` after any such pass.

---

## 25. Checker textures = material shaders never compiled (Nahimic crashes ShaderCompileWorker)

**Symptom:** every surface without a texture renders the engine default checker;
`M_C1_*.uexp` cooks to ~3.6 KB with zero shader-map strings.

**Root cause (proven, not inferred):** `ShaderCompileWorker.exe` crashes with
`0xc0000005` on the cook box. Windows Event Log, Application, id 1000:
`Faulting module name: NahimicOSD.dll` (`C:\ProgramData\A-Volute\...\NahimicOSD.dll`),
then again in `ntdll.dll`. Nahimic (A-Volute audio OSD, MSI boards) injects into
every process. With SCW dead, no material ever compiles, and both editor and cook
log `Failed to compile Material for platform PCD3D_SM5, Default Material will be
used in game` + `Cooking a material resource ... doesn't have a valid ShaderMap`.

**Diagnosis recipe:**
- `strings M_X.uexp | grep -cE "VertexFactory|BasePass|FMaterialShaderMap"` —
  a compiled master has >0 (NS `M_NS_Base_v2` = 23, ours = 0). File size alone is
  not proof; a simple compiled material can be ~11 KB, a failed one ~3.6 KB.
- `Get-WinEvent -FilterHashtable @{LogName='Application';StartTime=(Get-Date).AddHours(-3)}`
  filtered on `ShaderCompileWorker` gives the faulting module.

**Fix:** stop the injectors before any cook/compile:
`sc stop NahimicService` + `taskkill /F /IM NahimicSvc64.exe` (also `NahimicSvc32.exe`)
via an elevated scheduled task (`/ru <user> /rl highest /it`). Restore afterwards
with `sc start NahimicService` if the user wants the audio OSD back.

**Second lesson — python-authored masters can be permanently uncompilable.**
Recompiling the three original `M_C1_Surface*` masters in an interactive editor
session never produced a shader map even with SCW healthy. Rebuilding them from
scratch in the same editor session worked first try (`M_C1_Tex2` 11,176 B /
`M_C1_TexMasked2` 18,481 B, 14 shader strings, `M_C1_Tex2` parent confirmed in
instances). Lesson: if a master will not compile, recreate it rather than repair it,
and repoint the instances (`parent` property + `update_material_instance`).

**Editor interaction facts that cost rounds:**
- `-ExecutePythonScript` quits the editor the moment the script returns — a tick
  callback cannot keep it alive. Use `-ExecCmds="py <file>"` when the editor must
  stay open (compiles finish, then save in a tick callback).
- GUI editor launched from sshd lands in session 0 and dies with
  `DXGI_ERROR_NOT_CURRENTLY_AVAILABLE`. It only gets a window via
  `schtasks ... /it`, landing in the same SessionId as `explorer`.
- `Material.Expressions` is protected in Python (`cannot be read`) — you cannot
  dump a graph that way.

## 26. Do NOT trust `EditorStaticMeshLibrary.get_num_uv_channels` in a commandlet (it returns 0)

**False alarm that cost hours (2026-11-02)**: the OBJ-imported meshes appeared to have
**zero UV channels**, which "explained" flat textures. It was an API artefact.

- `unreal.EditorStaticMeshLibrary.get_num_uv_channels(mesh, lod)` is **deprecated** in
  5.5 and returns **0** when called from `-run=pythonscript` (commandlet), where
  `StaticMeshEditorSubsystem` is unavailable (`get_editor_subsystem(...)` → None).
- In a real editor session (GUI via schtasks `/it`), `unreal.StaticMeshEditorSubsystem
  .get_num_uv_channels(mesh, 0)` returns the truth: **1 UV channel** for the shipped
  `c5_18` and for Blender-exported FBX imports. UVs were never missing.
- Rule: any editor-subsystem-dependent query must run in a GUI editor session, never in
  a commandlet. If a probe returns a suspicious zero/nil, validate it against a
  known-good asset **in the same process** before drawing conclusions.
- Data point that also came out of this: the FBX round-trip reproduces the OBJ import
  exactly — bounds `565620 × 625280 × 29594`, 133 static materials — so Blender OBJ→FBX
  is a valid import path (Blender 5.2 `export_scene.fbx` uses `axis_forward`/`axis_up`,
  not `forward_axis`/`up_axis`; `wm.obj_import` DOES use `forward_axis`/`up_axis`).
- `InterchangeGenericMeshPipeline.import_vertex_attributes` is **not** the UV switch —
  flipping it (even on the saved `/Interchange/Pipelines/DefaultAssetsPipeline`) changes
  nothing about UV import. `InterchangeGenericAssetsPipeline.mesh_pipeline` is read-only
  from Python (its sub-object can still be mutated, but it does not affect UV import).

## 27. Checker everywhere even though every asset is correct = materials cooked for the WRONG shader platform (SM5 only, game runs SM6)

**Symptom**: grey/white checkerboard over every custom surface in game; nothing in the
cook log; every asset loads at runtime (`mi_load/master_load/mesh_load/tex_load = OK`);
MIs carry correct texture parameters in the cooked pak; meshes have UVs and 133 material
slots; masters contain real `TBasePass*` shader maps.

**Root cause**: `D:\UEProjects\C1\Config\DefaultEngine.ini` had **no** `TargetedRHIs`
entry, so the cook produced **PCD3D_SM5 only**. Motor Town (UE 5.5, RTX 4070, DX12)
runs the **SM6** shader platform, so no shader in our material matched the active
platform and the engine substituted the default material at render time.

**Fix**: add to `Config/DefaultEngine.ini`, then clean-cook:
```ini
[/Script/WindowsTargetPlatform.WindowsTargetSettings]
TargetedRHIs=PCD3D_SM5
TargetedRHIs=PCD3D_SM6
```

**Verified numbers**: cooked `M_C1_Tex2.uexp` **11,176 B** (SM5 only, 1 × `PCD3D_SM5`
string) → **17,983 B** with both platforms (1 × `PCD3D_SM5` + 1 × `PCD3D_SM6`).
Pak 171,508,036 → 171,511,402 B.

**How to check a cook's platform coverage**:
`Select-String -Path <master>.uexp -Pattern "PCD3D_SM5"` / `"PCD3D_SM6"` — a working
modpak must contain the platform the game actually runs.

**Lesson**: "asset loads fine" proves nothing about rendering. Shader *platform* coverage
is a separate axis from shader *presence*. Verify the platform string, not just the
`TBasePass`/`FMaterialShaderMapContent` strings.

## 29. Materials cooked in a separate project NEVER render in Motor Town — reparent to a vanilla master

**Symptom**: the whole map renders flat-coloured with checkerboard patches. Textures,
UVs, MI parameters, master graph, import paths, shader platform (SM5 *and* SM6) all
verified correct, yet nothing changes after any material edit.

**The falsification test that settled it**: set the master to emit a flat magenta
constant and re-cook. The world did **not** change at all. A material that is being
rendered cannot ignore its own master — therefore our material was never on the
surfaces. MT silently substitutes the default material when it cannot resolve a cooked
material's shader map ID (UE log string: `Tried to access an uncooked shader map ID in
a cooked application` → `Default Material will be used`). Shipping builds compile this
warning out, so there is no log to read — the magenta test *is* the log.

**Root cause**: a master material cooked in a different UE project carries shader maps
keyed to a shader map ID the target game cannot resolve. MT's own materials work because
MT cooked them.

**The test that proved the fix** (cheap, no re-cook): take ONE cooked MI from the
installed pak, rewrite only its `Parent` import to a vanilla MT material
(`--patch-export-props` with `op: set_import_ref`, `class_name: MaterialInterface`,
`package_path: /Game/Env/Materials/Road/MI_Road_01A_Ver01_NoGroove`), repack as a tiny
override pak, install. The road immediately rendered MT's asphalt on **our** geometry.
That single test separates three hypotheses at once: our geometry/imports/overrides are
fine, and only our shader maps are rejected.

**The fix** (`--retarget-mis <inDir> <outDir>` in `csharp/UAssetTool`): reparent every
cooked MI to `/Game/Env/Materials/Master/M_PropMaster` and rename our texture params onto
its parameter set. No project change, no re-cook — the MIs are patched from the cooked
output and shipped as an override pak mounted last.

`M_PropMaster` parameter set: `BaseColor`, `Normal`, `Metallic`, `Roughness`, `Specular`,
`Mask` (textures); `Use_MaskTexture`, `Use_NormalTexture`, `UV_Tiling`.

Param remap: `BaseColor→BaseColor`, `Normal→Normal`, `MetallicTex→Metallic`,
`RoughnessTex→Roughness`, `EmissiveTex`/`EmissiveStrength` → **dropped** (no equivalent).

**Verified numbers**: retargeted=568 failed=6 (the 6 masters — no `Parent` property,
expected). `zzzz_AMC_C1Mats_P.pak` = 2,301,786 B replacing 568 instances, vs the 171 MB
main pak. Textured corridor confirmed in-game.

**Gotchas learned on the way**:

- **Override pak precedence**: name it `zzzz_` so it mounts after `zzz_AMC_C1_P` and wins
  the same asset paths. A one-file pak is enough to test a single material.
- **`mesh:GetMaterial(i)` and `mi:GetMaterial()` return nil for EVERYTHING in UE4SS** —
  vanilla `Atlas/Cab` and `MI_Road_01A_Ver01_NoGroove` return nil too. Never conclude
  "no materials at runtime" from these accessors; validate against a vanilla asset first
  (same trap as entries 24–25).
- **`PKG_UnversionedProperties` absence is NOT a bug**: unversioned cooked packages are
  opt-in (`-UnVersioned`), so versioned cooked content is legitimate. Do not chase it.
- **NS (Nordschleife) is SM5-only with its own masters** — so platform coverage and
  cross-project cooking are both *not* general explanations; only the shader map ID is.
