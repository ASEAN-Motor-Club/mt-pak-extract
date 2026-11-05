# C1 Shuto — implementation record and reproducible pipeline

This document is the authoritative description of how the C1 map mod is built, why
each step exists, and what makes it reproducible. It exists because the same work
must be repeated when the **full map** is imported: the numbers will change, the
procedure must not.

Everything here is derived from a working build, not from documentation of intent.
Where a claim was disproved, it is recorded as disproved so it is not re-attempted.

---

## 1. What the map actually is

C1 is a ported Shuto expressway. The source is a BeamNG mod whose AI routing lives in
`levels/<map>/main/missiongroup/<group>/items.level.json` as `DecalRoad` objects —
one JSON object per line. Art-only extractions contain **no** routing data.

The ported level carries three separate layers, and confusing them is the single most
expensive mistake in this project:

| Layer | Package | Lives in | Who reads it |
|---|---|---|---|
| Visual geometry | `C1.umap` + content assets | client + server pak | renderer |
| Roads / navigation / AI spawner | `C1_Roads.umap` + `.uexp` (streamed sublevel) | client + server pak | engine, AI |
| Baked traffic graph | inside `C1_Roads.uexp` (`AMotorTownNavigation.GraphData`) | both paks | AI only (server relevant) |

`C1_Roads` is a **streamed sublevel**, so it only loads if `C1.umap`'s `UWorld` block
registers it. A `LevelStreamingAlwaysLoaded` export is inert on its own — the engine
reads streaming levels from the native `UWorld` block, not the export table. The
working map is one whose `UWorld` block was written by a cook of an editor level that
genuinely had the sublevel attached.

A cooked map package is a **pair**: `Maps/C1_Roads.umap` is a ~6–27 KB header, and
`Maps/C1_Roads.uexp` is the payload (1.0–15.9 MB) holding actor properties and the
whole graph. A "tiny cooked map" is not necessarily a broken cook — check the `.uexp`.

---

## 2. Determinism contract

Five things decide whether a rebuild reproduces the shipped artifact.

**Frozen inputs (must be pinned, hashed, and archived):**

1. `c1/decal_roads_v1.json` — the road set derived from the BeamNG source. Commit it.
   The pipeline never reads the source archive directly at build time.
2. `c1/pipeline/constants.json` — every tunable constant (below).
3. `c1/tools/author_traffic_spawner.py` — the spawner rows are **embedded in the
   script** (`ROWS = json.loads(r"""…""")`), not read from a sibling JSON. Editing the
   sibling file changes nothing; that cost two wasted bake cycles.
4. `csharp/UAssetTool` — post-cook patching. The `--set-array-class-ref` mode is
   required and must be present in the built binary.
5. `repak` (packing) and the UE 5.5 cook. Cook output is **not** byte-reproducible
   across machines (embedded build/timestamp data); pak bytes therefore vary while
   content does not.

**Ordering:** the baker samples roads sorted by actor label (`roads.sort(key=label)`),
and the spatial-hash iteration preserves insertion order, so node indices, edges and
the bake report are reproducible for a given level + constants. Do not remove that
sort **or the next rebuild silently renumbers every node.**

**Acceptance criteria (hard):**

- `dead_ends == 0` — the only graph property that has ever predicted in-game behaviour.
- `nodes`, `cross_links`, `lane_change` equal to the recorded baseline for that road
  set (they change when the map changes; they must not change when it does not).
- `nodes_with_road == nav_nodes` and `nodes_null_road == 0` on the live server — a
  graph that lost its road references after cook is a broken bake.

**Pak bytes are reproducible if you pin the packer.** `repak` compresses entries on a
rayon pool and writes them in completion order: three packs of the same tree produced
three hashes (`5a5f9860…`, `4ba2f756…`, `95747cd5…`) at an identical 68,764,212 bytes.
With `RAYON_NUM_THREADS=1` the same three runs produce one hash (`7e482fab…`). Stage 7
sets it, so identical trees now give identical paks — the residue is the cook.

