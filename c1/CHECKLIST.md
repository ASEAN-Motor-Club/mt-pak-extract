# C1 Shuto — level cleanup checklist

Status as of 2026-11-02. Anything marked `[~]` is deliberately deferred, not done.

## Must remove before release

- [ ] **DELETE the borrowed `MotorTownRoad` export ("MotorTownRoad_2", 144 B) from `C1_Roads.umap`.**
      It is the NS *shell* kept only so we had a valid cooked `AMotorTownRoad` to write into.
      Its properties and spline are replaced by ours, but the export itself is Nordschleife's.
      Removed only once the level can be authored properly (mirror project via UHT headers, or
      an offline builder that can synthesize the export from scratch). Tracked here so it does
      not quietly ship.
- [ ] **Repath everything off Nordschleife.** Zero references to `/Game/Mods/Nordschleife/*`
      must remain in either map. Known carriers:
      - `C1.umap`: 3,920 imports / 3,181 name-table entries still point at NS packages
        (`.../Props/BP_NS_Prop`, `.../Road/Meshes/SM_CT_phys_asphalt_*`) even though the actors
        using them are gone. They are unused, but they are strings and they are NS.
      - Both map headers: `FolderName` = `/Game/Mods/Nordschleife/Maps/NS_Nordschleife[_Roads]`
      - `C1_Roads.umap`: residual `Road_Nordschleife` blob string
      - Package name of the shipped map must be `/Game/Mods/C1/Maps/C1` (NameMap entry, summary,
        and `LevelStreamingAlwaysLoaded` ref in the main map) — verify none of these still say NS.
      This needs an import/name-table compaction pass (drop unused imports + unused names and
      remap FName indices), which does not exist yet.
- [ ] Residual string `Road_Nordschleife` in a binary blob of the pruned `C1_Roads.umap`
      (not a parsed property; owner not yet identified). Zero it out or confirm it is inert.
- [ ] `FolderName` in both map headers still reads `/Game/Mods/Nordschleife/Maps/NS_Nordschleife[_Roads]`.
- [ ] `BP_NS_Prop_C` ×23 and `BP_NS_Sky_C` ×1 kept in `C1.umap` by explicit instruction.
      Replace with our own props/sky before release.
- [ ] `MotorTownNavigation` in `C1_Roads.umap` — confirm its `GraphData` actually covers our
      spline; `BuildNavigation()` may have to run for GPS/AI to see the road.

## Done

- [x] Prune NS scenery from `C1.umap` — 1,858 `StaticMeshActor`s dropped, our 75 kept, 0 NS strings left.
- [x] Prune NS actors from `C1_Roads.umap` — 205/214 exports dropped: 40 race sections, 40 area
      volumes, NS house, second NS road. 4 actors remain.
- [x] Verify both road actors were NS's (CourseKey `Nordschleife2`, `RoadFlags=136`, 1,011-pt spline,
      60/300 kph) and that no road of ours existed.

## Done — road spline

- [x] `--set-spline` on the surviving road: **1,379 keys** (our loop, closed), `RoadType`/`CourseKey`
      removed, `LaneWidth=300`, `NumForwardLanes=2`, `NumBackwardLanes=0`, `SpeedLimitKPH=60`,
      `RoadFlags=0` (AI enabled — NOT `NoAI`/`NoCompanyAI`), `SplineBounds` set to our bbox.
- [x] All four `FSplineCurves` sub-curves rewritten (`Position`, `Rotation`, `Scale`,
      `ReparamTable`) — they must share the key count or the spline is invalid at load.
- [x] Lane data came from the BeamNG mod itself (`levels/c1/main/missiongroup/ck_ai`):
      155 `DecalRoad` AI paths, all `oneWay=true`, `lanesLeft=2/lanesRight=0` over 84.4% of the
      length covering our loop, node width median 6.0 m → 2 × 3.0 m.

## Navigation graph (baked data)

- [ ] **Blocker:** `UAssetAPI` cannot parse `MotorTownNavigation` exports at all —
      `parse failed: ArgumentOutOfRangeException` on both our maps and vanilla `Jeju_World`
      (export 26740). So no reference graph can be read, cloned, or written offline with the
      current tooling. `FMTRoadGraphNode`/`FMTRoadGraphData` layout is known from UHT headers,
      but the serialized schema is not resolvable by our parser.
