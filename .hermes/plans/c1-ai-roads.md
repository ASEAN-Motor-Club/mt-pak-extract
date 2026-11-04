# C1: one-way LHT splines -> MT traffic roads (RHT), with AI traffic

Editor-first. No UAssetTool byte edits on the map; the post-cook class-ref repair stays
the only non-editor step.

## Source truth: BeamNG DecalRoad

From `ported-map-extension/references/beamng-source-model.md` (measured on this map):

- 155 `DecalRoad`, 6,040 nodes, 209.72 km, material `road_invisible`, `drivability: 1`.
- **Every road is `oneWay: true`.** There are no two-way carriageways to reproduce.
- Lane counts come from `lanesLeft` / `lanesRight`; **2/0 over 84 % of the C1 loop length**,
  i.e. two lanes, both on the left of the spline (Japan keeps left).
- Node widths 3-10 m, median 7 m.
- Graph is one connected component, 8,282 junction links.

## Our current C1_Roads (parsed from the shipped pak)

- 28 `MotorTownRoad` actors. 27 serialise `2 forward / 0 backward`? **No** - they serialise
  `NumForwardLanes` from the authored spec: 22 segments = 1 lane, 4 = 2 lanes, 2 = 3 lanes;
  `NumBackwardLanes` = 0 everywhere. `LaneWidth` 300 (two at 333/3-lane, two at 350).
- `SpeedLimitKPH` is serialised nowhere -> every road sits on the 30 kph CDO default.
- Only `MotorTownRoad_27` has `RoadType=Track_Course`, `CourseKey=C1Shuto` - the race line.
  The other 27 inherit `Road`.
- **Discrepancy to resolve:** the source is 2/0 for 84 % of loop length, but 22 of our 28
  segments carry a single forward lane. Either the authoring split reduced lanes, or lane
  counts were derived per-segment rather than per-road. Must be reconciled against the
  source before anything else changes.

## LHT -> RHT is already solved by the frame

The map transform is a pure Y mirror `(x, -y, z)` with negated yaw. A reflection swaps
left and right (v x p flips sign), so "keep left" in BeamNG becomes "keep right" in the
mirrored level - which is exactly MT's right-hand-traffic convention. Consequence:
BeamNG `lanesLeft` maps to MT `NumForwardLanes`, `lanesRight` to `NumBackwardLanes`, and
because `lanesRight` is 0 everywhere the result is one-way forward traffic.
Verify once against a stock MT road (spline vs lane offsets) before trusting it wholesale.

## Stages

0. Recon + source restore.
   - Re-fetch the BeamNG level (the mod pak the map came from) - the local extraction was
     pruned - and re-read `DecalRoad` nodes/lanes.
   - Editor script lists every road actor: RoadType, CourseKey, lanes, width, speed, flags,
     spline point count, start/end coords, end->next-start gap.
   - Per segment: reconcile authored lane count vs source `lanesLeft`; measure lateral
     offset between the spline and the visible pavement (is our spline on the tarmac
     centre, or on the lane edge?). Output JSON report, no writes.
1. Layout decisions (freeman): keep 1-lane segments or restore 2 where the source says 2;
   speed limits per class of road (mainline vs ramp vs narrow street); whether the race
   line stays `Track_Course`.
2. Properties, editor: `RoadType=Road` on traffic splines (already default), clear
   `CourseKey` there, set `NumForwardLanes` / `NumBackwardLanes=0` / `LaneWidth` /
   `SpeedLimitKPH` / `RoadFlags`. Keep the `Track_Course` actor untouched for racing.
3. Lane geometry, editor: if Stage 0 shows the spline sits on the lane edge rather than the
   carriageway centre, offset the spline laterally by half the lane span so MT's
   right-hand lane placement lands on the tarmac. Re-check against the mesh.
4. Topology, editor: snap segment endpoints within tolerance so the graph connects (source
   is one connected component across 155 roads; our 28 splits create 27 seams). Close the
   loop, drop the duplicate 28th actor.
5. Navmesh, late: NavMeshBoundsVolume over the course + Recast, build paths (characters,
   not traffic).
6. Navigation graph, late: `BuildNavigation()`, then verify `GraphData` node/edge counts and
   bounds. Risk: reconstructed `MotorTownNavigation.cpp` has an empty `BuildNavigation()`
   body - confirm the editor module actually populates `GraphData`.
7. Traffic validation: PIE, then staging with `NPCVehicleDensity > 0`; watch for stops at
   seams and cars driving beside the tarmac (that means Stage 3 offset is wrong).
8. Bake, cook, ship: client cook + class-ref repair, WindowsServer cook, verify, publish v3.

## Risks

- One-way source means traffic is generated on one-way roads only; MT's AI may expect
  two-way routing. If vehicles refuse to spawn or route, model the few genuinely two-way
  stretches (railway-parallel streets) as separate opposite splines rather than inventing
  return lanes.
- Lane properties do not change the visual mesh; a wrong offset or width puts AI off the
  pavement.
- Race course must keep working: keep the `Track_Course` line or re-derive `CourseKey`.
- Navmesh + graph bakes are the expensive steps; they stay last.
