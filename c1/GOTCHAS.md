# C1 Shuto map — gotchas, root causes and fixes

Running log of every trap hit while porting the BeamNG C1 Shuto corridor into Motor
Town (UE 5.5.4) as a modded map. Each entry: **symptom → root cause → fix**, with
the measurement that proved it where one exists. Add to this instead of
re-deriving.

Toolchain paths
- Cook host: `D:\UEProjects\C1` (Win64, UE 5.5.4 at `D:\UE_5.5`)
- Level/asset patcher: `mt-pak-extract-wt-0719/csharp/{UAssetTool,UMapPatch}`
- Scratch work: `/opt/data/cache/scratch/c1`
- Client paks: `D:\SteamLibrary\steamapps\common\Motor Town\MotorTown\Content\Paks`

---

## Audit 2026-11-05 — entries that were wrong and caused regressions

Every entry was re-checked against live measurements. Three were actively harmful:

- **§22 "bake offsets into vertices, leave components at origin" — over-broad, now scoped.**
  Correct only for components inside a blueprint actor chain. Standalone `StaticMeshActor`
  transforms do move what renders (554 actors, verified). Following it literally is why
  placement was "fixed" by re-importing the whole mesh set over and over.
- **§23 "pre-negate Y in the OBJ" — wrong for BeamNG sources, now scoped.** The importer
  negating Y *is* the BeamNG→MT conversion (opposite Y axis). Cancelling it mirrors the
  map against splines authored in MT space. Carry the sign in the actor transform instead
  and mirror UV **V**.
- **§17 "collision rc=1 but succeeds, gate on the marker" — not a collision gate.** The
  marker counted write attempts; the meshes ended up with 0 simple collision and only 76
  of 555 with `CTF_UseComplexAsSimple`. Gate on the per-mesh trace flag read back.

Lesson that generalises: **a doc entry is a hypothesis about a specific build.** When a
symptom reappears after a documented fix, re-measure before re-applying — a stale entry
applied confidently is worse than no entry.

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

> **CORRECTION 2026-11-05 — that marker is not a collision gate.** It counts write
> *attempts*, not resulting state. Measured on the 555-mesh full map: **0 meshes had
> simple collision and only 76 carried `CTF_UseComplexAsSimple`**; the remaining 479 sat
> at `CTF_UseDefault` with an empty body setup — geometry you can see and fall straight
> through. The only trustworthy check reads the flag back per mesh, in a fresh process:
> `mesh.get_editor_property("body_setup").get_editor_property("collision_trace_flag")`.
> Also note `get_collision_complexity()` disagrees with that property (see the
> 2026-11-03 collision notes) — and that the cook still emits `ConvexElems`, so "0 convex
> hulls" is not a state you can rely on either.

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

> **SCOPE CORRECTION 2026-11-05 — this entry caused repeated re-imports and a collision
> regression; read the scope before applying it.** "Component transforms do nothing" is
> true only for components that belong to a **blueprint actor chain** (the NS prop
> hierarchy), where the parent transform wins and the vertices are already world-space.
> It is **false for standalone `StaticMeshActor`s**: verified 2026-11-05 by moving 554
> cell actors with `set_actor_location` — the world union went from a collapsed 5.1 ×
> 12.1 km to the correct 19.2 × 27.6 km, with no re-import and no vertex edit.
> Rule: fix **placement** with actor transforms (idempotent, cheap, keeps collision and
> UVs); touch vertices only when the geometry itself is wrong. Re-importing to fix
> placement discards `BodySetup`/`CollisionTraceFlag` — that is how a build ships with
> no collision (see §17 correction).

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

> **SUPERSEDED 2026-11-05 — do not apply this fix blindly.** The *observation* stands
> (the OBJ importer negates Y; X and Z pass through). The *fix* only applies when the
> source geometry must keep its own Y sign. For a **BeamNG source**, the negation **is
> the conversion**: MT runs the opposite Y axis, so `y_MT = -y_BeamNG`. Pre-negating the
> OBJ cancels that and puts the map back in the wrong handedness — the whole map ends up
> mirrored against road splines that were authored in MT coordinates.
> Correct handling for BeamNG sources: leave the OBJ alone, let the importer's negation
> stand, and carry the offset in the actor transform (`y = -origin_y * 100`). Then mirror
> **V** in the UVs, because the same mirror reverses the texture (checklist §2h, gate C).
> Also: the "trace winding" note below means imported meshes are back-facing — this is
> why masked/foliage surfaces need `TwoSided`.
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

