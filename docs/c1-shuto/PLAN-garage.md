# PLAN — garage actors on the C1 map

Status: SHIPPED and verified in game, 2026-11-15 (plan written 2026-11-03).

## As built (current live state)

- **`zzzzzz_AMC_C1Map_v17_P.pak`** — six garages, one fuel pump, `MTSunSky`,
  `DriveGameModeBP_C`, PlayerStart at Shibaura. Reproducible chain:
  `c1/scripts/apply_map_edits_v17.sh`.
- Garage markers `BP_C1_Prop_C_0..C_5`, each `Child.ChildActorClass = GarageActorBP_C`:
  Shibaura (110237,-470902,87411), Tatsumi (593234,-466784,87449),
  Yotsuyakamicho (83167,406270,84990), Haneda (381965,511319,85216),
  Shin-yamashita (-844349,1606825,86672), Heiwajima (-13950,146710,85530).
- Fuel pump marker `BP_C1_Fuel_C_0` at (-10260,155550,85540), cloned from a garage
  marker then re-pointed at `FuelPump_01A_C`. Runtime probe: `GARAGES 6 / PUMPS 1`.
- Extra sites are added by `--clone-actor` on the map, NOT by re-running placement:
  a clone inherits the source component's class ref, so a garage clone needs no
  further patch. Only a different class (fuel) needs `--set-child-class-refs`
  again, which is why each class group needs its own actor-name prefix.
- **`/tp <name>` on the Shuto server** targets these six garages at Z+100.
  Implementation and the no-backend gating: MTDediMod PR #57, Nix location list and
  `MOD_TP_LOCATIONS_FILE`: amc-server PR #569.

## Failure that shaped the final design

Setting `ChildActorClass` on the **Blueprint template** (`BP_C1_Prop`'s
`Child_GEN_VARIABLE`) instead of the map instances crashed the client on map open
(access violation in child-actor construction). The class ref belongs on the map
instances only, and the dump gate is `NO_BAKED_CHILD` — no `GarageActorBP_C_N` /
`FuelPump_01A_C_N` / `MTSunSky_C_N` export may appear in the cooked umap.

## Verification gates

## What NS actually does (measured, not assumed)

Extracted `NS_Nordschleife.umap` from `ZZ_Nordschleife_P.pak` (3,948 exports) and dumped it.

- NS ships **no garage assets of its own**. Its pak has only `BP_NS_Prop`, `BP_NS_Sky` and the
  two maps. Everything gameplay-facing is a reference into the base game.
- The garage class is reached through the **import table**, not an export:
  `Import[5] BlueprintGeneratedClass GarageActorBP_C` (Outer → `/Game/Objects/GarageActorBP`)
  plus the CDO import `Default__GarageActorBP_C` (Import[29]).
- Instances are **`ChildActorComponent`s with `ChildActorClass` overridden per level instance**:
  - 21 × `ChildActorClass = Import[5]` → `GarageActorBP_C`
  - 2 × `Import[4]` → `FuelPump_01A_C`
  - 1 × `Import[0]` → `MTSunSky_C` (the sky, same trick we already use)
- Those components live on **24 `BP_NS_Prop_C` actors** placed in the level; NS's own
  `BP_NS_Prop` is a bare `Actor` with one `ChildActorComponent` named `Child`.
- So the pattern is: *own* dumb actor + per-instance child class = base-game actor, by path.

## What the garage actor is

Extracted `MotorTown/Content/Objects/GarageActorBP` from `v0.7.19.pak`:

- Parent class is native: **`MTGarageActor`** (`/Script/MotorTown`). The BP only adds a
  `DefaultSceneRoot`, an `InteractionCube` (from `/Game/Objects/InteractionCube`, carrying an
  `MTInteractableComponent`) and a `Camera`.
- No gameplay-configurable properties are serialized on the BP. **The garage is configured
  entirely by its world transform** — that is why NS can place 21 of them with no per-actor data
  and no DataTable rows.

## Approach for C1 (same shape as the sky, extended)

1. **Author a prop BP in the project** — `BP_C1_Prop`, parent `Actor`, one `ChildActorComponent`
   named `Child`. Cooked offline exactly like `BP_C1_Sky` (`build_sky_bp.py` is the template).
2. **Place instances** at garage sites in `build_mvp_level.py` (or a new
   `build_props.py`), each with its own transform. Nothing MT-specific is referenced in-editor,
   so the cook stays valid without MT content.
3. **Post-cook patch**: point each prop instance's `Child` component at
   `/Game/Objects/GarageActorBP` + `GarageActorBP_C`, adding the package + BGP imports. This is
   the same operation as `--set-class-ref` (the sanctioned post-cook mutation), but it has to
   run over **many** actors.
   - New tool op: `--set-child-class-refs <in> <out> <actorNamePrefix> <componentName>
     <packagePath> <className>` — matches all exports whose name starts with the prefix instead
     of a single export name.
4. **Pack + install** through the existing `mvp_deploy` path, class-ref for the sky unchanged.

## Placement

C1 corridor is the 74-cell / ~14 km loop. Garages need a reachable, flat, off-carriageway spot,
which the BeamNG source does not mark. Proposal:

- **1 garage at the spawn cell** (`c3_13`, SPAWN=(169915, −692979, 84352), yaw 155.9) so the map
  is usable immediately.
- **Then N along the spline** (`c1_road_points.json`, 1,379 points): walk the loop and drop one
  every ~2 km, offset laterally to the left shoulder (Japan drives on the left), z + 100,
  then snap to the nearest cell's top surface.
- Placement generation lives in `props_place.py` and emits a JSON consumed by
  `build_props.py`, so positions are data, not code.

Open decisions: garage count, and whether to include the 2 fuel pumps (same mechanism,
`/Game/Objects/Fuel/FuelPump_01A` + `FuelPump_01A_C`).

## Verification gates

- Offline: cooked umap dump shows exactly N exports whose component references
  `GarageActorBP_C`, and zero unresolved imports (`--dump` header check).
- In-game, per garage: interaction prompt appears, garage can be bought/opened, vehicle stored
  and retrieved, and the site is reachable by car without clipping.
- Server: the pak is the same on client and dedicated server; confirm one garage registers on
  the staging server before any production copy.

## Risks

- **Transform-only config** means a garage placed inside geometry, on a slope, or with its
  interaction cube inside a wall is unusable. Positions must be checked on foot/in car.
- **No map/UI registration evidence yet.** NS places actors with no DataTable rows, so the
  assumption is that `MTGarageActor` self-registers; if the garage works in-game but does not
  appear on the map screen, that is a separate (DataAsset) problem, not a placement bug.
- **Child actor spawning**: `ChildActor` must stay null on the component so it is constructed at
  runtime; if a patch ever writes a non-null `ChildActor`, the garage spawns twice or not at all.
- The 21 garages in NS are spread over a ~20 km circuit; C1's 14 km loop suggests ~8–10.
