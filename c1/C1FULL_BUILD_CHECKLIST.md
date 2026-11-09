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
- 156 `MotorTownRoad` actors in `C1Full_Roads`, each carrying its spline in **world
  space** (verified 2026-11-05: `C1_Course` p0 `(2349.8, -7694.0, 847.3) m` matches the
  gate spec with Y negated). They legitimately sit at `(0,0,0)` — do not "fix" that.
- 40 `MotorTownRaceSection` actors **deleted** 2026-11-05: they carry no component, so
  their transform was the only thing placing them and all 40 sat stacked at the origin.
- 155 `C1_Rd*` roads sampled by the nav baker (156 `MotorTownRoad` total; `C1_Course`
  is excluded by the baker's label filter); graph **42,578 nodes / 9,911 cross-links /
  42,700 lane-change edges / 0 dead ends / 1 island**, re-baked 2026-11-05 after the
  race sections were removed. Baseline lives in `pipeline/constants.json`
  → `expected_c1full`, and the stage only reads it with `C1_BAKE_SET=c1full`.
- 554 cell actors.
- Source assets: 554 meshes (555 including `uvquad`), 1,609 material instances + 30
  sibling aliases = 1,653 shipped MIs, 2,314 textures.
- Cooked: `C1Full_Roads.uexp` 60,740,498 B, `C1Full.uexp` ~197 KB (moves with each
  re-authoring — never gate on an exact byte count, gate on the Roads size).
- Pak: mount `../../../`, V11, zlib, `RAYON_NUM_THREADS=1`. v24 (2026-11-05) =
  699,497,561 B, `60c18affc4f0e77be80ee5a8aeb8394c18444143774457ae5dcf0c9d7145943b`.
- Geometry: 554 tiles at metres→cm ×100 (bounds x −11.2..8.0 km, y −10.7..16.9 km),
  single LOD, collision `CTF_UseComplexAsSimple` on all 555. **~9.1 M tris, no LODs** —
  the parked 1.12 GB build differed only by carrying LODs.

## 0. Preconditions

- Project `D:\C1FullMirror`: content present at both namespaces above
- Tools: `uatt.sh` (UAssetTool), `repak`, `mod_explore`, `win_put.sh` / `win_ps_file.sh`
- `DOTNET_ROLL_FORWARD=Major`, `DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1`

Gate: source counts match the facts block.

## 1. Level state

- 554 `C1_cell_` actors, each with a static mesh, each at
  `(origin_x*100, -origin_y*100, 0)` — metres→cm with the **opposite Y** axis
- 0 hidden actors, 0 hidden-in-game, 0 invisible components
- 156 road actors in `C1Full_Roads`, 0 `MotorTownRaceSection`
- each mesh carries **collision** (full-map import resets per-asset collision; corridor
  settings do not survive it) — `CTF_UseComplexAsSimple`. Do **not** gate on "0 convex
  hulls": the cook emits `ConvexElems` regardless (measured: `BodySetup` ≈131 KB on a
  mesh with the complex flag). Gate on the trace flag only.
- **scale**: union of mesh bounds must be the same order as the road splines
  (`x -1,104,777..611,734 cm`, `y -1,002,062..1,658,899 cm`). A union spanning a few km
  instead of ~20 km means `import_uniform_scale=100` never applied and every tile is
  100× too small — invisible geometry, no collision, no error. Per tile: OBJ x = −5,068.62 m
  must import as −506,862 cm.
- **no LODs.** Project decision: shipped build is LOD0 only. `replace_existing=True` does
  **not** drop extra LODs (it rewrites LOD0 only) — delete the asset, then import.
- **cooked bounds** of the fixed set must match the road span:
  `x ≈ -11.2..8.0 km, y ≈ -10.7..16.9 km, z ≈ 0.6..1.2 km`, 0 tiles outside the map area
  (catches an unshifted import and a wrong-sign actor transform)

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

## 2h. Geometry gates (placement, collision, UV)

Placement is an **actor** problem, not an import problem. The imported mesh assets are
cell-local (asset bounds = OBJ coords minus the 500 m cell origin, Y negated by the
importer), so the level is placed correctly by moving actors:

```
actor.location = (origin_x * 100, -origin_y * 100, 0)     # metres -> cm, opposite Y
```

Never re-import the mesh set to fix placement — re-import rebuilds each asset from the
OBJ and discards collision and UV state (this is how a build ships with no collision).

Gate A — placement. Actor world union must match the road spline span, not a few km:

```
expected  x ~ -11.0 .. 6.1 km, y ~ -10.0 .. 16.6 km
pass      |min_x + 11.0km| < 0.5km and |max_y - 16.6km| < 0.5km
```

A union spanning only a few km means the meshes are local and the actors never moved.

Gate B — collision. The OBJ importer never creates collision. Every mesh in the set must
have `CollisionTraceFlag = CTF_UseComplexAsSimple` (trimesh collision); a mesh left at
`CTF_UseDefault` with no convex elements has an empty body setup and the player falls
through it.

```
unreal.StaticMeshEditorSubsystem.get_simple_collision_count(mesh)   # 0 is expected
mesh.get_editor_property("body_setup").get_editor_property("collision_trace_flag")
    == unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE          # required
```

