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
- Source assets: 554 meshes, 1,633 materials, 2,314 textures.
- Cooked: `C1Full_Roads.uexp` 60,740,498 B, `C1Full.uexp` 156,625 B. Tree 10,433 files:
  1,108 mesh / 3,204 material / 6,113 texture cooked files + 4 map files.
- Pak: mount `../../../`, V11, zlib, `RAYON_NUM_THREADS=1`.

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
- **no LODs.** Project decision: shipped build is LOD0 only. Current state: 418 meshes
  single-LOD, **137 still carry 4 LODs** from the earlier pass and must be re-imported
  single-LOD (no API deletes LODs). None of those LODs are empty, so they are not a
  rendering bug — they are unwanted payload.
- **cooked bounds** of the whole set: `x -1.5..3.6 km, y -10.5..1.6 km, z 0..1.2 km`,
  0 tiles outside the map area (catches the OBJ Y-mirror and unshifted imports)

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

### 2b. Material parenting — the invisible-geometry cause

Every MI must be parented to an **MT master** (`M_PropMaster`, `M_PolygonMaster`,
`M_DecalMaster`). MIs parented to our own `M_C1_Surface` ship fine, load fine, and
render **nothing** — MT refuses to compile third-party master shaders. This is what
"geometry missing" actually was.

Gate: dump a sample of cooked MIs; `Parent (Object): Index=-N` must resolve to an
import named `M_PropMaster` / `M_PolygonMaster` / `M_DecalMaster`, and the MI must still
carry its `/Game/Mods/C1/Textures/...` refs.

The correctly-parented MI set is the one previously shipped as
`zzzz_AMC_C1Mats_P.pak` (1,609 assets). **It now belongs inside the content pak** —
shipping it as a separate override pak is what let it silently disappear during cleanup.

## 3. Cook

Cook `C1Full` + `C1Full_Roads` from the mirror client project (Windows target) to
`Saved\Cooked\Windows\MotorTown\Content\Mods`.

Preconditions: `TargetedRHIs` must list **both** `PCD3D_SM5` and `PCD3D_SM6` in
`Config\DefaultEngine.ini` (SM5-only cooks render as default material because MT runs
SM6), and Nahimic must be stopped (`NahimicService`, `NahimicSvc64.exe`) or
`ShaderCompileWorker` crashes and no material compiles.

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

Gate: `mod_explore --list` → mount `../../../`, 10,433 files, per-directory counts as
in the facts block. Round-trip: extract the 4 map files, sha256 == tree copies.

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