> Six material paks were shipped chasing "the blend mode is wrong" before the real defects (a
> dead parameter binding, and textures carrying no alpha) were found. Read
> `docs/MATERIALS_ALPHA_BLEND.md` before building a second variant on alpha or blending — it
> carries the attempt ledger and the diagnosis order. The single most expensive rule in it:
> **reparenting changes the parent, not the parameter names**; an instance reparented onto
> `M_plants` while its colour parameter is still `Color` binds nothing and renders a *black*
> background, which is indistinguishable from a broken mask.

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

## 2026-11-03 — full-map attempt (parked) and pipeline split

- **`LevelEditorSubsystem.load_level` in `-run=pythonscript` reports 1 actor** for a
  populated map. If a script keys off `get_all_level_actors()` it will "not see" 75 existing
  actors, spawn duplicates, and save. Key off actor labels, and always re-read the saved map
  with `UAssetTool --level-actors` before cooking. This is how the corridor level was lost
  from the project (recoverable: corridor ships maps from `maps_in/`).
- **`ECollisionTraceFlag` has no NoCollision member.** Collision-off is per component:
  `smc.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)`. `collision_enabled` is
  not exposed as an editor property in this build.
- **`set_lod_from_static_mesh(dest, dest_index, src, src_index, reuse_slots)`** — destination
  index is the SECOND argument. Wrong order → "Failed to convert parameter
  'destination_lod_index'". `set_lod_screen_sizes`/`set_lod_group` don't exist on that class;
  `lod_group` is a plain StaticMesh editor property.
- **Interchange hard-asserts with no traceback** when an OBJ face UV index exceeds the `vt`
  array. Write LOD OBJs position-only.
- **Two-pass collision writing is mandatory**: accumulating all faces in RAM OOMs at the
  8 GB container cap (died silently twice at exactly 61 tiles).
- **A pak entry list is a better spec than a manifest.** Rebuilding the corridor pak from
  `cells_manifest.json` + the material manifest dropped 2 meshes, 6 MIs and ~550 texture
  assets; rebuilding from the verified pak's own file list gave exact parity (4,847 entries).
- **Maps are pairs.** `C1_Roads.uexp` holds the spline data; shipping only the `.umap` is
  silent and roadless.
- **The full-map pak is 1.12 GB and too slow to play.** Parked at
  `builds\zzz_AMC_C1_Full_P.pak`; corridor pak restored over it. See `pipeline/README.md`.

## 2026-11-03 — corridor collision

- **Shared asset names are the pipeline-split trap.** The full-map import re-imported the
  corridor's 74 cells (same names, same folder) with default collision, so per-asset settings
  from the corridor track (complex-as-simple) do not survive a full-map import. `replace_existing`
  imports must be followed by a re-apply of collision/materials for that track.
- **`is_section_collision_enabled` returns False unconditionally** in this build — even right
  after `enable_section_collision(..., True, ...)`. Section-level collision filtering is
  therefore unverifiable and must not be shipped blind.
- **`enable_section_collision(static_mesh, collision_enabled, lod_index, section_index)`** —
  four positional args, enabled first. Sections are per-LOD; collision reads LOD0.
- **`get_collision_complexity()` disagrees with `body_setup.collision_trace_flag`**; the former
  reported CTF_USE_DEFAULT for a mesh that was already complex-as-simple. Trust the body_setup
  property, read in a fresh process.
- **`StaticMaterial` has `material_interface`, not `material_interface_path`** — reading the
  path property raises and kills the whole run.
- **Env vars do not survive nested `ssh → ssh → powershell` quoting**; pass script options via
  a flag file in the project root instead.
- Corridor geometry is clean: 0 duplicate faces, 0 malformed faces, 2,042 zero-area collinear
  tris (PhysX discards them). Collidable families are 64% of corridor triangles.

## 2026-11-03 — navigation / dangling references (corridor crash)

- **A cooked map can export actors whose class package no longer exists.** The corridor level
  shipped 23 `BP_NS_Prop_C` and 1 `BP_NS_Sky_C` exports (plus 24 child components) imported
  from `/Game/Mods/Nordschleife/...`. While the NS pak was installed they resolved; after it
  was removed the level had 24 unresolvable class imports — a fatal load error, and the most
  likely cause of the crash.
