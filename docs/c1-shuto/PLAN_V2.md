# C1 Shuto — Plan v2: deterministic build, no mutation

Status: replaces the "patch a cooked level" approach (UMapPatch / --prune-level /
--compact-imports / --move-actor / --set-bool) for the shipped artifact.

## Why the old approach is being abandoned

Every artifact was produced by mutating a cooked `.umap` with four different
byte-level tools. When it broke, there was no way to tell which pass was at fault,
and the bisect was additionally poisoned because `bAutoSpawnMissingNavData = True`
was carried through every build, so "materials crash", "meshes crash" and "roads
crash" were all the same fault reported three times. A mutated cooked level cannot
be reasoned about; it can only be diffed by luck.

New rule: **source → editor → cook → pack**. Nothing post-processes a cooked asset.

## Ground truth, from the reference pak

`ZZ_Nordschleife_P.pak` (1,229,891,983 B):
- 4,944 entries, pak version **V8B**, mount `../../../`
- `MotorTown/Content/Mods/Nordschleife/Road/` — 4,934 (meshes, materials, textures)
- `Sky/` — 4 (`BP_NS_Sky`), `Props/` — 2 (`BP_NS_Prop`), `Maps/` — 4
- **No `GameResource` override** → it never registered itself in any in-game list;
  it was only ever launched directly. Our time-attack listing came from *our*
  `zzz_AMC_C1Offline_P.pak` (`MTGameResource` patch), not from NS.
- Level shape (the known-good template): 1,933 `StaticMeshActor` + 1,933
  `StaticMeshComponent`, 23 `BP_NS_Prop_C` + 24 `ChildActorComponent` + 24
  `SceneComponent`, plus exactly one each of `World`, `WorldSettings`,
  `PersistentLevel`, `LevelStreamingAlwaysLoaded`, `NavigationSystemModuleConfig`,
  `Model`, `PlayerStart` (+`CapsuleComponent`), `ExponentialHeightFog`
  (+component). Its class imports are `DriveGameModeBP` and `MTSunSky` (vanilla).

Consequence: a course needs **both** a level and a `MTGameResource` row. NS proves
the engine does not require the row; the game's UI does.

## Build contract

1. Source of truth is JSON in the repo: cell meshes, cell transforms, spline, actor
   placements. No numbers typed into a script.
2. The level is created **empty in the editor** and actors are spawned by Unreal, so
   every component tree is serialised by the engine. Never authored by hand.
3. Cook once, straight from that level.
4. Pack with `mod_pack` (V11, mount `../../../`) from a staging directory built from
   the cook output **plus** the map. Same producer and version as every other mod
   pak here; no baseline-list staging, no UnrealPak entry list, no mutation.
5. Every build writes a manifest (input hashes, cooked file hashes, pak hash) so a
   rebuild is byte-comparable.

### Class resolution: how we reach game classes

`D:\UEProjects\C1` has neither the MotorTown module nor its assets, so `/Script/MotorTown.*`
and `/Game/Blueprints/MTSunSky` are not spawnable in-editor. Cooked references are
package-path strings resolved against the mounted paks, so a project can hold a fake
asset at the exact game path, reference it, and have the game resolve to the real one —
provided the fake is never packaged.

Order of work (full write-up: `docs/c1-shuto/RESEARCH-base-game-classes.md`):

1. **Now — dummy blueprint assets.** Create `BP` assets at `/Game/Blueprints/MTSunSky`
   and `/Game/Objects/GarageActorBP` (parent `Actor`) so `ChildActorClass` is an
   ordinary editor reference; exclude both from staging. Removes the temporary
   post-cook `--set-class-ref` step.
2. **Later — stub `MotorTown` C++ module** from the existing UHT dump, for direct
   `AMTSunSky` / `AMTGarageActor` / `AMotorTownRaceSection` access in-editor.
3. **Later — `UE4GameProjectGenerator`** over our UHT dump (+ game `.uproject` and
   `.upluginmanifest` extracted from the pak) to generate a full project.
4. **Later — `Suzie`** plugin, generating classes at editor startup and during cook
   from a live-game `.jmap` dump.

Trigger for 2–4: needing `AMotorTownRaceSection`, which has no blueprint counterpart
in the game's content tree, so dummying a BP cannot cover it.

### Hard constraint: the project has no game classes

`D:\UEProjects\C1` is a bare UE 5.5 project. It has **no MotorTown module and none of
the game's blueprint assets**, so in-editor spawning of `/Script/MotorTown.MTSunSky`,
`MTGarageActor`, `/Game/Blueprints/MTSunSky.MTSunSky_C` or
`/Game/Objects/GarageActorBP.GarageActorBP_C` fails with "class NOT FOUND". Verified
2026-11-03.

Consequences:
- Only **engine** classes can be authored in-editor: `PlayerStart`,
  `ExponentialHeightFog`, `DirectionalLight`, `SkyLight`, `SkyAtmosphere`.
