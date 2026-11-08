# Stage 0 finding: the road set is the racing line, not the AI path network

Measured 2026-11-04 against the live game and the BeamNG source.

## What the current 27 segments actually are

They are contiguous slices of the single 1,379-point course polyline (see `road_specs_v2.json`:
each segment is an `start`/`end` index range into the same `points` array). Total length
**13.79 km**, one closed loop, all one-way. They follow the racing line, not the carriageways.

## What the source actually contains

- **155 DecalRoad paths**, 6,040 nodes, **209.7 km** total, every one `oneWay: true`,
  `lanesLeft: 2` / `lanesRight: 0` (67 explicit, the rest declare only the left count).
- **26 of them lie on the 13.79 km loop** (17.7 km of path); the other **129 are off-loop**
  (192.0 km): ramps, slip roads, elevated branches, surface streets.
- **35 parallel-opposite pairs** within 60 m - the opposing carriageways the user described,
  including stacked duplicates. Each direction is its own one-way path with its own Z.
- On-loop paths are short fragments (0.14-0.65 km) plus a few long ones (3.87, 3.89 km),
  joined by 23 end-to-start links under 15 m.

## Why this matters

MT expects one-way lane paths as roads (stock Jeju: 490 roads -> 17,619 graph nodes). Our
racing-line slices give the AI a single centre path around the loop with no carriageway
separation, no ramps, and no second direction - a graph built from them would not match the
map's real roads.

## Options

1. **Full decal rebuild** - one road actor per DecalRoad (155), lanes from `lanesLeft`,
   width from node widths, one-way, speed 120. Keeps both carriageways and the whole
   expressway network, matches how MT maps are built. ~6,040 spline points total.
2. **Loop-only rebuild** - the 26 on-loop paths (17.7 km). Both directions of the loop,
   no ramps/surface network. Smaller, faster, but traffic cannot leave the loop.
3. **Keep the 27 + add the opposite carriageway by offset** - rejected: stacked sections
   make a lateral offset wrong, and it invents geometry that is not in the source.

`C1_Course` (Track_Course, 1,379 points, `C1Shuto`) stays untouched in every option - it
drives the 40 race gates, not traffic.