**What is legitimately non-deterministic:** cooked `.uexp` bytes (embedded build data),
and therefore any count or hash that depends on the source road set. Verify *content* (file list,
property values, `.uexp` size within reason), not pak hashes.

---

## 3. Coordinate and lane model

- Source frame → level frame: **pure Y mirror, no offset**, yaw negated:
  `(x, -y, z)`, `yaw → -yaw`. Assert `max(Y) < 0` in the authoring script so a missed
  mirror fails loudly.
- Units: cm. `LaneWidth` and spline coordinates are centimetres; `SpeedLimitKPH` is
  km/h; **graph node `SpeedLimit` is cm/s** (`km/h × 27.78`).
- Lane geometry: lanes **tile** the carriageway.
  `lane_width × (num_forward + num_backward) == decal width` holds on every road of
  the port (verified on all 155). Therefore lane centres are measured from the road
  edges:

  ```
  total_w = lane_width * (nf + nb)
  forward lane k  (k = 1..nf):  lateral = -total_w/2 + (k - 0.5) * lane_width   # LHT: +1 leftmost
  oncoming lane -k (k = 1..nb): lateral = +total_w/2 - (k - 0.5) * lane_width
  ```

  The intuitive `(abs(lane) - 0.5) * lane_width` stacks outward from the centreline
  and puts lane 2 of a 2-lane 3.5 m road at 5.25 m from a centreline whose half-width
  is 3.5 m — 1.75 m off the tarmac. That was the "lanes don't align with the geometry"
  bug: AI drove into barriers, separators and columns.
- **Oncoming lanes must reverse the travel frame.** A `-N` lane node inherits the
  spline tangent, which is the *forward* direction. Negate direction **and** right
  vector for `lane < 0`; keep the lateral offset on the spline's own right vector or
  the lane jumps to the wrong side.
- **Handedness:** the map is LHT while MotorTown's AI keeps right. Numbering lanes
  from the **left** edge makes the AI-preferred `+1` the LHT slow lane. This only
  works if the AI selects by lane index; if it selects by lateral offset the mirror
  is inert and the fallback is one lane per carriageway.
- Opposite directions are **separate road actors**, never backward lanes on a one-way
  actor. The port has 3 genuine opposed pairs (`dot = -1.00`, 8.5–12 m apart).

---

## 4. Graph construction rules

A node is one sample point on one lane. Node count ≈ `sum(points × lanes)`.

- Sample step: **1000 cm** along each lane.
- Edges along a lane: cost `0.0`, distance = spacing (matches the shipped Jeju
  distribution; `Flags = 0`, `CrossroadId = -1`, `IslandId = 0` sample values are
  inside the shipped histogram — do not "fix" them).
- **Connect every node, not just road endpoints.** Endpoint-only linking leaves every
  mid-road merge and on-ramp with no outgoing edge; in game that is "the car drives a
  stretch then stops". Rule: each node links to the nearest node of a **different**
  road within `connect_any_cm = 4000`, same lane sign, forward dot ≥ `0.55`.
- **Lane-change edges** between adjacent lanes at the same spline point, non-zero cost
  (`30.0`), so traveling straight stays preferred and no lane becomes its own island.
- **Near-parallel guard:** skip a cross-road link when the candidate is closer than
  `parallel_skip_cm = 400` **and** near-parallel (`dot > 0.90`). Junction links
  survive because their tangents are perpendicular. On the current map this rejects
  574 candidates and changes nothing (the graph is identical) — it is a guard against
  future map edits, **not** a fix, and must not be presented as one.

Acceptance: `dead_ends == 0`. Log the count on every bake.

---

## 5. AI spawn layer

Traffic requires four things simultaneously; three of them failing silently is normal.

1. **Game type `Driving`**, on a dedicated server. Time Attack has no spawner.
2. **`AMTAIVehicleSpawnSystem` in the level** — a single reference `gameState.AIVehicleSpawnSystem`.
3. **`VehicleTypes` non-empty per setting** — set via struct text import:
   `s.import_text("(VehicleTypes=(2,3))")`; `EMTVehicleType` is not exported to Python.