- Lighting for Phase 1 therefore uses engine actors, not `MTSunSky`.
- Any game-class actor must either be (a) injected into the cooked level as a
  post-step — the very thing this plan forbids — or (b) obtainable as a project
  asset. There is no third option today.
- `AMTSunSky`'s constructor *does* create `SunLight`/`MoonLight`/`SkyLight`/
  `PostProcess` (`MTSunSky.cpp:26-36`) and `UpdateLighting()` is an empty stub, so a
  hand-injected native actor crashed only because it carried no serialised children.

## Course registration (what actually makes it a time-attack course)

Two separate assets, both required, neither touched by the old approach:

- `/Game/DataAsset/GameResource` (`MTGameResource`): `DriveMaps` and
  `TimeAttackMaps` arrays. Each row is `Key`, `Name`, `Level` (soft object),
  `bDevWorld`, `bAvailableInDemo`, `WorldMap` (`WorldMapTexture`,
  `WorldMapLocation`, `WorldMapSize`, `DefaultViewLocation`, `DefaultViewWidth`,
  `DefaultViewHeight`). Vanilla `TimeAttackMaps` holds 6 rows pointing at dedicated
  TA levels; `DriveMaps` holds 12 dev/test maps.
- `/Game/DataAsset/Courses` (`DataTable` of `MTCourseRow`): 13 rows keyed by course
  name (`AnsanSpeedway`, `Town_Circuit`, `OlleSpeedway_Kart`, …). From
  `MTCourseRow.h` the row is exactly `Name` (`FText`), `Name2` (`FMTTextByTexts`),
  `bUseOffTrack` (`bool`), `RacerXPPerLap` (`int32`) — no map reference, no
  `HeatDamageMultiplier`/`OverlapSlots` (those come from an unrelated row struct).
- **The course name lives on the road, not in the table.** `MotorTownRoad.h`:
  `AMotorTownRoad` has `RoadType`, **`CourseKey` (`FName`)**, `LaneWidth`,
  `NumForwardLanes`, `NumBackwardLanes`, `SpeedLimitKPH`, `RoadFlags`, and an
  `Instanced USplineComponent* Spline`.
- `MTLaptimeModule.h`: `FMTLaptimeModule` holds `TMap<FName, FMTLaptimeCourse>
  Courses`, `AMotorTownRoad* CourseRoad`, `AMotorTownRaceSection*
  OverlappedRaceSection`. `MTLaptimeCourse.h`: `FMTLaptimeCourse` = `Sections`
  (`TArray<AMotorTownRaceSection*>`) + `NumSections`. So lap gates are
  `AMotorTownRaceSection` actors carrying `CourseName` (`FName`),
  `RaceSectionIndex` (`int32`), `bIsStopBox` (`bool`).
- **Our roads map has the road but no course name**: `C1_Roads` contains
  `MotorTownRoad_2` (`LaneWidth 300`, 2 forward lanes, 60 km/h, spline bound) and
  `MotorTownNavigation_1`, and `CourseKey` appears **zero** times in the map.
- Vanilla TA persistent levels are **thin containers**: `PolygonTown_TimeAttack_01`
  imports only `TimeAttackGameModeBP`; `AnsanSpeedway_TimeAttack` holds just
  `World`/`WorldSettings`/`NavigationSystemModuleConfig`/`Model`/`LevelBounds` plus
  one `LevelStreamingAlwaysLoaded`. Course actors (road + sections) live in the
  streamed sublevels, which is the same shape our `C1` → `C1_Roads` split already has.
- The Nordschleife pak has **no** `GameResource`/`Courses` override, which is why it
  never appeared in any list and had to be launched directly.

Plan: set `CourseKey` on `C1_Roads/MotorTownRoad_2` (at generation time, not by
patching), add the matching `Courses` row via `--add-rows` from the vanilla asset,
and point `TimeAttackMaps`/`DriveMaps` at `/Game/Mods/C1/Maps/C1`.


## Observed results (2026-11-03, MVP build)

- **Loads.** `C1` starts from the time-attack list with no crash — the first configuration
  to load since the working NS-era build.
- **Geometry visible** — buildings seen in the distance.
- **Sun and sky present**, but the world is **too dark**.
- **No player character, no minimap, no map UI** — the level had no game mode, so no
  player controller was created. Cause identified: vanilla/NS levels set
  `WorldSettings.DefaultGameMode` (NS imports `Default__DriveGameModeBP_C`), our
  editor-authored level set nothing.
- Causally important: this also means the sky, geometry and pack pipeline are all
  sound; what was missing was game-mode wiring, not content.

Fix applied (build 235,623,194):
- Dummy BPs added for `/Game/GameMode/DriveGameModeBP` and
  `/Game/GameMode/TimeAttackGameModeBP` (parent `GameModeBase`), same dummying rule as
  the sky — never staged into the pak.
- `WorldSettings.DefaultGameMode` set in the editor. The editor's actor list excludes
  `WorldSettings`, so it must be reached via
  `GameplayStatics.get_actor_of_class(get_editor_world(), WorldSettings)` — iterating
  level actors returns nothing.
