# Motor Town map porting — end-to-end guide

How to take an external map (BeamNG mod, hand-authored level, anything with road
geometry) and turn it into a Motor Town map mod that loads in single-player and on a
dedicated server with working AI traffic.

This is the *portable* procedure. The C1 Shuto specifics (constants, counts, lane
formulas) stay in [`C1_PIPELINE.md`](C1_PIPELINE.md); the executable per-build gates
are in [`../C1FULL_BUILD_CHECKLIST.md`](../C1FULL_BUILD_CHECKLIST.md); the numbered
hard-won traps from the C1 port are in [`C1_PORT_LESSONS.md`](C1_PORT_LESSONS.md)
(and in full in [`../GOTCHAS.md`](../GOTCHAS.md)). Read the lessons file before
changing anything here — it exists so these are not rediscovered at the cost of a day.

Everything below is written for a map called `<MAP>` living at
`/Game/Mods/<MAP>/`, with content (meshes/materials/textures) possibly shared from
another namespace. Substitute as needed.

---

## 0. What a MT map mod actually is

A map mod is not just a `.umap`. The game needs five separate things, and a build is
only correct when all five are present:

1. **A parent map** (`/Game/Mods/<MAP>/Maps/<MAP>`) — the level the game opens. Holds
   the `WorldSettings` with the game-mode override, the sky, the garage, the player
   start, and a `LevelStreamingAlwaysLoaded` reference to the sublevel.
2. **A streamed sublevel** (`<MAP>_Roads`) — owns the `MotorTownRoad` actors (the
   spline that AI drives on), the baked `MotorTownNavigation` graph, and the
   `AMTAIVehicleSpawnSystem`.
3. **Geometry** — static mesh tiles placed as actors in the parent map. C1Full places
   554 tiles; the C1 corridor places 75.
4. **Content chain** — meshes → material instances → materials → textures. All four
   must resolve *inside the pak* or the meshes render as nothing (see §5.1).
5. **Registration paks** — a `GameResource` override that adds the map to
   `DriveMaps` / `TimeAttackMaps`, and a `Courses` override for the race row and its
   display name. These mount at `../../../` (vanilla paths), not inside the mod folder.

Miss any one and the symptom is dramatic and misleading: blank world, invisible
geometry, or a map listed under the wrong name.

### Namespacing rules

- **Pak identity = mount point + package paths**, not filename. Two paks mounting the
  same packages silently collide, and the one that sorts **later** wins.
- A named mount (`../../../MotorTown/Content/Mods/<MAP>/`) can only satisfy paths under
  that folder. If your assets reference `/Game/Mods/Other/Textures/...`, either ship
  that namespace too (mount `../../../`, include both trees) or don't ship.
- **Do not rename a content namespace after authoring.** Every material instance's
  texture parameter is a package reference; moving `Materials/`, `Meshes/`,
  `Textures/` to a new namespace leaves those references pointing at the old path,
  the cook serialises them as `null`, and masked materials then render as nothing.
  If the namespace must change, rebuild the content from the source project, do not
  patch references afterwards (see §5.1 and §5.2).

---

## 1. Stage map

| # | Stage | Runs on | Output | Gate |
|---|-------|---------|--------|------|
| 0 | env | anywhere | paths, tool locations | tools resolve |
| 1 | road specs | container | `road_specs.json` | road count, total km |
| 2 | geometry import | editor | tiles as meshes | mesh count + material slots |
| 3 | level assembly | editor | parent map + sublevel | cell actors, no hidden |
| 4 | road authoring | editor | `MotorTownRoad` actors | `AUTHORED=n FAILED=0` |
| 5 | nav bake | editor | `GraphData` | 4 counts, `dead_ends == 0` |
| 6 | spawner | editor | `AMTAIVehicleSpawnSystem` | row count, service rows zeroed |
| 7 | cook | Windows | cooked map pair | `LogCook: Done!`, `.uexp` size |
| 8 | post-cook patch | anywhere | patched map pair | class refs + VehicleClass |
| 9 | pack | anywhere | `.pak` | file count, mount, round-trip sha |
| 10 | registration | anywhere | `GameResource` + `Courses` paks | names present, array counts |
| 11 | install + verify | client / staged server | paks in place | sha match + in-game |