4. **`VehicleClass` referencing a shipped vehicle BP** — injected **post-cook**, never
   authored in the editor and never bound at runtime.

Traffic only exists near players (`bDespawnIfPlayersAreFar`), so an empty server always
reports zero vehicles. Never read that as a regression.

Two structural rules learned the hard way:

- Non-traffic rows are zeroed **in the embedded `ROWS`** inside
  `c1/tools/author_traffic_spawner.py`. Mutating the array in the editor does not
  persist (struct copies), and a sibling JSON file is not read at all.
- `WorldSettings.DefaultGameMode` is **not** the traffic gate on a dedicated server. A
  server pak with no `DefaultGameMode` property at all still runs traffic. Keep the
  ref for correctness; do not expect it to spawn anything.

`--set-class-ref` cannot reach an `ObjectProperty` inside a `TArray<FStruct>`; that is
why `UAssetTool --set-array-class-ref` exists:

```
UAssetTool --set-array-class-ref <in.umap> <out.umap> \
  MTAIVehicleSpawnSystem_0 SpawnSettings SettingKey VehicleClass <vc_map.json>
```

`vc_map.json` maps `SettingKey → [package path, class name]`. Verify by dumping the
written package and expecting a **negative import index** per patched row.

---

## 6. Pipeline stages

Every stage is a script in `c1/pipeline/`, takes explicit paths, and prints an
acceptance line. `run_all.sh` chains them; each can be run alone.

| Stage | Script | Runs on | Output |
|---|---|---|---|
| 0 | `00_env.sh` | anywhere | exports paths/versions |
| 1 | `01_decal_specs.sh` | container | `road_specs_v2.json` from BeamNG source |
| 2 | `02_author_roads.sh` | editor (mirror project) | `C1Roads` level: 54 road actors |
| 3 | `03_bake_nav.sh` | editor | `GraphData` in the level + report line |
| 4 | `04_author_spawner.sh` | editor | `AMTAIVehicleSpawnSystem`, 16 settings |
| 5 | `05_cook.ps1` | Windows | cooked `Maps/C1Roads.umap/.uexp` |
| 6 | `06_postcook_patch.sh` | container | class refs + `VehicleClass` injected |
| 7 | `07_pack.sh` | container/host | compressed pak (V11, zlib) |
| 7b | `07b_build_release_paks.sh` | container/host | **both** server and client paks |
| 8 | `08_deploy_staging.sh` | staging host | pak in `.mod-cache`, server restarted |
| 9 | `09_verify.sh` | staging host | graph + pak assertions |

### Stage notes that are not obvious

**5 — cook.** The map cooks from the **mirror client project** (`D:\C1Mirror`,
Windows target), not from a WindowsServer project: the latter yields a 787-byte
`.uexp` stub because the level content lives in the mirror. The cook must go through
`cook_roads.bat`, because the bare `-run=cook -map=…` invocation exits `rc=1` in three
seconds when the project's plugin DLLs are not on `PATH`. Judge the cook by
`LogCook: Display: Done!` and the output mtime, never by the exit code alone.

**6 — post-cook patch.** Two different maps, two different fixes:

- `C1.umap` (parent): `pipeline/repair_class_refs.sh` writes `DefaultGameMode`,
  `SunSky.ChildActorClass`, `Child.ChildActorClass`. It **fails on `C1_Roads`** — that
  sublevel has no `WorldSettings`/`SunSky`/`Child` exports ("no export named SunSky").
- `C1_Roads` (sublevel): only `--set-array-class-ref` for the spawner.

`UAssetAPI`/UAssetTool needs the `.uexp` beside the `.umap`, absolute paths, and on
.NET 10 a runtime roll-forward: `DOTNET_ROLL_FORWARD=Major` and
`DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1`.

**7b — both artifacts.** Server and client are assembled from their own base
paks, never from each other: the client pak carries 10,039 files and its own
`C1.umap` (the one registering the streaming level), the server pak 8,056. The
client's map layer is merged by extracting the published client pak, overlaying
`Maps/C1.umap` + `Maps/C1_Roads.*` + the two `BP_C1_*` actors, and repacking —
the same operation that was done by hand for the v4 release, now scripted.

