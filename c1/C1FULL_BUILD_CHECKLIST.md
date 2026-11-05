# C1Full — per-build checklist

Executable gates for the full-map mod. Background and the generic procedure live in
[`docs/MAP_PORTING_GUIDE.md`](docs/MAP_PORTING_GUIDE.md); C1 corridor specifics in
[`docs/C1_PIPELINE.md`](docs/C1_PIPELINE.md).

**Why this file exists:** a plain editor cook silently drops four map-level patches
(game mode, sun sky, garage, spawner vehicle classes), and a fifth failure — material
texture references — is invisible until the map loads. Each was being re-applied by
hand per build, so every rebuild lost a different one: blank world, invisible geometry,
fallback name. Every step below has a gate that must pass before the next.

## Facts of this build

- Namespace: maps at `/Game/Mods/C1Full/Maps/`; content (meshes, materials, textures)
  stays at `/Game/Mods/C1/` — the MI→texture references are baked to that path.
- 155 roads / 209.72 km / 6,040 points; graph 42,578 nodes / 10,167 cross-links /
  42,700 lane-change edges / 0 dead ends; 554 cell actors.
- Source assets: 554 meshes (555 including `uvquad`), 1,609 material instances, 2,314 textures.
- Cooked: `C1Full_Roads.uexp` 60,740,498 B, `C1Full.uexp` 156,625 B. Tree 10,447 files:
  1,108 mesh / 3,218 material / 6,113 texture cooked files + 4 map + 4 C1Full extras.
- Pak: mount `../../../`, V11, zlib, `RAYON_NUM_THREADS=1`. v6 =
  659,718,290 B, `3d437472dab693fff7eb339eef68667a6f14e7713001633a47c79b84d53d287e`.
- Geometry: 554 tiles at metres→cm ×100 (bounds x −11.2..7.7 km, y −10.7..16.5 km),
  single LOD, collision complex-as-simple. **~9.1 M tris, no LODs** — the parked
  1.12 GB build differed only by carrying LODs.

## 0. Preconditions

- Project `D:\C1FullMirror`: content present at both namespaces above
- Tools: `uatt.sh` (UAssetTool), `repak`, `mod_explore`, `win_put.sh` / `win_ps_file.sh`
- `DOTNET_ROLL_FORWARD=Major`, `DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1`

Gate: source counts match the facts block.

## 1. Level state

- 554 `C1_cell_` actors, each with a static mesh
- 0 hidden actors, 0 hidden-in-game, 0 invisible components
- 155 road actors in `C1Full_Roads`
- each mesh carries **collision** (full-map import resets per-asset collision; corridor
  settings do not survive it) — `CTF_USE_COMPLEX_AS_SIMPLE`, 0 convex hulls
- **scale**: union of mesh bounds must be the same order as the road splines
  (`x -1,104,777..611,734 cm`, `y -1,002,062..1,658,899 cm`). A union spanning a few km
  instead of ~20 km means `import_uniform_scale=100` never applied and every tile is
  100× too small — invisible geometry, no collision, no error. Per tile: OBJ x = −5,068.62 m
  must import as −506,862 cm.
- **no LODs.** Project decision: shipped build is LOD0 only. `replace_existing=True` does
  **not** drop extra LODs (it rewrites LOD0 only) — delete the asset, then import.
- **cooked bounds** of the fixed set must match the road span:
  `x -11.0..6.1 km, y -10.0..16.6 km, z 0.8..0.9 km`, 0 tiles outside the map area
  (catches the OBJ Y-mirror and unshifted imports)

Gate: `check_hidden.py` → `cells=554 hidden_actor=0 hidden_in_game=0 component_invisible=0`;
`mesh_bounds.py` → `near_origin=554 far=0`.

Note: a full-map build already existed once — 554 cells, LOD'd (510), collision-split
(61 tiles), pak 1,118,340,359 B — and was **parked as too slow (9.14 M tris)**. If this
build differs from it, say what changed.

## 2. Material chain

Every MI's texture parameter must resolve, and the check must run in a **fresh editor
process** — in-session reads can show values that were never saved.

Gate: `verify_mi.py` → `resolved == params` (0 nulls).

Do not try to repair MIs in place: property writes report success and do not persist
(guide §5.2). Fix the path they already reference, or repoint the actors.

### 2b. Material parenting — MIs must ship with their masters

**Corrected twice. Current rule, with the evidence behind it.**