Rule: **never skip a gate.** Every regression in §5 was a skipped or silently-failing
gate, not a mystery.

---

## 2. Stages in detail

### 2.1 Road specs (stage 1)

Extract the source map's AI path data into road specs: per road, an ordered polyline,
declared lane counts, widths, and one-way flag. For BeamNG that is
`levels/<map>/main/missiongroup/ck_ai` → `DecalRoad` actors.

```bash
bash c1/pipeline/01_decal_specs.sh        # -> road_specs_v2.json
```

Gate: road count and total length match the source. C1Full: **155 roads / 209.72 km /
6,040 points**.

Pitfalls:
- Units: BeamNG is metres, Unreal centimetres. A 100× transform error looks like
  "scaled to the moon" actors, not like a unit bug.
- Declared lanes lie. Audit `lane_width` **before** believing any lane complaint;
  width > ~400 cm usually means an under-declared carriageway.
- Never merge dual carriageways. Opposed pairs are identified by midpoint **tangent
  dot = −1** with separation below `(wa+wb)/2`, sustained — never by closest point.

### 2.2 Geometry (stage 2)

Tiles from the source map are converted to meshes and imported, then placed as
`StaticMeshActor`s at world coordinates (the mesh geometry itself carries world space,
so actors sit at origin).

Gate: mesh count == tile count, every actor has a mesh, **zero hidden actors**, every
material instance the meshes use has an **MT master as its parent** (§5.0), each mesh
has **collision data**, and the whole set's **cooked bounds** match the source bbox:

```
cells=554  hidden_actor=0  hidden_in_game=0  component_invisible=0
MI parent = M_PropMaster | M_PolygonMaster | M_DecalMaster   (never a mod-owned master)
bounds_km  x -1.5..3.6  y -10.5..1.6  z 0..1.2      (0 tiles outside the map area)
```

Bounds are non-negotiable: the OBJ importer negates Y, and component transforms do not
move world-space geometry, so a mirrored or unshifted import looks perfectly fine in the
editor list while sitting kilometres away at runtime. Compare **cooked asset bounds**
against the source bbox axis by axis (`C1_PORT_LESSONS.md`, gotchas 22/23).

**LODs: project decision — none.** The shipped C1Full build uses LOD0 only. Note that
there is no Python API that deletes LODs (`get_num_lods` exists, there is no setter or
remove on `StaticMeshEditorSubsystem` in this build), so an earlier LOD pass can only be
undone by re-importing those tiles single-LOD. Check with
`sm.get_num_lods()` and also verify the LODs aren't empty (`get_num_triangles(i) == 0`
for `i > 0` makes tiles vanish at distance — that is a real failure mode, distinct from
having LODs at all). Deleting the asset *before* importing is what actually yields a
single-LOD asset: `replace_existing=True` on a multi-LOD asset rewrites **LOD0 only** and
keeps the extra levels.

**Scale gate — the one that matters most.** Cell OBJs are authored in metres; Unreal
imports 1 unit = 1 cm. If `import_uniform_scale = 100` fails to land, every tile ends up
**100× too small** and the whole map collapses into a miniature clustered near the
origin: nothing visible where the roads are, nothing to stand on, and no error anywhere.
It reads exactly like "geometry missing". The catch is cheap — **compare the union of
mesh bounds against the road spline bounds**:

```
roads   x -1,104,777..611,734 cm   y -1,002,062..1,658,899 cm   z 82,367..92,004 cm
meshes  must be the same order of magnitude (a union spanning a few km instead of ~20 km
        means the scale never applied)
```

The same failure shows up per tile: `c-10_-21`'s OBJ sits at x = −5,068.62 m, so the
correct asset bound is **−506,862 cm**. Getting −5,068 cm means the import is 100× small.
`import_uniform_scale` must be set on `static_mesh_import_data`; the property silently
fails to apply elsewhere, so assert the imported bounds rather than trusting the option.