**7 — pack.** `mod_pack` in this tree has no compression flag; use `repak`:

```
repak pack -m "../../../MotorTown/Content/Mods/C1/" --version V11 --compression Zlib dir out.pak
```

`mod_pack` and `mod_explore` also matter behaviourally: `mod_explore --extract-all`
**ignores its output-dir argument** and always writes `./mod_out` relative to the
process CWD. `cd` into a scratch dir first.

**8 — deploy.** Install into `<state>/.mod-cache/paks/<name>.pak`, keep the filename
stable (`zzz_AMC_C1_Server_v3_P.pak` while iterating) because the operator approves
paks by name, and restart as its own command. Pre-start copies from the cache and
wipes non-base paks in `Content/Paks/`.

### Rebuild loop in practice

```
bake → read 4 counts → (unchanged? stop, do not cook)
     → cook → pull .umap/.uexp → patch → pack → deploy → restart → probe
```

The "stop if the four counts are unchanged" rule is what prevented shipping a
placebo on the parallel-link guard.

---

## 7. Packaging and release layout

Client install is **one content pak plus small extras**, all at mount
`../../../MotorTown/Content/Mods/C1/`:

- `zzz_AMC_C1_P.pak` — content **and** the road layer (`Maps/C1.umap` with the
  streaming link, `Maps/C1_Roads.*`, `BP_C1_Prop`, `BP_C1_Sky`).
- `zzzz_AMC_C1Mats_P.pak`, `zzz_AMC_C1Courses_P.pak`, `zzz_AMC_C1Offline_P.pak`.

Load order is filename order; `zzzz_` sorts after `zzz_`. Before the consolidation,
the road layer shipped as a separate `zzzz_…Map…` overlay needed precisely because a
pak cannot merge into another pak — the merge was done by extracting, overlaying, and
repacking, not by mounting two paks.

Server artifact is a separate full pak built from the same cooked map bytes.

Publishing rules (store `/var/lib/mod-releases/mods/`, hand-out `/root/download/`,
public `/releases/mods/<name>.pak`):

- versioned filenames, collision guard (`[ -e ] && exit 2`) plus `cp -n`;
- capture `sha256sum` of existing paks before, verify after (`sha256sum -c`);
- superseded artifacts go to `mods/archive/` — **outside** the served directory, or
  they remain downloadable under the old name;
- verify distribution with a ranged GET (`206`, 1024 bytes), not just the copy;
- leave exactly one pak per generation for artifacts published in the same session.

---

## 8. Verification ladder

Each rung fails independently; all of them together mean the build is right.

1. **Bake** — `dead_ends = 0`, counts equal to baseline (`C1BAKE_DONE` line).
2. **Cook** — `LogCook: Done!`, `.uexp` size plausible (graph present), mtime moved.
3. **Patch** — dump shows `VehicleClass` import indices negative; `DriveGameModeBP`,
   `MTSunSky`, `GarageActorBP` present; **no** `_C_N` child-actor instances.
4. **Pak** — `mod_explore <pak> --list`: mount point, file count, `Maps/C1_Roads.uexp`
   size, expected extras.
5. **Server load** — `nav_nodes`, `nodes_with_road == nav_nodes`, `nodes_null_road = 0`,
   `spawn_system_valid: true`, with `player_count` beside any vehicle count.
6. **In game** — traffic flows, keeps to the correct lane, does not stop mid-road.

Rungs 1–4 are scripted (`09_verify.sh`, `07_pack.sh`); rung 6 is a human check.

---

## 9. Disproved leads — do not re-attempt

Recorded because each cost a build cycle and each looks plausible.

- **`Flags = 1030` / `CrossroadId` / `IslandId` tuning.** A 60-node sample from one
  junction was unrepresentative; whole-graph histograms put `Flags = 0` as the
  plurality. Copying 1030 onto all nodes removed every spawn attempt.