MT compiles material shaders into its **own** library. A master cooked in our project ships
no usable shader data (`.uexp` 3.6–7.9 KB), so it renders the engine checkerboard no matter
how correct its graph is. Only **instances of MT's own masters** render.

Therefore every MI is retargeted onto a vanilla master and its parameters must match that
master's declared set. For `M_PropMaster`, read from its `TextureStreamingData`:

```
BaseColor  texture      Normal     texture
Metallic   scalar       Roughness  scalar
Specular   scalar       UV_Tiling  scalar
```

Renaming `MetallicTex → Metallic` / `RoughnessTex → Roughness` while keeping the Texture2D
value yields an instance that **fails to compile** → checkerboard, indistinguishable from a
missing material. Drop those parameters; let the scalar defaults apply.

Gate, over every MI in the pak:

```
parent  = resolve Parent (Object): Index=-N -> Import[N-1].Name     (-9 means Import[8])
pass    = parent is a vanilla MT master (M_PropMaster / M_PolygonMaster / M_plants)
and       no TextureParameterValue names a parameter the master declares as SCALAR
and       every /Game/Mods/C1/Textures/... ref exists in the pak
```

A clean material-resolution probe is **not** evidence of rendering: `GetMaterial(0)` returns
the assigned instance and reports zero defaults even while the screen shows checkerboard.
Screenshots outrank probes here.

Ship the retargeted set **inside the content pak** (never as a separate override that can be
retired), and never ship the mod-owned `M_C1_Surface*` masters expecting them to render —
they exist only as authoring parents, and in `C1Full` they are removed entirely.

## 3. Cook

Cook `C1Full` + `C1Full_Roads` from the mirror client project (Windows target) to
`Saved\Cooked\Windows\MotorTown\Content\Mods`.

Preconditions: `TargetedRHIs` must list **both** `PCD3D_SM5` and `PCD3D_SM6` in
`Config\DefaultEngine.ini` (SM5-only cooks render as default material because MT runs
SM6), and Nahimic must be stopped (`NahimicService`, `NahimicSvc64.exe`) or
`ShaderCompileWorker` crashes and no material compiles.

**Status in this project: `TargetedRHIs` is not set at all** (no `PCD3D_*` line in
`DefaultEngine.ini`). That was harmless once every MI was reparented to a vanilla MT
master — MT compiles those shaders itself and we no longer cook any master of our own.
If a future build ships a mod-owned master, this gate becomes blocking again.

Gate: `LogCook: Display: Done!` **and** `C1Full_Roads.uexp` ≈ 60.7 MB. A ~800 B stub
means the sublevel saved empty — see `save_map` in the guide §2.3. Exit code is `1` on
the known Water Body collision-profile warning; ignore it. Spot-check a cooked master
for `PCD3D_SM6`.

## 4. Patch the cooked maps — MANDATORY, every cook

- **4a. Parent class refs** — `c1/pipeline/repair_class_refs.sh`:
  `WorldSettings.DefaultGameMode=DriveGameModeBP_C`,
  `SunSky.ChildActorClass=MTSunSky_C`, `Child.ChildActorClass=GarageActorBP_C`.
  Property references only, never baked actors.
  Gate: dump → 6 matches (3 refs × 2 lines), no `MTSunSky_C_<n>` / `GarageActorBP_C_<n>`.
  Missing this = **blank world, no player controller, no game mode**.

- **4b. Sublevel spawner** — `--set-array-class-ref <umap> <out> <export> SpawnSettings
  SettingKey VehicleClass vc_map.json`.
  **Auto-detect `<export>`**: dump and grep `Name=MTAIVehicleSpawnSystem_[0-9]+` — it is
  `_1` after re-authoring, `_0` before. Hardcoding it fails the build.
  Gate: dump → 8 `/Game/Cars/Models` refs.

- **4c.** Both maps patched as **pairs** (`.umap` + `.uexp` together, absolute paths);
  a map without its `.uexp` parses as garbage (`count ('-156621') …`).

## 5. Pack

`RAYON_NUM_THREADS=1 repak pack -m "../../../" --version V11 --compression Zlib pack2 <out>.pak`

Tree must contain `MotorTown/Content/Mods/C1Full/Maps/*` **and**
`MotorTown/Content/Mods/C1/{Meshes,Materials,Textures}/*`.

Gate: `mod_explore --list` → mount `../../../`, 10,447 files
(554 mesh / 1,609 material / 2,148 texture `.uasset` + 4 map files). Round-trip: extract
the 4 map files, sha256 == tree copies (`946801611ede…` / `0ee8d0ab641c…` /
`1787630c787a…` / `22cabe1bb54b…`).