Hidden actors are worth checking explicitly — a cell can be present, correctly
assigned and invisible at the same time.

### 2.3 Level assembly (stage 3)

Build the parent by **loading the existing level**, not creating a new one: that keeps
the course gates, sky, garage and streaming reference already in it.

Gate: cell actor count == tile count, road actor count == road count.

Never use `rename_asset` on a map. It produces an empty 787-byte shell because the
level's actors live in the package's map data, not the asset registry entry. To move a
map: **delete the destination, then `save_map` into it**.

### 2.4 Roads (stage 4)

Spawn one `MotorTownRoad` actor per spec road in the sublevel, set the spline
(4 sub-curves must share the key count), lane counts, one-way direction, speed limit,
`RoadFlags` (AI enabled — not `NoAI`), and `SplineBounds`.

Gate: `AUTHORED=<n> FAILED=0`.

Left-hand traffic is not a flag: it is the **travel-frame reversal** of the spline
direction plus the lane numbering. Getting it wrong produces cars driving on the wrong
side while the map otherwise looks fine.

### 2.5 Nav bake (stage 5)

Bake the graph deterministically: roads sampled **sorted by actor label**, so node
indices are stable for a given level + constants.

```bash
bash c1/pipeline/03_bake_nav.sh
```

Gate (C1Full baseline): `nodes 42,578`, `cross_links 10,167`,
`lane_change 42,700`, `dead_ends 0`.

- `dead_ends == 0` is the only graph property that has predicted in-game behaviour.
  Treat a non-zero count as a build failure.
- Counts live in `constants.json`. Drift after a road-set change is expected —
  re-record the baseline in the same commit. Drift *without* a road-set change means
  something moved.

### 2.6 Spawner (stage 6)

Author `AMTAIVehicleSpawnSystem` in the sublevel with one row per vehicle class
(`Small`, `Special`, `Truck`, `Bus`, service rows). Service and Getaway rows must be
`MaxCount = 0` unless explicitly wanted — getaway vehicles are not acceptable content.

Gate: expected row count; all service rows zeroed.

### 2.7 Cook (stage 7)

Cook from the **mirror client project** for the Windows target. A WindowsServer project
yields a stub `.uexp`.

Gate: `LogCook: Display: Done!` **and** a plausible `.uexp` size. Judge by the log line
and the output mtime, never by exit code — the cook returns `rc=1` on a pre-existing
Water Body collision-profile warning while succeeding.

Also gate the **shader platform coverage**: with no `TargetedRHIs` in `DefaultEngine.ini`
the cook emits SM5 only, while the game runs SM6, and every custom material silently
renders as the default material with no log. Set both `PCD3D_SM5` and `PCD3D_SM6`, then
confirm the platform strings are present in a cooked master. And stop Nahimic
(`NahimicService`, `NahimicSvc64.exe`) before cooking — it crashes `ShaderCompileWorker`
and nothing compiles at all.

```
C1Full : C1Full_Roads.uexp   60,740,498 B      C1Full.uexp   156,625 B
C1     : C1_Roads.uexp       15.9 MB (54 roads)
```

A ~800 B `.uexp` means the sublevel saved empty — go back to §2.3.

### 2.8 Post-cook patch (stage 8) — mandatory, every cook

**The cook drops all of these.** They are asset-level edits the editor never
re-serialises, so they must be re-applied to every cooked build. This is the single
biggest source of "it worked last time" regressions.

Two maps, two different fixes — mixing them up fails loudly (`no export named SunSky`):

- **Parent map** — `pipeline/repair_class_refs.sh`:
  `WorldSettings.DefaultGameMode → DriveGameModeBP_C`,
  `SunSky.ChildActorClass → MTSunSky_C`,
  `Child.ChildActorClass → GarageActorBP_C`.
  These must be **property references only, never baked actors** (baking
  `MTSunSky_C_0` / `GarageActorBP_C_0` instances crashes on load).
  Gate: 3 refs present (6 dump matches), no `_C_<n>` instances.
  **Missing this = blank world, no player controller, no game mode.**