- Verified in the cook: `Export[161] WorldSettings` now carries
  `DefaultGameMode (Object): Index=-2` → `Import[1] DriveGameModeBP_C`, matching the NS
  level's shape.

Open item: the world is **too dark**. `MTSunSky` is spawned from the game's class with
its own defaults; whether MT drives time-of-day from it, or expects particular
serialized settings on the actor, is unresolved.

### Crash: dummy class as a serialized child actor (2026-11-03)

Setting `child_actor_class` on the `SunSky` component of the **level instance** made the
editor serialize a `MTSunSky_C_0` child actor. Load fails with:

```
LowLevelFatalError ... UObjectArchetype.cpp [Line: 175]
SceneComponent /Game/Blueprints/MTSunSky.Default__MTSunSky_C:RootSceneComponent had
RF_NeedLoad when being set up as an archetype of Class /Script/Engine.SceneComponent
in MTSunSky_C /Game/Mods/C1/Maps/C1.c1:PersistentLevel.MTSunSky_C_0
```

The dummy has no components, so the instance's component archetype cannot resolve. The
NS reference level never does this: it stores only a class import, no instance.

Rule: **dummy classes may be referenced, never instantiated.** After cooking, the map must
contain zero exports named `<DummyClass>_0`; `ChildActorClass` pointing at an import is
the correct shape. The class reference is applied to the cooked map with
`--set-class-ref`, which is a reference edit, not level surgery.



## Phases

### Phase 1 — a map that loads, is visible, and is a registered course
- Empty level `C1` with `PlayerStart`, `ExponentialHeightFog`, and `BP_C1_Sky` (plain
  `Actor` + `ChildActorComponent` `SunSky`, mirroring `BP_NS_Sky`) whose child class
  is the dummy `/Game/Blueprints/MTSunSky.MTSunSky_C`.
- No nav data, and do **not** set `bAutoSpawnMissingNavData`.
- `Courses` row `C1Shuto` cloned from the vanilla `Town_Circuit` row.
- `GameResource` rows: `TimeAttackMaps` + `DriveMaps`, `Key=C1Shuto`,
  `Level=/Game/Mods/C1/Maps/C1`, `WorldMapTexture` = vanilla `T_WorldMap_Jeju`.
  Both authored from the vanilla asset, not from the previously patched copy.
- Accept: map loads, is visible, appears in the time-attack list and starts.

### Phase 2 — geometry
- Spawn the 75 cell `StaticMeshActor`s from `cells_manifest.json` + extracted
  transforms; import materials/MIs as before (vanilla-parented at cook time, not by
  retargeting cooked MIs).
- Accept: corridor visible, drivable direction, no crash, cell seams align.

### Phase 3 — collision
- Per-mesh collision authored in the import settings, then cooked. Complex-as-simple
  only if a test proves it is needed and stable.
- Accept: facades stop the car, road surface is not jagged, no crash at load.

### Phase 4 — roads / nav / AI
- `DecalRoad` with the 1,379-point spline authored in the editor.
- Accept: AI NPCs use the road, `BuildNavigation` not required.

### Phase 5 — garage, spawn, extras
- `GarageActorBP` roadside, `PlayerStart` nearby, TA course settings if the row
  supports laps/checkpoints.
- Accept: garage usable, spawn next to it, course completable in time attack.

## Checklist (Phase 1)

- [x] Reference pak analysed (4,944 entries, V8B, mount `../../../`, Road/Sky/Props/Maps,
      no `GameResource`/`Courses` override)
- [x] Vanilla `Courses` and `GameResource` extracted and characterised
- [x] Vanilla TA level shape captured (`TimeAttackGameModeBP`, 2 always-loaded sublevels)
- [x] Editor can create `C1` level + `PlayerStart` + `ExponentialHeightFog`
- [x] Confirmed: game classes/BP assets unavailable in the project (engine classes only)
- [ ] Level carries `BP_C1_Sky` + `SunSky` child component; dump of the cooked map
      shows them
- [ ] Dummy `/Game/Blueprints/MTSunSky` exists in-project and is **excluded** from the
      staged pak
- [ ] `bAutoSpawnMissingNavData` absent or `False`
- [ ] Cook output contains `Maps/C1.umap` + `.uexp`
- [ ] `Courses` row `C1Shuto` added from the vanilla template (`--add-rows`)
- [ ] `GameResource` rebuilt from vanilla: 13 drive rows, 7 time-attack rows, no
      dangling object refs
- [ ] Pak built with `mod_pack`, V11, mount `../../../`, only our content
- [ ] Manifest written; zero `Nordschleife` strings in the pak
- [ ] Install: only vanilla + our pak in the mount path
- [ ] Game reaches gameplay on C1, world is lit
- [ ] C1 appears in the time-attack list and starts

## Non-goals
- No edits to a cooked `.umap` for shipping. Diagnostics may patch a copy, but a
  diagnostic build never becomes a release build.
- No Nordschleife content, meshes, materials or level in the shipped pak.