## 6. Registration (`zzz_AMC_C1FullOffline_*`)

- `DriveMaps[12]` and `TimeAttackMaps[6]`, `Key=C1FullShuto`,
  `Level=/Game/Mods/C1Full/Maps/C1Full`
- Both carry `Name` text via **`set_description`** — `set_display_name` silently no-ops
  on a plain `TextProperty`

Gate: display string present in `GameResource.uexp` (4 hits); array counts 13 / 7.

## 7. Course row (`zzz_AMC_C1FullCourses_*`)

Clone `Town_Circuit` → row `C1FullShuto`, `bUseOffTrack=true`, `RacerXPPerLap=50`,
its own `Name` via `set_description`.

Gate: display string in `Courses.uexp`; 14 rows. A cloned row without its own name
shows the template's — the "Town Circuit" fallback.

## 8. Install

- Back up `Content\Paks` (all `*.pak` except the 2.8 GB vanilla) with a SHA256 manifest
- Install content + offline + courses; verify `SHA_MATCH` per file
- Retire superseded builds into the backup dir
- Confirm **no other pak mounts `Mods/C1/` or `Mods/C1Full/`** — a later-sorting pak
  overrides silently and makes every subsequent result non-reproducible

Gate: installed files `SHA_MATCH`; active pak list contains exactly one pak per namespace.

## 9. In-game

- Listed as **C1 Full Shuto Expressway** under Time Attack
- Loads into normal driving (DriveGameMode), player controllable, HUD present
- Full city visible past the loop, **textured**
- AI traffic present

### §8b — Shader archive gate (HARD FAIL)

- [ ] `mod_explore <pak> --list | grep -c 'ShaderArchive'` **must be 0**.
  Shipping `ShaderArchive-*.ushaderbytecode` shadows the game's own library and crashes the
  client at boot: `LowLevelFatalError [GlobalShader.cpp:803] Could not load section N (of 330)
  of the global shadermap`. MT ships only SM5 archives (`Global` 13,242,450 B, `MotorTown`
  56,636,716 B); our cook emits same-named partial ones. Mod paks cannot extend MT's shader
  library — instances of MT's own masters only.

### §2c — Mesh → material coverage (HARD FAIL)

For every mesh in the pak, every `/Game/Mods/<root>/Materials/MI_*` path it references must
exist in the pak. Count it, do not eyeball it:

```python
pat = re.compile(rb"/Game/Mods/C1Full/Materials/(MI_[A-Za-z0-9_\-]+)")
need = {n.decode() for mesh in meshes for n in pat.findall(open(mesh,'rb').read())}
missing = need - {basename(f)[:-7] for f in glob("Materials/*.uasset")}
assert not missing, missing
```

2026-11-05: **30 missing**, covering `MI_C1_mat_wal` (99 meshes), `MI_C1_mat_saku` (81),
cameras (64+64), `MI_C1_mat_fence` (40), `MI_C1_sign` (28). Those slots had been drawing the
engine default in every build. Restore by cloning the surviving sibling under the expected name
(`MI_C1_mat_wal` → `MI_C1_mat_wal_15`).

### §2d — Map import completeness, including the namespace root (HARD FAIL)

Every `/Game/Mods/<root>/…` import in the shipped `.umap` must resolve inside the pak — not just
meshes and maps. On 2026-11-05 the packer copied `Materials/ Maps/ Meshes/` only, so
`BP_C1_Sky` and `BP_C1_Prop` (loose at the namespace root) were absent: the level had no sky
actor, therefore no sun and no skylight, and every surface rendered unlit — visually identical to
"materials not applied".

### §2e — Ship one material shape

Instances only, parented to MT's own masters, `BaseColor` texture + `Metallic`/`Roughness`
scalars. No master assets in the pak. See `MAP_PORTING_GUIDE.md` §5.0.
### §2f — Texture bindings non-null (HARD FAIL)

Instances must come from the build that rendered, never from a cook output or a duplicate tree —
the cook stores `ParameterValue (Object): Index=0` (null) for texture parameters and the world
renders flat white.

```bash
dotnet UAssetTool.dll --dump <Materials>/MI_x.uasset | grep 'ParameterValue (Object)'
# every texture parameter must show a non-zero index (e.g. Index=-7), never Index=0
```

Sample one instance per material family. 2026-11-05: the cook output and the `C1Full` tree copies
were null; only the shipped `C1` pak's instances carried textures, and swapping the source is what
turned white into a textured world.