- [ ] Two routes to real baked data:
      (a) **Mirror project** — UE4GameProjectGenerator from the UHT headers (VS 2022 Community
          is installed; `D:\UE_5.5` present), spawn `MotorTownRoad` + `MotorTownNavigation`,
          call `BuildNavigation()`, save, cook. Correct and also removes the borrowed NS road.
      (b) **Offline generator** — requires first fixing the nav-actor parse (schema for
          `FMTRoadGraphNode` incl. `Debug_NavPoints` weak-ptr array), then learning node/edge
          conventions from a parsed vanilla graph before writing ours.
- [ ] Cheap experiment first: cook + ship the road as-is (empty `GraphData`, `RoadFlags=0`).
      If AI traffic appears, the game builds navigation at load and no baking is needed;
      if it does not, baking is confirmed as required.

## Mirror project (route CLOSED — proven unable to bake)

- [x] Generator built against UE 5.5 after: NETFXSDK install, `PlatformAllowList` rename,
      unique-build-environment removal, engine-plugin pruning, KantanCharts/Prefabricator
      reconstruction from the UHT dump, enum `None = 0` entries, blueprint-specifier stripping.
- [x] Generated `D:\C1Mirror` (3,435 files, `Source/MotorTown` 1,444 headers) and compiled
      1,416 translation units.
- [x] **DEAD END, structurally:** `ProjectGenerator` emits *empty stubs* —
      `void AMotorTownNavigation::BuildNavigation() { }`. The nav algorithm exists only in the
      compiled game binary, never in headers, so a mirror-built editor can create an *empty*
      graph and nothing else. Same reason plugin modules fail to link (declared, never defined).
      Do not resume this route for navigation data.

## Navigation data — actual route

- [x] `C1NavDump` UE4SS probe v2 installed (5,305 B): calls `BuildNavigation()` in the running
      game, then dumps every node + edge (**road, SplineDistance, SplinePointIndex, Lane,
      LateralOffset/Distance, RightSideClearance, Flags, AutoConnectDistance, SpeedLimit,
      IslandId, CrossroadId, location, Direction, RightVector, Edges[to/cost/dist/flags]**),
      plus graph bounds and heightmap cell count → `D:\c1_nav.json`.