- **Runtime class binding** (`LoadAsset` onto `settings[i].VehicleClass`). Works as a
  diagnostic, rejected as a fix — the map must carry the reference post-cook, like the
  garage/sunsky refs.
- **`BuildNavigation()` at runtime.** A measured no-op on custom road sets; the graph
  must be baked at authoring time from editor Python.
- **Corridor fusion via cross-road links.** Guard rejects 574 candidates and produces
  an identical graph; parallel twins were never linked in the first place.
- **Elevation as an explanation for apparent road overlap.** 114 overlapping
  candidates were all within 3 m of each other; tunnels did not mask anything.
- **Minimum-distance as an overlap test.** It collapses to ~0 wherever two roads meet
  at a junction and reported 35 of 40 pairs as overlapping when 3 are real.
- **Raycast lane-alignment audits in the editor.** No collision exists in the editor
  world: 14,183 traces, 14,183 misses. Reads exactly like "every lane is off the
  geometry" and is meaningless.
- **RE of the spawner** (Ghidra, 156 MB stripped exe, FName pool entries referenced by
  index). Several hours in, unnecessary once placement was proven to work. The project
  and anchors are recorded; treat it as a last resort, not a first step.

---

## 10. Repeating this for the full map

What changes, what must not.

**Changes:**

- `01_decal_specs` input: the full `items.level.json`. Re-derive the bbox filter
  (keep decals with ≥60 % of nodes inside the map's geometry bbox) and expect the road
  count to rise well above 54.
- Bake counts: `nodes`, `cross_links`, `lane_change` all grow. Record the new baseline
  in `constants.json` — that file is the regression guard.
- Spawn settings: more settings may be worth enabling across a larger map; keep
  service/Getaway rows at `MaxCount = 0` unless explicitly wanted.
- Cook time and `.uexp` size (already 15.9 MB at 54 roads).
- Pak sizes; if the client pak exceeds ~500 MB, reconsider whether the road layer
  belongs in a separate pak after all.

**Must not change:**

- The lane offset formula, the oncoming travel-frame reversal, the LHT numbering.
- `step_cm = 1000`, `forward_dot = 0.55`, lane-change cost `30.0`, edge cost `0.0`.
- `dead_ends == 0` as the acceptance criterion.
- Post-cook patching (never runtime binding), and the two-map split in stage 6.
- Single stable pak filename while iterating; versioned filename only at publish.
- The verification ladder.

**Sanity checks specific to a bigger map:**

- Audit `lane_width` distribution **before** believing any lane complaint:
  `Counter(lane_width)`. Values above ~400 cm flag an under-declared carriageway
  (four 10 m roads were authored as 2 × 500 cm where the art shows 3 lanes at 333 cm).
- Check for near-neighbour actors: a wide actor beside a narrow one reads as extra
  lanes even when both are declared correctly (`C1_Rd029` 13 m/4-lane sits 131 cm from
  `C1_Rd028` 6 m/2-lane).
- Expect more genuine opposed pairs; identify them by midpoint **tangent dot = -1**
  with separation < `(wa+wb)/2` sustained over a stretch, never by closest point.

---

## 11. File map

```
c1/
  decal_roads_v1.json          frozen road set (source of truth for the bake)
  road_specs_v2.json           derived authoring spec (stage 1 output)
  docs/C1_PIPELINE.md          this document
  pipeline/
    constants.json             every frozen constant + baseline counts
    nav_bake_config.json       bake config consumed by the baker
    vc_map.json                SpatialKey -> vehicle class map for post-cook patch
    00_env.sh … 09_verify.sh   the stages
    run_all.sh                 driver
    repair_class_refs.sh       parent-map class refs (existing)
  tools/
    build_decal_specs.py       BeamNG items.level.json -> specs
    author_decal_roads.py      spawn MotorTownRoad actors
    c1_bake_nav.py             bake GraphData (deterministic, sorted)
    author_traffic_spawner.py  AMTAIVehicleSpawnSystem + embedded ROWS
```