- **Sublevel** — `--set-array-class-ref ... SpawnSettings SettingKey VehicleClass`,
  which writes the vehicle-class imports the spawner rows reference.
  Gate: one `/Game/Cars/Models/...` ref per traffic row.

Operational requirements:
- `.umap` and `.uexp` must be **beside each other** with matching basenames, and paths
  must be absolute. A map without its `.uexp` parses as garbage
  (`count ('-156621') must be a non-negative value`).
- .NET 10 needs `DOTNET_ROLL_FORWARD=Major` and
  `DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1` or it aborts on ICU/timezone init.
- **Do not hardcode the export name.** `MTAIVehicleSpawnSystem_0` becomes `_1` after
  re-authoring. Dump the map, grep `Name=MTAIVehicleSpawnSystem_[0-9]+`, use that.

### 2.9 Pack (stage 9)

`mod_pack` in this tree has no compression flag (writes stored entries). Use `repak`:

```bash
RAYON_NUM_THREADS=1 repak pack -m "../../../" --version V11 --compression Zlib -q tree out.pak
```

`RAYON_NUM_THREADS=1` is required for reproducible output. UnrealPak `-Create`
produces unreadable paks on this engine build — do not use it.

Gate: `mod_explore --list` → expected mount, expected total file count, expected
per-directory counts; extract the maps back out and compare sha256 with the tree copies.

### 2.10 Registration (stage 10)

`GameResource` holds `DriveMaps` and `TimeAttackMaps` as **separate arrays** with no
game-mode field — the mode comes from the level's `WorldSettings` (`DriveGameModeBP`).
To make a map available as Time Attack with normal driving, register the **same level
in both arrays**.

Each entry needs `Key`, `Level{package,asset}`, `bDevWorld`, `bAvailableInDemo`, the
`WorldMap` block, and — critically — a **`Name` text**. An empty name makes the game
fall back to the course template's name (the "Town Circuit" symptom).

`Courses` needs a row per map with a `Name` text too, plus `bUseOffTrack` / XP fields.

Text gotcha: `set_display_name` only works on the struct-wrapped name type used by
parts/tires; on a plain `TextProperty` it **silently no-ops**. Use `set_description`,
which writes a culture-invariant `TextProperty`. Then verify the string is actually in
the `.uexp` — the tool reports success either way.

```jsonc
{"op":"append_struct_clone","path":"DriveMaps","template_index":0,"fields":{...}},
{"op":"set_description","path":"DriveMaps[12].Name","value":"<Display Name>"}
```

Every JSON value the tool reads must be an array-shaped config — a stray `_comment`
string aborts the whole run.

### 2.11 Install and verify (stage 11)

- Back up every `*.pak` (excluding the ~2.8 GB vanilla) with a SHA256 manifest and
  re-hash each copy before overwriting.
- Install, then verify `SHA_MATCH` per file.
- **Remove or retire anything that sorts after your pak and mounts the same
  namespaces** — otherwise the build is not deterministic and you will debug a
  phantom.
- In-game acceptance: listed under the right name, loads into the intended game mode
  with a controllable player, geometry visible **and textured**, traffic present.

---

## 3. Determinism contract

Reproducible: road specs (sorted), node/edge indices (sorted actor labels), graph
counts, patched property values, pak file list, patched map sizes.

**Not** reproducible: pak byte hashes and cooked asset bytes (the cook embeds build and
timestamp data), and any tool step that reports success without writing (see §5.2).

Therefore: verify **content**, never pak hashes across rebuilds. Keep a
`constants.json` baseline and fail the build on unexpected drift.

---

## 4. Rebuild loop in practice

```
bake → read the 4 counts → unchanged? stop, do not cook
     → cook → pull map pair → patch (both maps) → pack → verify contents
     → install → in-game check
```

Stopping when the counts do not move is what prevents shipping a placebo build.

---

## 5. Failure catalogue

Symptom → cause → fix. Every entry here cost real time; they are ordered by how much
they mislead.

### 5.0 Checkerboard / "materials aren't applied": four separate causes, in likelihood order

**This section has been wrong three times. Everything below is anchored to a measurement.**