Gate C — UV orientation. The level frame is a pure Y mirror of the source, which reverses
the texture. Mirror V at import time (`v' = 1 - v` in the OBJ). Upside-down surfaces mean
V was not mirrored; a V flip must be done as an import, never as a post-hoc material hack.

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

**One asset, one pak** — the single-pak tree below is superseded; see `docs/PAK_LAYOUT.md`. Each pak
stages exactly one family and the builders refuse to stage another's assets:

```bash
c1/tools/build_basepak.sh <source-pak>            out/zzz_AMC_C1Base_v2_P.pak      # /Game/Mods/C1 + BPs
c1/tools/build_meshpak.sh <cooked>/Mods/C1Full/Meshes out/zzzzz_AMC_C1Mesh_v2_P.pak 554
c1/tools/build_matspak.sh <mats-dir>              out/zzzzz_AMC_C1Mats_P21_P.pak
c1/tools/build_levelpak.sh <cooked>/Maps          out/zzzzzz_AMC_C1Map_v3_P.pak    C1Full
c1/tools/build_levelpak.sh <cooked>/Maps          out/zzzzzzzz_AMC_C1NavTest_v2_P.pak C1Full_Roads
c1/tools/build_levelpak.sh <cooked>/Maps          out/zzzzzzzzzz_AMC_Shuto_Lights_v12_P.pak C1Full_Lights
```

Then the ownership gate — this is the ship condition, not an optional check:

```bash
for p in out/zzz*_P.pak; do python3 c1/tools/pakset.py manifest "$p" c1/out/pakset; done
python3 c1/tools/pakset.py check c1/out/pakset   # must print "OK: every asset has exactly one owner"
```

Historical single-pak tree (kept for reference only): `MotorTown/Content/Mods/C1Full/Maps/*` **and**
`MotorTown/Content/Mods/C1/{Meshes,Materials,Textures}/*`, mount `../../../`, 4,359 files. That
layout is what produced 4,420 double-claimed entries across 6 paks — do not rebuild it.

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
- **Whitelist every installed pak path** with `c1/tools/approve_paks.ps1` before launching. The
  client prompts at boot for any pak path it has not seen, keyed by full path in
  `%LOCALAPPDATA%\MotorTown\Saved\Config\Windows\CustomPak.ini` `[CustomPakAccepted]`; a rebuild
  under a new versioned filename always prompts again. The install is not finished until the
  script reports `APPROVE_OK`.

Gate: installed files `SHA_MATCH`; active pak list contains exactly one pak per namespace;
`APPROVE_OK` for the installed set.

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
### §2g — Masked override serialised (HARD FAIL, per route)

For one instance per route (`[veg]` → `M_plants`, `[masked]` → `M_AlphaTest`), the dump must show
the blend mode, two-sided flag and clip value together:

```bash
dotnet UAssetTool.dll --dump mats/MI_C1_mat_tree_01.uasset | grep -E 'BlendMode \(Enum\)|TwoSided|OpacityMaskClip'
# BLEND_Masked + TwoSided True + 0.3333 — all three, else the surface is opaque
```

A structure with only `TwoSided` and clip (or `BlendMode (Byte): 0`) means the property was dropped
silently — check that the material routed as vegetation also set the mask flag.

## §0 — Pak layout: layered in development, single pak on release

Consolidating the dev set into one pak (done 2026-11-06 for the Shuto release) is the **release**
shape only. It must not be used while iterating: every nav bake, material tweak or map edit then
means rebuilding and re-uploading ~700 MB, and a single stray override silently discards another
layer's work.

**Development (client `Content\Paks`) — mount order is filename sort order:**

| pak | size | carries | rebuilt when |
|---|---|---|---|
| `zzz_AMC_C1FullCourses_v3_P` | 3 KB | `DataAsset/Courses` | course/route data changes |
| `zzz_AMC_C1FullOffline_v4_P` | 50 KB | offline/session data | rarely |
| `zzzz_AMC_C1Test_P` | ~699 MB | geometry + everything base | meshes/geometry changes |
| `zzzzz_AMC_C1Mats_P20_P` | 3 MB | material instances | material changes |
| `zzzzz_AMC_C1Mesh_P` | 11 MB | mesh overrides | mesh-only iteration |
| `zzzzzz_AMC_C1Map_P` | 392 KB | **parent map** (`C1Full.umap/.uexp`) | map actor/POI edits |

Rules that follow from the sort order (`_` = 0x5F sorts before `z` = 0x7A, so `zzz_` < `zzzz_` <
`zzzzz_` < `zzzzzz_`):

1. **Never ship an override that is not in the layer it belongs to.** A pak that carries
   `C1Full_Roads.*` replaces the roads sublevel *including its baked nav graph* — that is how a
   nav bake gets silently discarded by an unrelated map or lights pak.
2. **Lights and other additive content must be their own sublevel** (`C1Full_Lights`), never a
   `C1Full_Roads` override, or every light tweak re-ships 60 MB of nav.
3. **Check the mount order before judging any in-game result.** Two paks shipping the same record
   is not an error the engine reports; the later filename wins silently.
4. **Release = one pak** (`zzz_AMC_Shuto_P.pak`), built from the final layer set, published, and
   hash-verified over HTTP. It is never installed on a dev client.

Diagnostic: `Get-ChildItem Content\Paks -Filter *.pak | Sort-Object Name` and compare each file's
sha256 against the build that produced it. A "missing" dev pak usually means a release pak was
installed over it.