- **`--prune-level` drops exports only, imports are left behind** (by design: "unused imports
  are inert"). Use `--compact-imports` afterwards to rebuild the import table; it walks
  ClassIndex/OuterIndex/SuperIndex/TemplateIndex and every property, so class imports of
  surviving exports are kept.
- **A dump listing shows export `Class=` as a name, not an index** — reachability analysis
  based on `Index=-N` only will report class imports as unused and is wrong. Do index-based
  analysis in C#, not on the text dump.
- **Soft references cannot be validated through the import table.** The sublevel link is a
  `SoftObject` `WorldAsset` to `/Game/Mods/C1/Maps/C1_Roads`, which never appears as a package
  import; a map can look "clean" and still stream a sublevel. Check soft paths separately.
- **`UnrealPak -List` cannot read the encrypted vanilla pak**: `-cryptokeys=` with a
  `guid: null` key fails with `Failed to find requested encryption key 0000...`, and the legacy
  `-aes=0x...` path truncates the key ("more than 32 characters"). Use the Rust `listpak` with
  the key, or pull the pak.
- **UE4SS `mods.txt` lives at `ue4ss\Mods\mods.txt`**, not `ue4ss\mods.txt`. Crash dumps land in
  `ue4ss\crash_*.dmp`; a shipping build writes no UE log at all, so there is no textual crash
  record.
- `is_section_collision_enabled` false-positives (see above) also mean: never trust a
  reader that returns a constant. Verify against a second, independent read.

## 2026-11-03 — placing actors in a cooked level (sunsky / garage / PlayerStart)

- **Unversioned cooked properties are index-based, not name-based.** The writer emits a header
  of schema indices, so a property dict is only correct if the schema used at write time is the
  export class's real schema. Writing a Blueprint-class actor (`*_C`) while substituting another
  class's schema (the old `--add-garage` trick) produces index values the engine will read
  against the *BP's* schema — silently wrong. Use native classes (schema present in
  `Mappings.usmap`) or add a real schema for the BP class first.
- **A `--dump` of an unknown class reads back as `RawExport`**, even when the written bytes are
  fine. Do not use "C#Type=RawExport" alone as proof of failure; check `SerialSize` and, for
  native classes, that properties parse (`Properties (1): RootComponent`).
- **Freshly constructed `PropertyData` has no ancestry**, so `GenerateUnversionedHeader` cannot
  resolve it — clone a property from a real export instead.
- **FName number suffix**: `PlayerStart_0` is Value `PlayerStart` + Number `0`; compare with
  `ObjectName.ToString()`, not `ObjectName.Value.Value`.
- `--add-bp-actor` (native or BP class) and `--move-actor` now live in UAssetTool.

## 2026-11-03 — actors need their instanced components; override paks shadow later fixes

- **A cooked actor does NOT rebuild its instanced components from the constructor.** `AMTSunSky`
  owns `RootSceneComponent`, `DirectionalLight_Sun2`, `DirectionalLight_Moon2`, `SkyLight2`,
  `PostProcess` as `Instanced` UPROPERTYs, and `UpdateLighting()` dereferences them. Placing a
  bare `MTSunSky` actor (one `RootComponent`, no subobjects) crashes with
  `EXCEPTION_ACCESS_VIOLATION` on the first tick. Same shape for `AMTGarageActor`
  (`SizeBoxComponent`, `Camera`). The vanilla pattern (see `DrivingLicense.umap`) is actor
  export + one child export per component, all `Outer=<actor>`.
- **Therefore: transplant, do not author.** Copy the actor export *and* its descendant exports
  from a vanilla level, remap import indices, then override the transform.
- **An override pak silently shadows later fixes to the same assets.** `zzzz_AMC_C1Mats_P.pak`
  mounts last and replaces all 568 MIs; the grass/dirt BaseColor fix landed in the main pak's
  MIs and was therefore never visible. Rebuild the override pak from the *current* cooked MIs
  whenever MI params change. Verify by extracting the MI from the override pak and checking the
  parameter count/parent, not by rebuilding the main pak.
- **Uncompiled masters are invisible weight** once every MI is reparented to a vanilla master:
  `M_C1_Surface`, `M_C1_Surface_Masked`, `M_C1_Surface_Tex` ship with 0 shader maps.
- **`zzz_AMC_C1NSDeps_P.pak` is obsolete** after the reference cleanup — nothing imports the NS
  classes any more, and it is third-party content.

## 2026-11-03 — bisect discipline when a map crashes

- **A "known-good" pak is only known-good in its original environment.** The 171 MB corridor build
  contained the 23 `BP_NS_Prop_C` actors; it loaded only because the Nordschleife pak was
  installed. Running it without NS was guaranteed to crash and proved nothing. Always state the
  precondition of a baseline before spending a launch on it.