#### 5.0.1 Materials the meshes reference but which do not exist (most common)

Before any theory about shaders, count. For every mesh, extract the
`/Game/Mods/<root>/Materials/MI_*` paths it references and check each one exists in the pak.
On C1Full the answer was **30 missing**, and they were the biggest surfaces:

```
MI_C1_mat_wal            99 meshes     MI_C1_mat_saku      81
MI_C1_mat_camera         64            MI_C1_mat_camerapilar 64
MI_C1_mat_fence          40            MI_C1_sign           28
(+ 24 more)
```

Those slots draw the engine default in **every** build — including ones that "worked" —
because the instance named by the mesh was never created. Each missing name had a surviving
sibling (`MI_C1_mat_wal` → `MI_C1_mat_wal_15`, `MI_C1_mat_box` → `MI_C1_mat_box_1`), which is
how they were restored: clone the sibling, keep the name the mesh expects. Gate: **coverage
must be zero missing**, counted per mesh, never eyeballed.

#### 5.0.2 The sky/GameMode blueprints not shipped (looks identical to 5.0.1)

The level's sky is `BP_C1_Sky_C_0`, whose `SunSky` child component lives in
`/Game/Mods/<root>/BP_C1_Sky`. Because the packer copied only `Materials/ Maps/ Meshes/`, the
**loose root blueprints were absent from the pak**: no sky actor, no sun, no skylight, every
surface unlit. Unlit geometry is indistinguishable from "materials not applied" on a
screenshot. Gate: every `/Game/Mods/<root>/…` import in the map must resolve inside the pak,
including assets that sit at the namespace root.

#### 5.0.3 Custom masters can never render — shader code cannot ship

MT stores material shader code in `ShaderArchive-<lib>-<platform>.ushaderbytecode`, and only
two exist: `Global-PCD3D_SM5` (13,242,450 B) and `MotorTown-PCD3D_SM5` (56,636,716 B). There is
no SM6 archive, so MT runs SM5. A cook of our project emits the same two names but partial
(13,181,977 B / 6,186,317 B); mounting them shadows MT's files and the client dies at boot with
`LowLevelFatalError [GlobalShader.cpp:803] Could not load section 11 (of 330) of the global
shadermap`. **Therefore an instance parented to a master we ship has no shader code MT can
load, no matter how cleanly it compiles.** Instances of MT's own masters only.

Compiler sanity is still worth checking, because it separates a bad asset from a bad plan: a
master that never compiled cooks at **~3.6 KB with zero shader strings**; a compiled one is
**17–32 KB with `PCD3D_SM5`/`PCD3D_SM6` and `TBasePass*` names**. Compiling requires
`TargetedRHIs` in `DefaultEngine.ini`, and repairing a broken master never works — rebuild it
(`M_C1_Tex2`, `M_C1_TexMasked2` are the rebuilds that kept the original parameter names).

#### 5.0.4 Parameter type mismatches on a valid parent

For `M_PropMaster` (proven from its `TextureStreamingData`, which lists exactly two textures,
`T_Normal_N` and `T_White_BC`):

```
BaseColor  texture      Normal     texture
Metallic   scalar       Roughness  scalar
Specular   scalar       UV_Tiling  scalar
```

Writing a Texture2D into `Metallic`/`Roughness` produces an instance that fails to compile and
draws checkerboard. Drop those parameters and let the scalar defaults apply.

#### The recipe that actually shipped

The old C1 material pak is the reference implementation: **1,609 instances, zero masters**,
every instance parented to `/Game/Env/Materials/Master/M_PropMaster`, `BaseColor` as the only
texture parameter, `Metallic`/`Roughness` scalars. Ship that shape.

#### Instrumentation lesson

`GetMaterial(0)` returned the assigned instance for 628/628 components, `parent_nil=0`, and the
probe reported zero default-material fallbacks, while the screen was solid checkerboard —
because assignment succeeds and only rendering fails. A clean probe is not proof. Conversely,
UE4SS cannot call `GetTextureParameterValue` (`TrivialObject` error), so parameter values are
not observable at runtime; verify them in the asset, not in-game.