- [ ] Install the pak carrying our spline, launch C1, collect `c1_nav.json`.
- [x] **Baker implemented and round-trip verified**: `mt-pak-extract --bake-nav <in.umap> <out.umap> <nav.json>`
      (C# `RunBakeNav`). Creates the `GraphData` property the actor never had:
      `Nodes[]` of `MTRoadGraphNode` (Road→our road export, SplineDistance, AbsoluteLocation,
      Direction, RightVector, NodeIndex, LateralDistance, LateralOffset, Lane, SplinePointIndex,
      Flags, AutoConnectDistance, Edges[] of `MTRoadGraphNodeEdge`{NodeIndex,Cost,Distance,Flags},
      SpeedLimit, IslandId, CrossroadId, RightSideClearance) + `Bounds` as native `BoxPropertyData`.
      Native `VectorPropertyData`/`BoxPropertyData`/`TBox<FVector>` — no template cloning needed.
      Synthetic 3-node test: nav export went 70 → 577 bytes, reparse shows `GraphData → Nodes[3]`
      with every field and `Edges[1]{NodeIndex:1,Cost:50,Distance:50}` intact.
- [ ] Cook + pack + install the baked graph, verify AI traffic on the loop.

## Next

- [ ] Cook + pack, check in-game: road renders, AI traffic uses it, GPS routes on it.
- [ ] Own map image: render top-down, import `T_WorldMap_C1`, add `FMTMap` entry to
      `GameResource.DriveMaps` (`WorldMapSize`≈`429000`, `WorldMapLocation` from our bbox).
- [ ] Own garages (`GarageActorBP_C` reference) and home (`House_C` + Houses row).

## Garage placement

- BeamNG spawn data (`levels/c1/main/missiongroup/playerdroppoints/items.level.json`):
  `spawn_default` = Shibaura PA (1102.37, 4709.02, 874.11), `spawn_parking` = Tatsumi 1st PA
  (5932.34, 4667.84, 874.49), plus `spawn_road` / `spawn_mirai` / `spawn_new` / `spawn_garage`.
  Parking lot `Parking 2816` sits at (1099.04, 4738.5, 874.05) — beside `spawn_default`.
- **Coordinate mapping is exactly `ue_cm = beamng_m * 100`** (`finalize.py`), no rotation/offset.
- **BLOCKER for placing at the real lot: both parking areas fall OUTSIDE our imported corridor.**
  Our loop/world bbox is y 569,452..998,116 cm; Shibaura PA maps to y=470,902 and Tatsumi to
  y=466,784 — ~1 km south, where we have no geometry (the kit was built along the loop only).
  A garage there would float in the void.
- Implemented `--add-garage <in.umap> <out.umap> <x> <y> <z> <yaw>` (C# `RunAddGarage`):
  appends a `GarageActorBP_C` actor export (Outer=Level, `RootComponent`→new component) plus a
  cloned parsed `SceneComponent` holding the transform. Verified: exports 233/234 appear,
  x/y/z land in the .uexp as **float64**. BP instancing means SCS builds InteractionCube /
  MotorTownInteractable / Camera itself — no component authoring needed.
- Gotchas hit: `NormalExport(Export)` copy ctor does **not** carry `Data` (set it explicitly);
  UAssetAPI needs a schema entry for a BP class to write it (aliased `StaticMeshActor`'s schema —
  engine resolves cooked properties by name); `RelativeLocation` is a struct wrapping a nested
  `VectorPropertyData`, so setting it needs a recursive walk (same nesting as `SplineBounds`).

## 2026-11-03 — full map parked, corridor resumed

- [x] Full map imported (554 cells), LOD'd (510), collision-split (61 tiles), packed
      (1,118,340,359 B) — **parked**, not installed; too slow at 9.14 M tris
- [x] Corridor pak restored to the game (171,447,034 B, 4,847 entries)
- [x] Pipelines split: `c1/pipeline/{common,corridor,fullmap}` and
      `D:\UEProjects\C1\Scripts\{corridor,fullmap}`
- [x] Corridor repack tooling diffs against the verified pak's file list (parity: 4,847)
- [ ] Corridor materials pass — verify every MI resolves in-game
- [ ] Corridor LODs — attach to heavy cells, check pop at speed
- [ ] Corridor roads + navigation — spline sanity, AI behaviour on our road

## 2026-11-03 — nav/crash audit

- [x] Corridor level rebuilt import table: 3,920 -> 178 imports
- [x] Dropped 23 `BP_NS_Prop_C` + 1 `BP_NS_Sky_C` exports and their 24 child components
- [x] `C1_Roads` compacted 44 -> 21 imports (only /Script/*), nav actor + 1,379-pt spline intact
- [x] `C1NavDump` disabled (BuildNavigation in a live game is a crash risk, dump no longer needed)
- [ ] Level has no sky now (NS sky actor removed, no substitute) — add MTSunSky or similar
- [ ] `C1_Roads` FolderName still reads `/Game/Mods/Nordschleife/Maps/NS_Nordschleife_Roads`

## 2026-11-03 — actors placed on the corridor map

- [x] SunSky: native `MTSunSky` at (271405, 859266, 84760)
- [x] Garage: native `MTGarageActor` at (271391, 859273, 84760) yaw -116.2 (16 m right of centreline, 95-pt straight)
- [x] PlayerStart moved to (271397, 859270, 84760) yaw -116.2, ~6 m from the garage
- [x] Deployed: pak 203,942,417 B; `C1.umap` inside = 165,142 B
- [ ] If the garage reads as bare (no building mesh) the BP variant is needed — requires a real
      schema for `GarageActorBP_C`

## 2026-11-03 — gotcha audit of the shipped pak

- [x] Maps ship as pairs; 1,379-pt spline verified inside the installed `C1_Roads`
- [x] 79 package imports all resolve (only vanilla `DriveGameModeBP` external); 0 NS refs
- [x] `bHidden` True 0 / False 75; entry parity 4,847
- [x] Materials override rebuilt from current cooked MIs (568, parent `M_PropMaster`, jimen now
      carries BaseColor) and installed — 2,333,148 B, backup kept
- [ ] Remove `zzz_AMC_C1NSDeps_P.pak` (obsolete, third-party)
- [ ] Delete or stop shipping the 3 uncompiled masters
- [ ] Sky + garage: transplant actor + component subobjects from `DrivingLicense.umap`
- [ ] Collision cannot be read back from the pak (bulk data) — keep the editor-side probe as truth