- **UE4SS `crash_*.dmp` files are useless for stacks here.** UE4SS v3.0.1 writes them from the
  `dbgcore`/MiniDumpWriteDump thread with `ExceptionAddress = 0` and a zeroed `ThreadContext`
  (`rip = 0`), so neither the exception stream nor a thread-context walk yields a faulting frame.
  Scanning other threads' stacks produces false-positive "MotorTown" frames at `+0x0`.
- **Bisect from the outside in**: (1) move all mod paks out and confirm the game boots,
  (2) restore our paks, (3) swap one asset group at a time. Do not start by editing the level.
- **`MTEnv::SunSky` is assigned, never dereferenced** in native code, so a level with no sunsky is
  not a null-deref crash on its own.

## 2026-11-03 — ROOT CAUSE: bAutoSpawnMissingNavData on a custom level

- **A custom level that ships no nav data must not ask for nav data to be spawned.**
  `NavigationSystemModuleConfig_0.bAutoSpawnMissingNavData` was `True` in `C1.umap`. The map has
  no `RecastNavMesh` and no `NavMeshBoundsVolume`, so world init tried to build a navmesh with
  nothing to build it from and the client died with `EXCEPTION_ACCESS_VIOLATION` during level
  load. Vanilla levels carry the same flag but always have the actors to satisfy it.
- **Fix**: set the flag to `False` — `UAssetTool --set-bool <in.umap> <out.umap>
  NavigationSystemModuleConfig_0 bAutoSpawnMissingNavData false` (1 byte changes in the pak).
- **Bisect lesson**: this flag was `True` in every build tested, so the earlier "materials crash",
  "meshes crash", "roads crash" conclusions were all the same fault. Before adding or removing
  content, verify the *level's own world settings* — a constant fault makes every bisect result
  meaningless.
- **`zzz_AMC_C1Offline_P.pak` is not a launcher**: it overrides
  `/Game/DataAsset/GameResource` (`MTGameResource`), adding a 13th `DriveMaps` row and a 7th
  `TimeAttackMaps` row (`Key=C1Shuto`, `Level=/Game/Mods/C1/Maps/C1`). Remove that pak and the
  map silently disappears from the in-game map/time-attack lists. Its `WorldMapTexture` points at
  vanilla `T_WorldMap_Jeju`, so the row itself is valid.
- **FName Number vs Value**: `NavigationSystemModuleConfig_0` is stored as value
  `NavigationSystemModuleConfig` with `Number = 1`; string comparisons must rebuild the suffix.
- **An MI set travels with its masters — reparenting to a vanilla master is a regression,
  not a fix**: C1's 1,633 material instances parent to four masters shipped in the same pak
  (`M_C1_Surface`, `M_C1_Surface_Tex`, `M_C1_Surface_Masked`, `M_C1_Surface_Trans`) and
  render correctly. Flattening them onto `M_PropMaster` renames texture parameters
  (`MetallicTex → Metallic`, `RoughnessTex → Roughness`) so values stop binding, and
  destroys masking/translucency outright — `_Masked` and `_Trans` have no equivalent, so
  those surfaces draw nothing. Result: "some materials load, most are missing, roads
  among them". The earlier "MT rejects third-party master shaders" conclusion was wrong:
  the two invisible-geometry incidents were a texture-namespace rename and a 100× scale
  error, neither of which was a material fault.
- **Gate for the above**: for every MI resolve `Parent (Object): Index=-N` to
  `Import[N-1].Name` (negative index is 1-based, so `-9` is `Import[8]`) and require that
  name to exist as an asset **inside the same pak**. Bundling the MIs but not their masters
  fails silently at load with no log line.
- **A Texture2D written into a SCALAR parameter invalidates the instance → engine
  checkerboard**: MT builds shader maps into its own library, so a master cooked in our
  project can never render (its `.uexp` is ~3–8 KB, there is no shader data to ship). Only
  instances of MT's own masters render. When retargeting `M_C1_Surface_Tex` instances onto
  `M_PropMaster`, its parameter set is **`BaseColor` (texture), `Normal` (texture),
  `Metallic` (scalar), `Roughness` (scalar), `Specular` (scalar), `UV_Tiling`** — prove it
  from the master's `TextureStreamingData`, which lists exactly two textures (`T_Normal_N`,
  `T_White_BC`). Renaming `MetallicTex → Metallic` and keeping the Texture2D value produces
  an instance that fails to compile and draws the default checkerboard, exactly like a
  missing material. Drop such parameters instead and let the scalar defaults apply.