#### And check the simpler things first

Both earlier "invisible geometry" incidents were not material problems: one was a texture
namespace rename (§5.1), the other was every tile imported **100× too small** (§2.2). No
collision means geometry, not materials.

and blend/mask mode genuinely match, and only per material — never as a bulk rewrite.

**And check the simpler things first.** Both "invisible geometry" incidents in this project
were *not* material problems: one was a texture namespace rename (§5.1), the other was
every tile imported **100× too small** (§2.2). A material whose texture parameter is null
still renders (grey); geometry that is 100× small or absent gives no collision and no
silhouette. If there is no collision, it is geometry, not materials.

**Why a separate "mats pak" is a trap.** The corridor release shipped an override pak
(`zzzz_AMC_C1Mats_P.pak`) carrying an MI set on top of a content pak with a different one.
The override sorted later and won, so it worked — until it was retired during cleanup and
the map silently lost the winning set. **Whatever the pak identity of the MIs, one pak must
contain the full picture: the MIs *and* every master they name.** Splitting them across a
content pak and an override pak means the two can drift, and a later-sorting pak silently
decides the result.

### 5.1 Map loads, geometry invisible outside one area, "materials missing"

**Cause.** Material instances' texture parameters pointed at a namespace that no longer
existed after a rename. The cook serialised `ParameterValue = null`; those materials are
**masked**, so a null base texture clips the mesh to nothing. Invisible geometry, not
missing geometry.

**Diagnosis.** Compare cap counts (a working build had 6,611 texture files, the broken
one 0). Look for `Skipping non mounted imported package /Game/Mods/<old>/Textures/...`
in the editor log. Scan a cooked MI for the texture path string — if it isn't in the
`.uasset`, the reference is gone.

**Fix.** Restore the referenced namespace and re-cook. Do not try to repair the MIs in
place: see §5.2.

**Cook may not export every referenced texture.** In this project a cook emitted **774**
texture assets while the MIs referenced **1,993** — 1,550 unresolved, and the pak still
"worked" (grey surfaces, no error). Textures are stable across geometry work, so take the
texture tree from the last known-good build instead of trusting the cook, and gate it:

```
referenced = every "/Game/Mods/<MAP>/Textures/..." string inside the MI assets
present    = every .uasset under Content/Mods/<MAP>/Textures
gate:      missing == 0 (or a short, explained list)
```

### 5.2 Asset property writes report success but never persist

**Cause.** On material instances (texture parameter overrides) and on static meshes
(`static_materials`) in this project, `set_editor_property` / 
`MaterialEditingLibrary.set_material_instance_texture_parameter_value` mutate the
in-memory object, `save_loaded_asset` returns `True`, and the value is **gone on
reload**. The MIC setter also returns `False` while appearing to work.

**Detection.** Always verify from a *fresh process*: reload the asset and compare. A
save that "succeeds" is not evidence.

**Fix.** Change the thing the property points at, not the property: restore the asset
at the path the reference already names, or repoint the *actor* (actor properties do
persist), or rebuild the asset by duplication/import from the source project.

### 5.3 Blank world, no player controller, no game mode, no HUD

**Cause.** Cooked parent map has no `WorldSettings.DefaultGameMode` (and usually no
SunSky/Garage refs). The cook drops them every time.

**Fix.** §2.8 parent patch. Verify by dumping the cooked map and grepping
`DriveGameModeBP_C`.

### 5.4 Map listed as "Town Circuit" (or another map's name)

**Cause.** The `GameResource` entry's `Name` text is empty → fallback to the course
template the row was cloned from. Or the text write silently no-opped (§5.2 style:
`set_display_name` on a plain `TextProperty`).

**Fix.** `set_description` on `DriveMaps[n].Name` and `TimeAttackMaps[n].Name`, plus
the `Courses` row's `Name`. Verify the string exists in the `.uexp`.

### 5.5 Map renamed/moved, level comes up empty

**Cause.** `rename_asset` on a `.umap` only moves the asset shell (787 B); the level's
actors stay behind.

