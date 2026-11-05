# C1 port — lessons recovered from the thread (cross-check)

Purpose: a single place that reconciles the 3–4 days of C1 work with the portable
[`MAP_PORTING_GUIDE.md`](MAP_PORTING_GUIDE.md) and
[`../C1FULL_BUILD_CHECKLIST.md`](../C1FULL_BUILD_CHECKLIST.md). If a rule here is not in
one of those two documents, the documents are wrong — fix them, don't re-derive this.

Sources: `../GOTCHAS.md` (numbered entries), `../CHECKLIST.md`, `C1_PIPELINE.md`,
`../pipeline/README.md`, `../pipeline/constants.json`.

---

## Already established before this session — do not rediscover

### Geometry import

- **OBJ is metres, Unreal imports centimetres** → `import_uniform_scale = 100.0`. *(GOTCHAS 1)*
- **Some BeamNG placements mix metres and centimetres**; classify by distance from the
  tile median and divide/multiply by 100. 9.8% of vertices needed it; 0 unmatched. *(2)*
- **The OBJ importer negates Y** and reverses winding. Pre-negate Y in the OBJ
  (`y = -y`) so the flip cancels. Detect by comparing **cooked asset bounds** against
  source bbox axis by axis — comparing meshes to splines in source space can never catch
  it, both are mirrored. *(23)*
- **Component `RelativeLocation` does not move what renders** — these components come
  from an actor chain and the vertices already carry world space. Bake offsets into the
  **OBJ vertices** (cm ÷ 100), leave components at `(0,0,0)`. *(22)*
- **Spawn placement is a geometry property, not an actor property:** the map must
  *contain* the origin (spline **centroid** at origin), not merely touch it. *(19, 21)*
- **Cell actors can be `bHidden`.** A `--drop-mod-actors` sweep set `bHidden=true` on the
  owning `StaticMeshActor` of every component it touched: 67 of 75 tiles invisible at
  runtime, no culling pattern. Any pass that hides actors must be scoped by **current
  mesh ownership** and followed by a `--owners` audit. *(24)*

### Materials (all confirmed, in order of discovery)

- **Nahimic (MSI audio OSD) kills `ShaderCompileWorker`** → no master compiles → default
  material everywhere. Stop `NahimicService` / `NahimicSvc64.exe` before any cook. A
  compiled master has `VertexFactory|BasePass|FMaterialShaderMap` strings; a failed one
  is ~3.6 KB with none. *(25)*
- **Cook must target the RHI the game runs.** With no `TargetedRHIs`, the cook emits
  **SM5 only** while MT runs **SM6** → default material, no log. Set both
  `PCD3D_SM5` and `PCD3D_SM6` in `DefaultEngine.ini`; verify by grepping the platform
  strings in a cooked master. *(27)*
- **Materials cooked in another project never render in MT.** MT resolves shader maps by
  ID and silently substitutes the default material (`Tried to access an uncooked shader
  map ID`), and shipping builds compile that warning out. The falsification test: make
  the master emit magenta — if the world doesn't change, your material isn't on the
  surface. *(29)*
- **RETRACTED — "fix = reparent cooked MIs to a vanilla master".** This rule was wrong and
  it caused the C1Full "most materials missing" regression. C1's 1,633 MIs parent to four
  masters shipped in the same pak (`M_C1_Surface`, `_Tex`, `_Masked`, `_Trans`) and render
  correctly. Reparenting onto `M_PropMaster` renames `MetallicTex/RoughnessTex` so values
  stop binding, and drops masking/translucency with no equivalent — those surfaces draw
  nothing. *(corrected; supersedes 29)*
- **Rule that replaces it:** an MI set travels with the masters it names. Ship every master
  an MI references inside the same pak and gate it: resolve
  `Parent (Object): Index=-N → Import[N-1].Name` for **all** MIs and require each resolved
  name to be an asset in that pak. Bundling MIs without their masters fails silently.
- That set was also shipped as a `zzzz_` **override pak**. That is a trap: it works
  only while the override exists and sorts last. **The content pak must carry the
  MIs and their masters itself** — losing the override silently costs every material.

### Pipeline / build

- **Maps are pairs.** `.umap` holds import/name tables, `.uexp` holds property data;
  shipping the `.umap` alone is silent and roadless. Patch and byte-check the right file,
  always both when unsure. *(5)*
- **Never trust printed counters** — `cmp -s in out` on the file carrying the data, or a
  `--verify` dump read-back. Silent no-ops were the norm. *(6)*