- **"Backface" of the same bug — probe disagrees with the screen**: `GetMaterial(0)` on the
  component returns the assigned MI and reports `comp_default_material=0`, while the screen
  shows checkerboard, because assignment succeeds and only compilation fails. Do not treat a
  clean material-resolution probe as proof the materials render; a checkerboard screenshot
  outranks it.

- **NEVER ship `ShaderArchive-*.ushaderbytecode` in a mod pak — it crashes the client**
  (2026-11-05, v11, reproduced): the game ships exactly two archives,
  `ShaderArchive-Global-PCD3D_SM5` (13,242,450 B) and `ShaderArchive-MotorTown-PCD3D_SM5`
  (56,636,716 B) — **no SM6 archive at all**, so MT runs `PCD3D_SM5`. A UE cook of our project
  emits the same two names but partial (13,181,977 B / 6,186,317 B). Mounting them shadows the
  game's files and the client dies at boot with
  `LowLevelFatalError [GlobalShader.cpp] [Line: 803] Could not load section 11 (of 330) of the
  global shadermap`. Mod paks cannot extend MT's shader library, so **custom material masters
  can never render in MT regardless of how cleanly they cook**. Ship instances of MT's own
  masters only, and add a packaging gate: no `ShaderArchive-*` entry may appear in a mod pak.
- **"Compiled successfully" is not proof a master can render — check the payload.** A master
  that failed to compile cooks at ~3.6 KB with zero shader strings; a real one is 17–32 KB and
  carries `PCD3D_SM5`/`PCD3D_SM6` plus `TBasePass*` shader-map names. Gate on size + strings;
  the cook exit code and `LogCook: Done!` say nothing about it.
