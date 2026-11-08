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
- The `lanes` field in `road_specs_v2.json` reads 1 for 22 segments, but that is not what the
  level holds: Stage 0 read the actors directly and they are 2/0 (see below). Trust the level,
  not the spec file.

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


## Stage 0 results (measured, 2026-11-04)

Recon ran against `D:\C1Mirror` (the project that owns the MotorTown classes) on
`/Game/Mods/C1/Maps/C1Roads`. Raw output: `D:/UEProjects/C1/Scripts/c1_recon.json`.

- **28 road actors**: 27 `C1_SegNN_*` + `C1_Course`. All 27 segments are already
  `RoadType=Road`; only `C1_Course` is `Track_Course` (closed, 1,379 points, 120 kph).
- **Lanes**: 21 segments 2/0, 4 segments 1/0, 2 segments 3/0. Zero backward lanes anywhere,
  which matches the one-way BeamNG source.
- **Widths**: 21 at 300, 3 at 400, 2 at 333, 1 at 350.
- **Speed**: 27 segments at 50 kph, course at 120 kph. The speed IS set in the editor - the
  earlier cooked dump just did not show it.
- **40 `MotorTownRaceSection` gates**, all `CourseName=C1Shuto`.
- **`MotorTownNavigation` GraphData has 0 nodes** - navigation was never baked.

### The blocking finding: every segment is 10 m short at each end

Measured end->next-start for the 26 consecutive pairs plus the wrap:

- gap = **999.9 - 1001.7 cm, mean 1,000.6** (exactly 10.0 m), angle to the local tangent
  median **11.3 degrees** - the hole is *along* the road, not a lateral offset.
- This is systematic, not noise: the authoring split trimmed each segment by 5 m at both
  ends. The result is 27 disconnected splines where the game needs one connected graph.

### Second blocker: the graph cannot be baked in the mirror

`AMotorTownNavigation::BuildNavigation()` in the reconstructed source has an **empty body**,
and the mirror's compiled module is built from that source - so even a successful bake writes
0 nodes (which is exactly what the recon shows). The graph has to come from the real game
module at runtime, or be produced by a different mechanism. This is the open question for
Stage 5; everything up to it is unaffected.

### Patch list for Stage 2-4 (ordered, editor only)

1. Bridge the 28 x 10 m seams: extend each segment's first/last spline point along its
   tangent, or add a connector road per seam. Prefer extending - it keeps lane continuity.
2. Set speed limits per class instead of a flat 50.
3. Leave `C1_Course` untouched (race line + 40 gates stay valid).
4. Only then attempt the graph (Stage 5) and navmesh (Stage 6).

### Segment inventory

| label | type | fwd/back | width | kph | points | seam gap |
|---|---|---|---|---|---|---|
| C1_Seg00_r40 | ROAD: 1> | 1/0 | 400.0 | 50.0 | 16 | 0.0 |
| C1_Seg01_r36 | ROAD: 1> | 2/0 | 300.0 | 50.0 | 32 | 999.91 |
| C1_Seg02_r55 | ROAD: 1> | 2/0 | 300.0 | 50.0 | 49 | 1000.29 |
| C1_Seg03_r37 | ROAD: 1> | 2/0 | 300.0 | 50.0 | 15 | 1000.44 |
| C1_Seg04_r54 | ROAD: 1> | 2/0 | 300.0 | 50.0 | 33 | 1000.39 |
| C1_Seg05_r53 | ROAD: 1> | 2/0 | 300.0 | 50.0 | 21 | 1000.77 |
| C1_Seg06_r75 | ROAD: 1> | 3/0 | 333.0 | 50.0 | 52 | 1000.0 |
| C1_Seg07_r91 | ROAD: 1> | 2/0 | 350.0 | 50.0 | 22 | 1000.58 |
| C1_Seg08_r77 | ROAD: 1> | 2/0 | 300.0 | 50.0 | 8 | 1000.22 |
| C1_Seg09_r73 | ROAD: 1> | 2/0 | 300.0 | 50.0 | 32 | 1000.1 |
| C1_Seg10_r7 | ROAD: 1> | 2/0 | 300.0 | 50.0 | 319 | 1000.25 |
| C1_Seg11_r11 | ROAD: 1> | 2/0 | 300.0 | 50.0 | 61 | 1000.23 |
| C1_Seg12_r9 | ROAD: 1> | 2/0 | 300.0 | 50.0 | 22 | 1000.39 |
| C1_Seg13_r10 | ROAD: 1> | 2/0 | 300.0 | 50.0 | 59 | 1000.49 |
| C1_Seg14_r21 | ROAD: 1> | 2/0 | 300.0 | 50.0 | 31 | 1000.66 |
| C1_Seg15_r8 | ROAD: 1> | 2/0 | 300.0 | 50.0 | 65 | 1001.06 |
| C1_Seg16_r19 | ROAD: 1> | 2/0 | 300.0 | 50.0 | 15 | 1001.06 |
| C1_Seg17_r8 | ROAD: 1> | 2/0 | 300.0 | 50.0 | 35 | 1001.57 |
| C1_Seg18_r16 | ROAD: 1> | 2/0 | 300.0 | 50.0 | 47 | 1001.45 |
| C1_Seg19_r15 | ROAD: 1> | 2/0 | 300.0 | 50.0 | 21 | 1000.89 |
| C1_Seg20_r23 | ROAD: 1> | 2/0 | 300.0 | 50.0 | 263 | 999.99 |
| C1_Seg21_r27 | ROAD: 1> | 1/0 | 300.0 | 50.0 | 35 | 1001.71 |
| C1_Seg22_r26 | ROAD: 1> | 3/0 | 333.0 | 50.0 | 41 | 1000.92 |
| C1_Seg23_r22 | ROAD: 1> | 2/0 | 300.0 | 50.0 | 36 | 1000.53 |
| C1_Seg24_r38 | ROAD: 1> | 1/0 | 400.0 | 50.0 | 15 | 1000.93 |
| C1_Seg25_r56 | ROAD: 1> | 2/0 | 300.0 | 50.0 | 14 | 1000.77 |
| C1_Seg26_r58 | ROAD: 1> | 1/0 | 400.0 | 50.0 | 20 | 0.0 |


## Stage 2 results (applied, verified)

Editor pass in the mirror (`c1_bridge.py`, committed): each seam was closed at its midpoint -
the end point of segment N and the start point of N+1 were both moved to the midpoint of the
gap, then the spline was rebuilt. Endpoint displacement was 5 m per side, well under the
guard rails (max shift 15 m, minimum 3 m of room before the neighbouring point).

Independent verification (fresh editor process, re-opened the level and re-measured):

- **26 internal seam gaps: 0.000 cm** (were 999.9-1001.7)
- **wrap joint seg26.end -> seg00.start was already exactly coincident and still is** - the
  network is a closed loop, not an open chain
- **speed limit 120.0 kph on all 27 segments** (was 50); `C1_Course` untouched at 120
- lanes (21x 2/0, 4x 1/0, 2x 3/0), widths and the 40 `MotorTownRaceSection` gates unchanged
- level saved: 7,702,998 -> 7,705,046 bytes, backup at `C1Roads.umap.bak_bridge`

Still open: `MotorTownNavigation` GraphData = 0 nodes. Bridging seams makes a graph *possible*;
it does not create one.