- **The spline lives in the streamed sublevel**, not the parent map. *(4)*
- **`rename_asset` on a map leaves an empty shell** — delete destination, `save_map`.
- **`LevelEditorSubsystem.load_level` in `-run=pythonscript` reports 1 actor** for a
  populated map; scripts keying off `get_all_level_actors()` spawn duplicates and can
  lose the level. Key off labels and re-read the saved map with `--level-actors` before
  cooking. *(2026-11-03)*
- **Full-map import clobbers corridor cell settings.** Shared asset names in the same
  folder mean a `replace_existing` import resets per-asset collision/materials for the
  corridor track. Re-apply per track after any full-map import. *(2026-11-03)*
- **Collision writing must be two-pass** — accumulating all faces OOMs at the 8 GB
  container cap (died at exactly 61 tiles). *(2026-11-03)*
- **A pak entry list is a better spec than a manifest** (manifest rebuild lost 2 meshes,
  6 MIs, ~550 textures; rebuilding from the shipped pak's own list gave exact parity). *(2026-11-03)*
- **The full map was already built once: 554 cells, LOD'd (510), collision-split (61
  tiles), pak 1,118,340,359 B — parked, never installed, "too slow at 9.14 M tris"**
  (`builds\zzz_AMC_C1_Full_P.pak`). Any new full-map build must explain what changed
  relative to that one, or it is re-deriving a known result.
- **Pipelines are split** `pipeline/{common,corridor,fullmap}`; Windows `Scripts\{corridor,fullmap}`
  — shared asset names make a single shared pipeline unsafe.

### Packaging / install

- **Pak identity = mount + package paths**, and the pak sorting **later** wins. Retire
  superseded paks or results are not reproducible.
- **UnrealPak derives the mount from the common prefix** — check the reported mount
  rather than forcing a string. `-Create` produced unreadable paks on this build; use
  `repak` (V11, zlib, `RAYON_NUM_THREADS=1`).
- **Verify from the installed pak**: copy to `Paks`, pull it back, extract the entry,
  sha256 against the built file. Several rounds were spent testing a pak that never
  contained the change. *(18)*
- **`Set-Content` collapsing a response file silently packs fewer files**; an empty pak
  is ~339 B — assert the entry count. *(12, 13)*

### API traps that produce false conclusions

- `get_num_uv_channels` returns **0 in a commandlet** regardless of truth. *(26)*
- `is_section_collision_enabled` returns **False unconditionally**. *(2026-11-03)*
- `get_collision_complexity()` disagrees with `body_setup.collision_trace_flag` — trust
  body_setup, read in a fresh process. *(2026-11-03)*
- `mesh:GetMaterial(i)` / `mi:GetMaterial()` return **nil for everything** in UE4SS,
  including vanilla assets. *(29)*
- `set_lod_from_static_mesh(dest, dest_index, src, src_index, reuse_slots)` — destination
  index is the **second** argument. *(2026-11-03)*
- `ECollisionTraceFlag` has no NoCollision member; disable per component with
  `smc.set_collision_enabled(NO_COLLISION)`. *(2026-11-03)*
- **Asset property writes can report success and never persist** (MIC texture params,
  static-mesh `static_materials`). Verify from a fresh process.

---

## Cross-check result (this session)

Gates that were **in the documents** at review time: none of 1, 2, 19, 21, 22, 23, 24,
25, 27, 29, the pipeline-split rule, the parked-build fact, the two-pass collision limit,
or the API false-conclusion list. They are now in the guide (§5.0, §5.16–5.20) and the
C1Full checklist.

Measurement taken during this review, on the current C1Full project:

| Check | Result |
|---|---|
| cell actors in level | 554 |
| distinct meshes / null meshes | 554 / 0 |
| hidden actors / invisible components | 0 / 0 |
| actor locations | all at origin (correct: vertices carry world space) |
| **mesh cooked bounds** | **x −1.5…3.6 km, y −10.5…1.6 km, z 0…1.2 km — all 554 inside the map area, 0 outside** |
| mesh imports in cooked parent map | 873 refs → `/Game/Mods/C1/Meshes` |
| pak mesh payload | 554 `.uasset` + 554 `.uexp`, 1,648.7 MB (geometry inline, no `.ubulk` needed) |
| MI parent | **`M_C1_Surface` / `_Tex` / `_Masked` / `_Trans`** — correct, as shipped by the C1 pak (the earlier `M_PropMaster` reparent was the regression) |

So: geometry exists, is correctly placed, hidden nowhere, and is packed with real
vertices. The open question is therefore **runtime world contents**, which only the
in-game probe (`D:/map_probe.txt`, `cell_actors` / `staticmeshactors`) can answer.