- **A cook with no `TargetedRHIs` silently emits uncompilable materials.** `DefaultEngine.ini`
  needs `[/Script/WindowsTargetPlatform.WindowsTargetSettings]` with `TargetedRHIs=PCD3D_SM5`
  (MT's platform) or the log fills with `Failed to compile Material for platform PCD3D_SM6 …
  Default Material will be used in game`.
- **Repairing a broken master never works; rebuild it.** The compiled pair in the C1Full project
  (`M_C1_Tex2`, `M_C1_TexMasked2`) is a from-scratch rebuild that kept the original parameter
  names (`BaseColor`, `MetallicTex`, `Normal`, `RoughnessTex`, `EmissiveTex`, plus scalars), so
  original instances bind with no renaming. Editing `M_C1_Surface*` re-cooks the same 3,640 B
  failure every time.
- **Meshes reference material names that were never created.** A mesh slot is a hard import of
  `/Game/Mods/<root>/Materials/MI_<name>`; if no asset has that name the slot draws the engine
  default and looks like a broken material. C1Full had 30 such names — `MI_C1_mat_wal` alone was
  referenced by 99 meshes — because the instances were later renamed with suffixes
  (`MI_C1_mat_wal_15`) and the meshes were never updated. Gate builds on mesh→material coverage
  (checklist §2c). Fix by cloning the surviving sibling under the name the mesh expects.
- **Loose assets at the namespace root are part of the map, not of the folders.** `BP_C1_Sky`
  (carries the `SunSky` child component) and `BP_C1_Prop` live directly under
  `/Game/Mods/C1Full/`. A packer that copies only `Materials/ Maps/ Meshes/` ships a level with
  no sun and no skylight; the result is an unlit scene that is easy to misread as "materials not
  applied". Gate: every `/Game/Mods/<root>/…` import in the map resolves inside the pak
  (checklist §2d).
- **Verify which namespace the *cooked map* references, not which one the project contains.** A
  project can hold two full content trees while the level still points at the older one: C1Full
  had `Mods/C1` (4,587 assets) and `Mods/C1Full` (5,300) with divergent mesh generations
  (`c-10_-20` 71,574 B vs 72,890 B), and the map referenced `Mods/C1` until it was repointed.
  Check `strings <map>.umap | grep -oE '/Game/Mods/[A-Za-z0-9_]+/Meshes'` on the *cooked* map.
  Duplicated trees are the underlying defect — one namespace per release pair is the fix
  (`.hermes/plans/2026-11-05-single-content-namespace.md`).
- **The cook writes texture parameter values as NULL — never source instances from a cook output.**
  A cooked `MaterialInstanceConstant` keeps the parameter *name* but stores
  `ParameterValue (Object): Index=0`, i.e. no texture, and the surface renders **flat white**. Measured:
  every instance in the project cook had null `BaseColor`, while the same instance in the shipped C1
  pak carried `Index=-7` → `Texture2D mat_wal_15_file0`. The duplicate `C1Full/Materials` tree was
  degraded the same way. Authoritative source for instances = the build that demonstrably rendered.
  Gate: `UAssetTool --dump <mi>.uasset | grep 'ParameterValue (Object)'` must show non-zero indices,
  sampled per material family.
- **White ≠ checkerboard, and the distinction is diagnostic.** Checkerboard = material never resolved
  (missing asset, dead parent, uncompilable master). White = material resolved and rendered with a
  sampler on its default (null `BaseColor`, or a parameter name the master does not declare). Seeing
  white after seeing checkerboard means the chain is connected and only the bindings are wrong.
- **The mask flag and the parent are decided by different inputs — wire both or the surface stays opaque.**
  A sectioned route list (`[veg]`/`[masked]`/`[trans]`) fed the parent choice but the
  `isMasked` test only read the masked list, so vegetation was parented to `M_plants` **without**
  the per-instance `BLEND_Masked` override and drew its texture's green backdrop. Symptom is
  selective: instances that were *also* in the authored-masked list got the override and looked
  fixed, which reads as "some trees work, some don't". Fix: vegetation implies masked
  (`isMasked = isVeg || maskSet.Contains(name)`).
- **Verify the override actually serialised, per instance, by dumping it — the write fails silently.**
  `UAssetTool --dump <mi>.uasset` must show all three of `BasePropertyOverrides` →
  `BlendMode (Enum): BLEND_Masked`, `TwoSided (Bool): True`, `OpacityMaskClipValue (Float): 0.3333`.
  A struct that carries only `TwoSided` + clip (or `BlendMode (Byte): 0`) is opaque: the property
  was dropped during serialisation and nothing logs it. Sample one instance per route, never one
  instance total — the dropped-property case is per-asset.

## 30. A pipeline stage that skips on a missing input reads as success

**Symptom:** `06_postcook_patch.sh <wrong-path> <out>` printed
`== parent map absent, skipping (delta build)` and **exited 0**, so the patch looked
applied. Shipping that would have shipped an unpatched level (no game mode, no sunsky,
no spawner classes) with a green log.

**Cause:** the "delta build" convenience path treated a missing file the same as a
deliberate partial build.

**Fix:** absent parent map is now `exit 5` unless `ALLOW_DELTA=1` is set explicitly.

**Rule:** any stage whose job is "patch X" must fail when X is absent. A skip is only
legitimate when the caller asked for it. Same class of bug as trusting a printed counter
(§6): the gate must observe the *output*, not the intent.

## 31. `set_actor_location` can be a no-op on a component-less actor

**Symptom:** `MotorTownRaceSection` gates: `set_actor_location` + `set_actor_rotation`
returned without error, the script reported `placed=40`, and a re-read showed all 40
still at `(0,0,0)` (`GATE_PLACE_FAIL`).

**Cause:** not established; the actor class carries no components at all, so there is
nothing for the transform to move and the write does not persist.

**Fix applied:** deleted the actors instead of positioning them (they are not required
by the map).

**Rule:** after any transform write, re-read the value in the same process and include it
in a gate. `set_*` returning cleanly is not a write (same trap as §6, §17).

## 32. Ported lights: unitless intensity and sRGB colour (2026-11-06)

Four separate defects presented as one symptom — "the lights are too dim / too red / not on the
poles" — and three of them were unit errors, not lighting bugs.

**Symptom 1 — a brightness ladder where every rung looked wrong.**
Lamps at 20000 unitless read as a match flame; 200,000 still looked dim; the ladder
60k / 200k / 600k / 2,000,000 produced "all of them too bright" and "still dim" in the same session.

**Cause:** the two engines were never in the same unit.
- BeamNG: `SpotLight` intensity is **candelas**, `PointLight` is **lumens**, and the legacy
  `brightness` fallback is **1 brightness ≈ 5,000 cd (spot) / ≈ 62,832 lm (point)**; `range` only
  clamps an inverse-square falloff.
- UE: point/spot accept Candela / Lumen / Unitless, with **1 cd = 625 unitless**.

So 200,000 unitless ≈ **320 cd** — ~30× *dimmer* than the 10,000 cd that brightness 2 actually
means, and the 2M rung only reached ~3,200 cd. There was no value on the ladder that corresponded to
the source lamp, which is why the reports conflicted.

**Fix:** set `intensity_units = CANDELAS` (LUMENS for point lamps) and compute from the source:
`cd = brightness × 5000`, `lm = brightness × 62832`, `attenuation_radius = range_m × 100`.
Result on 2,169 lights: 10,000 cd ×1,083, 7,500 ×107, 5,000 ×623, 62,832 lm ×356.

**Symptom 2 — "they're all too red".**
Source colour `[1, 0.392, 0, 1]` written into `unreal.Color` came out as `(255,100,0)`.

**Cause:** source colours are **linear RGBA**; `unreal.Color` / the `light_color` editor property is
**sRGB**. Turning a linear value into a byte by multiplying by 255 saturates the hue.

**Fix:** convert `s = 12.92x if x <= 0.0031308 else 1.055·x^(1/2.4) − 0.055`, then ×255. Linear
0.392 → sRGB 168, not 100. The amber then reads as amber.

**Symptom 3 — `/lampcolor` turned the lamps black.**
`SetLightColor({r=…, g=…, b=…}, true)` via UE4SS produced a black light.

**Cause:** the Lua table did not cross into `FLinearColor` as anything but zero. Not a setter defect —
a marshalling one, and it silently *succeeded*.

**Rule:** never conclude "runtime colour control works" from a call that returned without error. Read
the component's colour back in the same call, and treat "the light went black" as a zeroed struct
before blaming the engine.

**Symptom 4 — per-lamp values could not be expressed.**
One `BP_C1_Lamp` produced identical lamps; trying to vary intensity per instance changed nothing.

**Cause:** a blueprint's light component is a **class default**. Every instance of the BP shares it,
and per-instance component overrides are not reliably cooked (a per-instance `visible=true` was lost).

**Fix:** when rows differ, author **native** `unreal.SpotLight` / `unreal.PointLight` actors — their
component properties serialise per actor. Keep a blueprint only for a lamp type that is genuinely
uniform. Consequence: after converting to native actors the level no longer references
`BP_C1_Lamp`, so the BP drops out of the cook (`MISSING Blueprints/BP_C1_Lamp`) and the pak contains
only the map. That is correct, not a regression.

**Rule:** choose the primitive from the data, not from convenience — uniform lamps can be a BP,
per-row lamps must be native actors.

**Docs:** BeamNG `documentation.beamng.com/modding/lighting/pbl` + `/lights/`; Epic *Using Physical
Lighting Units*. Skill: `motortown-map-lighting`, `references/light-units-beamng-to-ue.md`.

## 33. "Just delete them" vs find the real config — sign lights (2026-11-06)

**Symptom:** after the corridor port, lamps beside signs were white and blown out.

**First hypothesis (wrong):** the 356 corridor `sign_lights` carry no brightness, range, colour or
cone angles in the source, and every one is `isEnabled: false` — so they look like inert
placeholders, and the tempting fix is to drop them.

**What the level actually does:** `levels/c1/mainlevel.lua` builds a partition grid (384 m cells)
over `lightGroupNames = {"Tunnel_lights","Tunnel_sounds","sign_lights","LightGroup1", …,
"garage_japan_unpacked"}` and calls `light:setLightEnabled(value)` per cell as the camera moves, with
`texSize` raised to 256 when enabled. So the group *is* live; `isEnabled:false` in the file just
means "off until the manager says otherwise" — true for the street lamp groups too.

**What the objects specify:** position, `texSize: 32`, `flareScale: 0`, `animate: false`,
`locked: true`. Nothing photometric. They run on **PointLight class defaults**.

**Why the port blew out:** the class default is legacy `brightness 1`, converted at the documented
rate to **62,832 lm** (the isotropic equivalent of a 5,000 cd spot). BeamNG's own guidance for a
point light of this kind is **400–1,000 lm at radius 5–12 m**. We ported the class default literally,
~60× too strong, and it clipped to white against Motor Town's exposure. BeamNG absorbs it; UE at MT's
exposure does not.

**Fix:** keep the lamps, give value-less ones a documented small-point-light default (800 lm, 8 m)
instead of the legacy-brightness default.

**Rules**
- **"No values in the file" is not "no light".** Before deleting a group, grep the level's Lua for its
  group name and for `setLightEnabled`; a runtime light manager is common in converted levels.
- **Class defaults are config too.** Port them deliberately, and sanity-check the magnitude against
  the engine's own guidance table rather than only against the unit-conversion formula.
- **A unit conversion can be arithmetically right and operationally absurd.** 62,832 lm is the correct
  conversion and the wrong light. Cross-check any converted value against the docs' recommended range
  for that fixture type.

**Separate defect found in passing (not the cause):** sign materials declare only `colorMap` and
`alphaRef` — no roughness map — yet **1,638 of 1,653 material instances carry `Roughness = 0.65`**,
and only 217 of 1,605 source materials declare roughness at all. That constant is invented during the
material build, so every ported surface has a specular lobe the source never asked for. Flat signage
should be fully rough (1.0). Worth a material pass; it did not cause the white lamps.

## 34. Two features in one sublevel evict each other (2026-11-07)

`c1/tools/c1_bake_nav.py` and `c1/tools/author_corridor_lights.py` both load
`/Game/Mods/C1Full/Maps/C1Full_Roads` and save it. Each cook therefore produced its own copy of
that ONE asset, and pak mounting keeps exactly one copy per asset (last-alphabetical filename
wins). Installing the nav test pak at `zzzzzzzz_` over the lights pak at `zzzzzzz_` silently
replaced the lit roads sublevel with the nav one: **the lights disappeared** with no error at all,
ten minutes after they had been confirmed working.

Fix: the lights live in their own sublevel, `C1Full_Lights`, attached to the persistent
`C1Full.umap` as **Always Loaded** (`LevelStreamingAlwaysLoaded`), and the lights pak ships
`C1Full.umap` + `C1Full_Lights.umap` but **never** `C1Full_Roads`
(`c1/tools/build_lightspak.sh` fails if it leaks in). Nav keeps `C1Full_Roads`.

Rules that follow — **one level asset, one pak**, enforced by `c1/tools/build_levelpak.sh`:

| asset | owner pak | contents |
|---|---|---|
| `C1Full.umap` | map pak (`zzzzzz_AMC_C1Map_v2`) | persistent level; the only place the sublevel references live |
| `C1Full_Lights.umap` | lights pak (`zzzzzzzzzz_AMC_Shuto_Lights_v10`) | all 10,474 light actors |
| `C1Full_Roads.umap` | nav pak (`zzzzzzzz_AMC_C1NavTest_v2`) | roads + nav graph |

The script takes exactly one stem and fails if a second level asset appears in the staging dir.

**Materials are their own pak too** (`zzzzz_AMC_C1Mats_P*`, all 1,653 instances). An experiment
that changes a material instance must be folded INTO that pak, never shipped as a second mats pak:
two paks claiming the same MI is the same shadowing bug, only silent at the shader level. The
roughness trial (4 road MIs moved to `MI_GroundMaster` with a real `Roughness` texture) was
delivered as its own pak first; that was wrong and it was folded into `P21`.
A nav pak that also shipped `C1Full.umap` evicted the sublevel reference on filename sort alone
and the lights vanished again — that is a build error, not a sort-order policy to manage.
- Always-Loaded by streaming class, not by a `b_always_loaded` property: that property does not
  exist on `LevelStreamingAlwaysLoaded` in this build (`Failed to find property 'b_always_loaded'`).
- Sublevels are for packaging isolation, **not** performance. Streaming corridor lights by distance
  makes them pop while driving. The perf problem (10,474 lights) is a separate, still-open question
  and BeamNG's answer to it is a 384 m partition manager that toggles lamps inside one loaded level.

## 35. A fresh cook path silently skips stage 6 and the map loads with "missing game mode" (2026-11-07)

Cooking the map and packing it directly shipped a map that loaded with **missing game mode**, no
sky and no garage. A cooked mod map carries **no `WorldSettings.DefaultGameMode`, no
`SunSky.ChildActorClass` and no `Child.ChildActorClass`** until `c1/pipeline/06_postcook_patch.sh`
(`repair_class_refs.sh`) restores them as property references — that is what the stage exists for,
and any build path that does not run it produces exactly this failure.

`c1/tools/build_lightspak.sh` now greps the `.umap` for `DriveGameModeBP`, `MTSunSky` and
`GarageActorBP` and refuses to pack without all three. Verify with bytes, not by assuming the
pipeline ran: `repair_class_refs.sh` printing `REPAIR_OK` is the last step of the fix, but the pack
gate is what stops the next silent regression.

Also: `repair_class_refs.sh` must be pointed at the tool that actually has `--set-class-ref`
(`TOOL=` env). The stale copy under `mt-pak-wt-c1commit/csharp/UAssetTool/bin/...` fails with a
confusing `File not found: <rootdir>/Cargos.uasset` instead of an unknown-argument error.