**Fix.** Delete destination → `save_map` into it, then re-verify actor counts.

### 5.6 Sublevel cooks as an ~800 B stub

**Cause.** Cooking the wrong target (WindowsServer) or a map that saved empty.

**Fix.** Cook from the mirror client project; check `.uexp` size, not exit code.

### 5.7 Cook exits `rc=1` but reports `Done!`

**Cause.** Pre-existing `Water Body Collision profile` warning in the project's
`DefaultEngine.ini`. Not related to the map.

**Fix.** Judge the cook by `LogCook: Display: Done!` and output mtime.

### 5.8 `Unable to open pak file` after packing

**Cause.** UnrealPak `-Create` on this engine build produces a pak the game cannot read.

**Fix.** `repak` with `-m ../../../ --version V11 --compression Zlib`, `RAYON_NUM_THREADS=1`.

### 5.9 `set-array-class-ref` aborts with a schema error

**Cause.** A non-array value anywhere in the JSON config (a `_comment` string).

**Fix.** Every value must be array-encoded; keep comments out of tool configs.

### 5.10 `--set-array-class-ref` fails: export not found

**Cause.** Hardcoded `MTAIVehicleSpawnSystem_0`; re-authoring renames it to `_1`.

**Fix.** Dump the map, auto-detect the export name.

### 5.11 Map parses as garbage: `count ('-156621') must be a non-negative value`

**Cause.** `.umap` copied without its `.uexp` sibling (or non-absolute path).

**Fix.** Keep the pair together; pass absolute paths.

### 5.12 `.NET` aborts with a `TimeZoneInfo` stack trace

**Cause.** Missing globalization invariants on .NET 10.

**Fix.** `DOTNET_ROLL_FORWARD=Major`, `DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1`.

### 5.13 `duplicate_asset` "creates" thousands of assets that never appear

**Cause.** Duplication is registered in memory only; nothing is written unless the
process saves each package.

**Fix.** Copy on disk / re-import from the source project instead.

### 5.14 A build works, the next cook silently loses a patch

**Cause.** §2.8 — cook drops map-level patches. Every rebuild must re-apply them.

**Fix.** Run stage 8 on every cook; never treat it as a one-time fix.

### 5.15 Two paks fight and the wrong one wins

**Cause.** Pak identity is mount + package paths; the pak sorting later wins. An old
content pak mounting `Mods/<X>/` overrides the new one.

**Fix.** Retire superseded paks during testing; keep exactly one pak per namespace.

---

## 6. Copy-paste checklist

**Authoring (editor)**

- [ ] roads authored: `AUTHORED=n FAILED=0`
- [ ] bake: nodes/cross_links/lane_change recorded, `dead_ends == 0`
- [ ] spawner: expected rows, service/Getaway `MaxCount = 0`
- [ ] level: cell actors == tiles, 0 hidden, 0 invisible components
- [ ] materials: every MI texture param resolves (fresh-process check)
- [ ] **materials: every MI's parent is an MT master** (`M_PropMaster` / `M_PolygonMaster` /
      `M_DecalMaster`) — a mod-owned master renders nothing at runtime (§5.0)
- [ ] the content pak itself carries those correctly-parented MIs (no override pak)

**Build**

- [ ] cook from mirror client project → `LogCook: Done!`, `.uexp` plausible
- [ ] parent patch: 3 class refs, no baked `_C_<n>` instances
- [ ] sublevel patch: VehicleClass refs, export name auto-detected
- [ ] both maps patched as `.umap` + `.uexp` pairs
- [ ] pack: correct mount, expected file counts, round-trip sha match

**Registration**

- [ ] `GameResource`: `DriveMaps` and `TimeAttackMaps` both contain the map
- [ ] both entries carry the display `Name` (present in `.uexp`)
- [ ] `Courses` row exists with its own `Name`

**Install**

- [ ] backup + hash manifest of existing paks
- [ ] installed files `SHA_MATCH`
- [ ] no other pak mounts the same namespaces
- [ ] in-game: correct name, intended game mode, player controllable, geometry
      visible **and textured**, traffic present
