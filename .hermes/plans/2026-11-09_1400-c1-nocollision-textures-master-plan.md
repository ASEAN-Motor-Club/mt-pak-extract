# C1 — master plan: NoCollision split, textures, materials

Date: 2026-11-09 14:00 (+07). Supersedes `2026-11-08_1800-c1-nocollision-split.md` (which stays on
disk as the record of how the decisions were reached) and **extends**
`2026-11-07_1730-c1-decal-collision-split-rev3.md` + its rev-4 amendment, which remain authoritative
for the decal geometry math, the slot-array reconstruction, `CTF_UseDefault` semantics and the
cook/level chain.

Nothing in this plan has been executed against the editor project unless a task says DONE.

---

## 1. Objective

1. **Nothing drivable-looking should be non-solid, and nothing non-drivable-looking should be
   solid.** Road paint, road markings, `road_signs` and foliage move into a
   `C1Full_NoCollision` sublevel whose components carry no collision; the cell meshes keep the
   collidable road. No visible geometry is lost, moved or re-shaded.
2. **Textures sample at the resolution they were authored at**, with a complete mip chain.
3. **Masked materials are one-sided unless the source says otherwise** (guardrail z-fighting).

Acceptance is in-game, from the shipped paks, with the game restarted — not from project state.

---

## 2. Verified facts (evidence, not assumption)

**Import / LOD**

- `import_local.py:49` used `replace_existing = True` → reimport rewrote LOD0 and kept stale LOD1+;
  the gate at `:126-149` never called `get_num_lods()`, so 555 meshes reported `IMPORT_GATE_OK`.
- Editor scans (3 passes): `/Game/Mods/C1Full/Meshes` 556 assets, `lods_gt1 = 0`; whole
  `/Game/Mods/C1Full` 5,380 assets / 1,217 static meshes, `lods_gt1 = 0`; loaded `C1Full` 11,191
  actors, 555 StaticMeshActors, 555 distinct meshes, no HLOD.
- Shipped pak `zzz_AMC_C1Full_P.pak` (658,027,598 B): 10,875 entries, **zero `Meshes_LOD`**; cooked
  map has zero `Meshes_LOD` strings; 555 mesh uexps, 1,891.9 MB, 9,141,527 tris at a uniform
  207 B/tri (no LOD outliers). **The LOD-leftover theory is dead** — the 510 `Meshes_LOD` assets in
  the editor project are unreferenced orphans that have never shipped.

**Split inputs**

- `meshes_local` is a **half-applied decal split**: `c-14_-31.obj` is headed `# C1 geometry (decal
  split)`; across 555 OBJs only 41 cells still contain `mat_joint*`, 17 contain `mat_mj*`
  (67,245 joint tris), and 307 cells carry no paint at all. The 187 stripped cells lost their
  joints to `C1_Decals.obj`, which was **never imported** (`C1_Decals.uasset` does not exist).
- Task 0 scan (`D:/C1FullMirror/nocollision_scan.json`, 445,080 B, 555 OBJs / 2.8 GB / 61 s):
  - `road_paint` 248 cells / 43,539 sections / 139 materials / **374,571 tris**
  - `road_signs` 28 cells / 2,192 sections / 2 materials / **15,080 tris** (45,240 verts)
  - `foliage` 237 cells / 149,537 sections / 21 materials / **444,068 tris** (1,332,204 verts)
  - `solid_keep` 14 cells / 24,324 sections / 6 materials / 43,709 tris
- Importer drops **0.105%** (9,606 / 9,141,527) of OBJ tris as degenerate over 212 cells → every
  split gate compares against **shipped per-cell counts**, never OBJ counts.
- `road_signs` was never in the marking predicate: `extract_source_markings.py:27` is
  `MARK = re.compile(r'mat_(kbs|mj)_')`, the inventory has 214 materials and zero `road_signs`.
  Its 28 cells are all southern (`-14_-31`, `-19_-33`, `-22_-30`, `-22_-27`, `-17_-24`, `-14_-23` …).

**Materials**

- The cook writes texture parameter values as NULL (`GOTCHAS.md:742-749`); measured again in
  `D:/C1FullMirror` — `MI_C1_guard_rail2`, `MI_C1_mat_tree_02` report `BaseColor = None` and parent
  the local `M_C1_Surface`. **The shipped pak is the authoritative instance source.**
- Shipped material generation: 1,653 MIs on vanilla masters (`M_PropMaster` 1,199,
  `M_AlphaTest` 429, `M_AlphaTestOneSided` 14, `M_GlassTrans` 4, …). Source declares only 13 masked
  materials as `doubleSided` → **~416 masked instances ship two-sided when the source says they are
  not**; `M_AlphaTest` itself is `TwoSided: True`.
- `P23` (`zzzzz_AMC_C1Mats_P23_P.pak`, 2,356,986 B, sha `3616e42486a13c53…`, 445 instances / 68
  baked textures) is built, verified and **installed**: 350 `M_AlphaTestOneSided`, 90 `M_AlphaTest`
  (15 genuinely two-sided + 75 paint/bake), 5 `M_GlassTrans`; 572 texture parameters, **0 null**.
- Namespace: `C1Full.umap` references `/Game/Mods/C1Full/Meshes` ×320, `/Game/Mods/C1/` ×0; a cell
  mesh references `/Game/Mods/C1Full/Materials/MI_C1_*` ×75. Shipped MIs import their maps from
  `/Game/Mods/C1/Textures/…` — **that tree is load-bearing**; `Mods/C1/Materials` and
  `Mods/C1/Meshes` are dead duplicates, as is `Mods/C1Full/Textures`.

**Textures**

- Dimensions are faithful: 1,196 shipped textures match their source DDS exactly, **0 ship smaller**.
  952 are derived channel maps (`_d_color`, `_n_normal`, `_r_data`, `_m_data`) with no DDS of their
  own. `other/sign_over7` = 256×64 DXT1, and `levels/c1/art/textures/sign_over7.dds` is 256×64.
- **Mip chains are truncated on 1,817 of 1,817 textures** that carry pixel data: 786 at 2 mips,
  502 at 3, **360 at 1**, 169 at 4 — against 7-10 expected. `sign_over7.dds` declares **9 mips**;
  the shipped `.ubulk` is 10,240 B = mip0 (8,192) + mip1 (2,048), so the chain ends at 128×32.
- Source supply is small by design: 2,409 DDS, widths 128 (645), 256 (680), 512 (507), 1024 (185),
  2048 (23), 4096 (5); the 130 `sign_*` textures are 32-128 px wide.

### 2a. The installed pak set changed on 2026-11-09 — checked, baselines hold

Installed now, in sort order:

- `zzz_AMC_Shuto_P.pak` — 657,989,391 B, 11-09 03:04. Replaces `zzz_AMC_C1Full_P.pak`, which no
  longer exists on disk.
- `zzzz_AMC_C1Full_Roads_P.pak` — 4,750,185 B, 11-09 03:43. Owns exactly two files:
  `Mods/C1Full/Maps/C1Full_Roads.umap` + `.uexp`.
- `zzzzz_AMC_C1Mats_P23_P.pak` — 2,356,986 B, 11-09 02:28, 445 material instances.

**Diffed the new pak against the old one (pulled and unpacked both):** 10,875 files each, **zero
added, zero removed, exactly 2 changed** —
`Mods/C1Full/Maps/C1Full_Roads.uexp` and `.umap`. Meshes, materials, textures, `C1Full.umap` and
`C1Full_Lights.umap` are **byte-identical** to what §2 measured. So §2's numbers stand, and A0's
re-derivation is a confirmation step rather than a re-baseline.

**The roads sublevel is now triple-owned**, which is the fragile part:

- `Shuto` ships `C1Full_Roads.umap/.uexp` (48,848 B / 57,027,257 B, md5 `7b909041…`)
- `Roads` ships the same paths again with different bytes (48,880 B / 57,027,114 B, md5 `e1c7d53e…`)
- sort order means `Roads` wins

Same pattern for materials: `Shuto` ships all 1,653 instances and `P23` re-ships 445 of them, so
`P23` wins by name. Neither overlap is broken *today* — both are accidents of alphabet that
`c1/tools/pakset.py check` will flag. Consequence for this plan: **A6 must not add a third claimant
of `C1Full_Roads.umap`**; either the roads sublevel is folded into the map pak and the `Roads` pak
is retired in the same window, or the map pak builds without it. That decision is recorded as
A6.0 below.

---

## 3. Settled decisions (do not re-litigate)

- `ikegaki_*` **solid** (garden walls); `mat_PA_siba_planter01` **solid** (prop).
- Foliage granularity **per cell**, one mesh per source cell, in `C1Full_NoCollision`; each mesh
  carries only that cell's foliage materials.
- `road_paint` + `road_signs` → **one merged world-space mesh** (rev-4), not per-cell.
- Collision is disabled **per component** (`CollisionProfileName = NoCollision`):
  `ECollisionTraceFlag` has no NoCollision member (`GOTCHAS.md:530`).
- One sublevel, `C1Full_NoCollision`, referenced from the persistent level, **owned by the map pak**
  (`build_levelpak.sh` ships one level asset per pak; a second silently drops the reference).
- Shipped build = authoritative material instance source; project trees are the nulled cook output.
- Road paint stays on the two-sided master; only structure moves to `M_AlphaTestOneSided`.
- Ghosted trunks are accepted: no trunk/bark material exists in the source.

---

## 4. Task graph

```
A0 re-pull current paks → per-cell baseline + slotmap.json
A1 regenerate OBJs (meshes_local_v2)            ─┐
A2 write + run splitter                          ├─ Track A: NoCollision
A3 dry-run import 3 cells                        │   (A0 gates everything; A1 gates A2)
A4 full import (cells + split meshes)            │
A5 sublevel + actors + collision presets         │
A6 cook → mesh/map pak (model read from A0)      │
A7 in-game acceptance                           ─┘
B1.0 plan → B1.1 3-texture round trip → B1.2 bulk → B1.3 base pak   ── Track B
C1.1 rebuild → C1.2 gates → C1.3 P24 + delete P23 → C1.4 in game   ── Track C, own window
```

Track B and C never touch `Meshes/` or `C1Full.umap`, so they can run between A6 and A7 if A6 is
otherwise waiting on a game restart.

---

## 5. Track A — NoCollision split

### A0 — Re-pull the current paks, then build the offline baselines

0. **Pull the installed set** (`zzz_AMC_Shuto_P.pak` 657,989,391 B, `zzzz_AMC_C1Full_Roads_P.pak`
   4,750,185 B, `zzzzz_AMC_C1Mats_P23_P.pak` 2,356,986 B) into `pakcur/`, verified by size + sha256
   against the guest. **Already done 2026-11-09**: the diff is 2 files (the roads sublevel) — see
   §2a — so the per-cell baseline is a confirmation of §2, not a new measurement.

Then both baselines come from `pakcur/`, so neither depends on project state:

1. **`c1/source/slotmap.json`** — 554 cells, built locally from `UAssetTool --dump` of the 555
   shipped meshes with `c1/scripts/make_slotmap.py`. **Done 2026-11-09**: 554 records, 15,113 slots,
   2 null slots (`WorldGridMaterial` in `c11_9` and `c3_17` — engine default, i.e. genuinely empty),
   0 unresolved instances out of the 1,653 shipped in `C1Full/Materials`.
2. **`c1/source/c1_cell_baseline.json`** — per cell: triangle count, slot count, non-null count,
   material names. **Done 2026-11-09**: 554 cells, 9,141,527 triangles total.

   Note the correction: `cells_full_manifest.json` **does** exist — at
   `/opt/data/cache/scratch/c1/cells_full_manifest.json`, not in the repo or on the guest. It is
   OBJ-side only (tris + material names, no slots), so the baseline joins it to the dump-derived
   slot counts rather than replacing it. No new `.uexp` parser was needed. Its keys are bare cell
   names (`7_17`); shipped assets carry the leading `c` (`c7_17`).
3. Also recovered from the same directory: `probe_lods_all.json` (11-07 05:47) — at that time
   **134 meshes carried 4 LODs** (LOD1 3,081,760 / LOD2 1,540,895 / LOD3 770,452 tris), LOD0
   9,131,921. The 11-09 scans show 0 meshes above 1 LOD, so that is already resolved; A4's
   `TARGET_LODS=1` keeps it that way.

Gate (passed): 554 records; every non-null slot resolves to a real MI path; slot counts equal the
dump; mesh count 555 and `Meshes_LOD` absent; tris 9,141,527 matching the canonical export.

### A1 — Regenerate the 555 cell OBJs from canonical source

Why: `meshes_local` is a half-applied decal split (fact 2 above); splitting it would bake the
inconsistency in, and the missing joint geometry exists in no shipped asset.

- Tool: `c1/scripts/rebase_obj.py`, now taking `--src/--dst/--origins`.
- **Source correction (2026-11-09):** the canonical un-split export is **`D:/C1FullMirror/meshes`**,
  not a re-export from `c1_src.zip`. Verified by probe: header `# C1 corridor cell ...` (no
  `(decal split)` tag), `mat_joint*` still present (56 sections in `c-14_-31`), `road_signs` present
  (1,337 `usemtl` lines). `meshes_local_predecal` matches it. So A1 is a pure rebase — no
  DAE→OBJ re-export, which removes the largest source of drift from this track.
- Output: **`D:/C1FullMirror/meshes_local_v2`** (new directory; `meshes_local` untouched as rollback).
- Where it runs: guest Python, driven by `run_rebase.ps1` pushed to `D:/C1FullMirror/Scripts/`.
  **Done 2026-11-09**: `REBASE_DONE files=555`.

Gate (fail the whole task on any mismatch):

- 555 OBJs; **no** file headed `(decal split)`
- per-cell triangle totals equal `c1/source/c1_cell_baseline.json` exactly, summed **9,141,527**
  (the baseline is the canonical export, so there is no tolerance band here)
- `mat_joint*` present in **187** cells; **92 distinct** joint/mj material names; `road_signs` in **28**
- per-cell bbox **extent** equals the source OBJ extent on X/Y/Z within 1 mm — extent, not absolute
  position, because the rebase subtracts each cell's origin

**Result 2026-11-09 — passed.** 555 OBJs and one non-cell helper (`uvquad`, 1 triangle, excluded);
`meshes_local_v2` matches `D:/C1FullMirror/meshes` exactly on triangle count and material set for
all 555 files (0 differences over 5.6 GB of geometry), so the rebase is a pure translation. Totals:
9,141,527 triangles (exact), joint/mj cells **187**, distinct joint+mj material names **92**,
`road_signs` cells **28**, decal-split headers **0**, tri mismatches **0**, bbox extent drift
**0**, cells absent from the baseline **0**.

The 187 and 92 are now pinned precisely, because the first gate draft got them wrong: 187 is the
**union** of cells carrying `mat_joint*` (158) or `mat_mj*` (29, disjoint), and 92 is
1 `mat_joint` name + 91 `mat_mj` names. `D:/C1FullMirror/v2_scan.json` holds the per-cell
tris/mats/bbox for both trees, so later gates re-check without re-reading 5.6 GB.

### A2 — Write `c1/scripts/split_nocollision.py` and run it on `meshes_local_v2`

Generalises the guest `split_decals.py`. Read `source/nocollision_materials.json` for classification.

```python
"""Split C1 cells into structural / no-collision geometry.

Reads meshes_local_v2 (canonical, pre-split OBJs), writes:
  nc_out/paint/C1_NoCollision_Paint.obj   merged, world metres, road_paint + road_signs
  nc_out/foliage/<cell>.obj               one per cell, pivot-relative like the cell meshes
  nc_out/cells_v2/<cell>.obj              structural remainder, refs compacted
Every face is classified by `usemtl`, never by face index. Anything unclassified raises.
"""
```

Rules, in order:

1. Parse each cell OBJ as `v` / `vt` / `vn` / `usemtl` / `f` blocks. A face's material is the most
   recent `usemtl`.
2. Classify: `road_paint` ∪ `road_signs` → `paint`; `foliage` → `foliage`; `solid_keep` and
   everything else → `structural`.
3. Apply the `joint_support` / `joint_depth` exclusion list (95 void faces, 55 cells): a joint face
   that spans a void must stay **structural** and collidable.
4. Paint faces: transform to world metres (origin subtracted, V mirrored, per `rebase_obj.py`'s
   convention) and append into one merged OBJ, one `usemtl` group per source material.
5. Foliage faces: keep the cell's pivot-relative frame; one OBJ per cell.
6. **Compact every emitted OBJ to referenced vertices** (rev-3 G2: orphan verts produced a 409 m
   false bbox on `c-1_-3` and `c1_-8`), remapping `vt`/`vn` too.
7. Emit `nc_out/split_report.json`: per cell `structural_tris`, `paint_tris`, `foliage_tris`,
   `bbox`, `materials removed`.

Gates:

- per cell `structural_tris + paint_tris + foliage_tris == v2_tris` (exact; the degenerate drop
  happens at import, not here)
- totals: paint **410,312**; foliage `444,068`; structural `8,287,149`; `solid_keep` `43,709`
- every cell's referenced-vertex bbox is covered exactly by the union of its three buckets
- no OBJ carries an empty vertex array or an unreferenced `usemtl` group

**Result 2026-11-09 — passed** (`nc_out/split_report.json`, `ok=true`): paint 410,312,
foliage 444,068, structural 8,287,149, solid_keep 43,709, excluded faces 95/95, per-cell
triangle mismatch 0, bbox drift 0. Outputs on the guest: `paint/C1_NoCollision_Paint.obj`
(129.8 MB, 219 material groups), `cells_v2/` 554 files (2,463 MB), `foliage/` 237 files (129 MB).

Three things the run taught, all now pinned:

1. **Paint is 410,312, not 389,651.** The plan's 389,651 was measured on `meshes_local` — the
   half-split tree — so it undercounts by **20,661 tris spread over exactly the 187 joint/mj
   cells**, i.e. the tris the earlier `split_decals.py` pass had already removed. `meshes_local_v2`
   is canonical and still has them. Foliage (444,068) and `solid_keep` (43,709) were unaffected and
   match exactly.
2. **The curated material list was truncated, the patterns were not.** The split emits 219
   material groups: 141 from the reviewed list plus 78 `mat_mj_*` names the list had missed
   (2,424 tris). Total distinct joint/mj names is 91 + `mat_joint_a` = 92, which reconciles with
   the A1 count. `c1/source/nocollision_materials.json` now carries all 217 `road_paint` names and
   a note saying the patterns are authoritative.
3. **`c0_-21` is foliage-only** (24 tris, no structural geometry), so there are 554 structural OBJs,
   not 555. The tool reports it under `foliage_only` instead of writing an empty OBJ.

The exclusion list is keyed on the face centroid in **centimetres relative to the cell pivot**
(`round(centroid_m * 100, 1)`); that frame was confirmed against `c-11_-27`, where both listed
`mat_mj_futou` faces match a face centroid to 0.07 cm. A face is excluded when the measured drop is
**≥30 cm or unmeasurable**: 95 faces = 89 null + 6 numeric ≥30.

### A3 — Dry-run import on three cells (no full pass)

Cells: `c-14_-31` (has `road_signs` + joints), `c-1_-3` (was rebuilt before; 108 slots, no nulls),
`c0_-6` (heaviest foliage). Uses the patched `import_local.py` (delete-before-import,
`TARGET_LODS = 1`) plus `apply_slotmap.py`.

Gates: `lods == 1` per mesh; `deleted_first` count = 3; the slot array matches the OBJ's `usemtl`
set with every slot bound to an instance; collision flag read back after save.

**Result 2026-11-09 — passed** (`D:/a3_report.json`, `ok=true`):

- structural — `c-14_-31` 41 slots, `c-1_-3` 84, `c0_-6` 56: all `lods=1`, all `deleted_first`,
  slot names equal the OBJ `usemtl` set, every slot bound, `CTF_USE_COMPLEX_AS_SIMPLE` read back
  after save. Shipped slot counts (44 / 102 / 70) are **higher on purpose**: paint and foliage
  materials are no longer slots on the structural mesh.
- paint — 219 slots, all bound, `lods=1`, **zero collision elements**, flag left at default.
- foliage — `c-1_-3` 6 slots, `c0_-6` 7 (heaviest foliage), zero collision elements; `c-14_-31` has
  no foliage.

Two API facts that broke the first attempt, both now encoded:

1. **`StaticMaterial.imported_material_slot_name` is read-only** in 5.5, so the old
   `apply_slotmap.py` plan of rebuilding the array from `slotmap.json` cannot work — and rebuilding
   the array wholesale would also remap every face onto a different material, because the array
   order is what the face sections index. The working approach is **bind by name**: the importer
   builds the array from the OBJ's `usemtl` order, then each slot's existing name is resolved to an
   instance.
2. **The OBJ importer adds one convex hull to every static mesh.** A mesh is only genuinely
   non-colliding when that hull is cleared *and* the trace flag stays default; leaving the hull in
   place would make the paint sheet a single giant convex collider. `clear_simple_collision()` sets
   every `agg_geom` element array to empty and the gate re-reads all five arrays.

Binding rule, since 182 material names appear in the canonical OBJ export but in no shipped slot
for that cell (1,264 cell-material pairs): use the shipped `slotmap.json` entry when the cell has
one, otherwise `MI_C1_<material name>` if that instance exists — which it does for all 182. Anything
left over is reported, never silently dropped.

### A4 — Full pass

1. `slotmap.json` comes from **A0** (built locally from the shipped pak dumps) — push it to the
   guest first; do not re-derive it from the project.

   Gate: 554 records; every non-null slot resolves to a real MI path.
2. `rebuild_cells.py` for every cell (delete → import → apply slotmap).
3. `import_nocollision.py` (new, same options) for the paint mesh and 237 foliage meshes:
   `CTF_UseDefault`, empty body, no LODs.

Gates: 555 + 238 assets; per-mesh tri counts equal the split report; `slotmap` check green for all
554; no asset carries LOD1+.

### A5 — Sublevel, actors, collision

- Create `/Game/Mods/C1Full/Maps/C1Full_NoCollision`.
- Reference it from `C1Full.umap` as a sublevel (persistent level is the sole owner of that ref).
- Spawn: 1 `StaticMeshActor` `C1_NC_Paint` + 237 `C1_NC_<cell>`, `Mobility = Static`,
  `CollisionProfileName = NoCollision`, rotation 0.
- Cell actors keep their existing preset; only their meshes changed.

Gates: read back location, rotation **and** collision profile in the same process (rev-3 §31);
`StaticMeshActor` count = 555 + 238; `PlayerStart` and both garages unchanged at Shibaura/Tatsumi.

### A6 — Cook and package

**A6.0 — settle the roads-sublevel ownership before building.** `C1Full_Roads.umap` currently has
two claimants (see §2a), and nav lives in it. Choose one, in this order of preference:

1. fold `C1Full_Roads` into the map pak and retire `zzzz_AMC_C1Full_Roads_P.pak` in the same
   closed-game window (one owner, no alphabet dependency), or
2. build the map pak without `C1Full_Roads` and leave the `Roads` pak as its sole owner.

Whichever is chosen, `pakset.py check` must report **no path with two owners** across the whole
installed set afterwards.

`cook_alllights.ps1` → `06_postcook_patch.sh` → `apply_map_edits_p22.sh`, then package **in
whatever model the current install uses** — read off `zzz_AMC_Shuto_P.pak` for the content split
(10,875 entries: `Mods/C1/Textures` 6,445, `C1Full/Materials` 3,306, `C1Full/Meshes` 1,110,
`C1Full/Maps` 6, 2 BPs, 4 `DataAsset` overrides), and bump the version from what is on disk, never
from this document.

Existing artifacts for reference: `Mesh_v2..v7` (latest `zzzzz_AMC_C1Mesh_v7_P.pak`, 11-08 16:44),
`Map_v2..v8` (latest `zzzzzz_AMC_C1Map_v8_P.pak`, 11-08 16:50). **The `Mesh_v5`/`Map_v6` names in
the 11-08 plan are stale** — do not hardcode a version.

Gates (all on shipped bytes, not project state):

- per-cell cooked tris drop by exactly that cell's split tris; per-cell bbox unchanged
- `SHIBAURA`×2 / `TATSUMI`×1 / old-spawn×0 in the shipped map
- the map pak is the sole claimant of `C1Full.umap` **and** `C1Full_NoCollision.umap`; the
  mesh-owning pak is the sole claimant of `Meshes/`; `c1/tools/pakset.py check` reports no asset
  with two owners and no two versions of one pak installed
- install mesh+map as a **pair** in one closed-game step

### A7 — In-game acceptance

Drive the southern band: `/tp` to `-19_-33`, `-14_-31`, one bridge joint, one tunnel mouth.
Pass/fail per item, recorded:

- paint, `road_signs` and foliage draw and sit at the same height as before
- driving over paint/signs/foliage meets no resistance; a kerb still stops the car (control)
- `road_signs` do not block a car that clips a sign quad
- no z-fighting on guardrails after `P23`
- nothing missing where a stripped cell used to be (the `C1_Decals` gap never shipped, so this
  pass is the first time that geometry is judged)

---

## 6. Track B — Texture mip chains (B1: reimport through the engine)

Problem: every texture ships 1-4 mips of 7-10; `sign_over7` ends at 128×32 although its DDS carries
9 levels. Effect: no smooth LOD transition, distant surfaces clamp to the smallest stored level, and
the visible mip is lower than the authored resolution.

**Mechanism (decided): reimport in the editor.** The engine builds the chain, so the `.uexp` can
never claim mips the payload does not have — which is precisely the defect being repaired. The
offline `.ubulk` rewrite is rejected: it writes UE's serialized mip array by hand.

### B1.0 — Inventory before writing (read-only)

- For each of the 2,314 texture assets: current `ImportedSize`, `compression_settings`,
  `srgb`, `lod_group`, `mip_gen_settings`, `never_stream`, current stored mip count (from `.ubulk`
  size), and the source DDS path + its own `dwMipMapCount`.
- Emit `c1/source/texture_import_plan.json`: one record per texture with the **exact** options to
  reimport with, derived from the source DDS format (DXT1 → `TC_DEFAULT`, DXT5 → `TC_DEFAULT`,
  BC5 → `TC_NORMALMAP`, BC7 → `TC_DEFAULT`, G8 → `TC_GRAYSCALE`), `srgb` preserved per asset,
  `mip_gen_settings = TMGS_FromTextureGroup`, `lod_group` preserved.

Gate: 2,314 records; every record names a real source DDS or is explicitly `derived` (the 952
channel-split maps inherit their parent's settings); no record has an empty option set — **no
silent defaults: every import option is written explicitly.**

### B1.1 — Three-texture round trip

`sign_over7` (256×64 DXT1, 9 source mips), `mat_road_02_file0` (512², the most-seen surface),
`mat_tree_02` colour map (masked foliage — the family the cut-out gate cares about).

Reimport to a scratch path, then verify: stored mip count == source mip count; per-mip dimensions
descend to 1×1; mip0 pixels unchanged vs the current asset (decode and compare); compression, sRGB
and LOD group unchanged; alpha of the masked one still present.

Gate: all six checks pass on all three. Any failure stops Track B and the plan is revised before
bulk work.

### B1.2 — Bulk reimport

Batch through the same script, `-run=pythonscript` on the guest, in chunks with a running log so a
crash is resumable; every asset's result written to `texture_reimport_log.json`
(`ok` / `already_full` / `error:<msg>`).

Gate: zero `error`; counts reconcile (`reimported + already_full == 2,314`).

### B1.3 — Rebuild and ship the base pak

`build_basepak.sh` → new base pak → `pakset.py check`. Install in its own closed-game window,
separate from Track A's mesh/map pair, so a texture regression can never be confused with a
collision regression.

Gates: pak contains the same asset paths as before (no additions, no removals); every texture's
stored mip count equals its source; total pak growth reported and accepted before install; spot-check
in game that `sign_over7` reads sharp at distance and that masked foliage cut-outs still clip.

---

## 7. Track C — Material close-out (P24 replaces P23 in one window)

`P23` sorts last (`zzzzz_…`) and therefore **masks any future materials pak**. The resolution is a
replacement, not a patch:

- **C1.1** Rebuild the full material set from the currently installed instances (authoritative
  source — never the project trees) with the `doubleSided` master selection already proven in
  `build_materials.py`.
- **C1.2** Gates before packaging: every texture parameter non-null (`ParameterValue (Object)` index
  ≠ 0, sampled per family plus a full count), parent distribution matches the source
  `doubleSided` split, instance count == source count, no instance left on `M_AlphaTest` whose source
  lacks `doubleSided`.
- **C1.3** Ship as `zzzzzz_AMC_C1Mats_P24_P.pak` and **delete `P23` in the same closed-game
  window**. Two paks must never claim the same instance path; `pakset.py check` is the gate.
- **C1.4** In game: guardrails one-sided (no z-fighting), fences with real sheets still visible from
  both sides, masked cut-outs unchanged.

Not in this pass: texture-resolver `colorMap` filename variant; pruning `Mods/C1/Materials`,
`Mods/C1/Meshes`, `Mods/C1Full/Textures` (superset rule from `unreal-mod-namespace-separation` — diff
identical/differing/only-in-old, rewrite refs by folder rename, delete in its own commit).

---

## 7a. Robustness rules (apply to every task)

1. **Baseline from the installed build, never from a project tree.** A cook nulls texture bindings
   and can lag a rebuild; §2a is the standing example of how fast the "truth" moves.
2. **No silent defaults.** Every import/build option is written explicitly in a config that is
   committed; a missing option is an error, not a default.
3. **Read state back in a fresh process.** Collision flags, LOD counts and slot arrays are verified
   by a second process that re-opens the asset, because an in-process write can appear to succeed.
4. **One change per install window.** Mesh+map together (they are one unit); textures alone; paks
   alone. A regression must be attributable to exactly one change.
5. **Exact numbers or no ship.** Every gate is a count, a byte size, a sha256 or a per-cell delta —
   never "looks right".
6. **Rollback artifacts exist before they are needed.** The previous `Mesh_v4`/`Map_v5`/`Mats_P22`
   paks and `meshes_local\` are verified present on disk *before* A4 deletes anything.

---

## 8. Risks

1. **Slot-array drift** (rev-3 G1), highest: gated by order (import → apply slotmap), nulls, and
   `ImportedMaterialSlotName`.
2. **Orphan verts / false bbox** (rev-3 G2): compaction plus per-cell bbox gate.
3. **Merged paint mesh precision**: one world-space mesh at the map edge accepts ~0.25 cm float
   error against a 1 cm decal lift (rev-4). Accepted as cosmetic.
4. **Draw calls**: +238 actors. Per-cell foliage keeps culling; monitor in the south.
5. **Pair install**: mesh + map must go in together; a mesh-only pass leaves actors pointing at
   assets that are not in the pak.
6. **P23 sort order** masking a later material build (Track C).
7. **Server pak** timing: out of scope, follow-up after client acceptance.
8. **Reimport cost**: A4 deletes and reimports 555 assets in freeman's project. `P22` paks on disk
   are the rollback; `meshes_local` and `meshes_local_v2` keep the geometry side recoverable.

## 9. Rollback

- Up to A5 everything is project-local: restore `meshes_local\`, `slotmap.json`, and the reimported
  assets from `D:\c1full_paks\` backups.
- From A6: reinstall `Mesh_v4` / `Map_v5` / `Mats_P22` in one closed-game window.
- Track B: keep the current `Mods/C1/Textures` tree as `textures_premips\` before the first write.

## 10. Decisions taken 2026-11-09 (most-correct path)

1. **Track B runs as B1 — reimport in the editor.** Chosen over the offline `.ubulk` rewrite because
   the engine building the chain is correct by construction: no hand-written serialization, no
   header patch, no risk of a `.uexp` that claims mips the payload does not have (which is exactly
   the defect being fixed). Slower, and it is the right side of that trade.
2. **Track C ends with a replacement, not a patch.** A full materials build ships as
   `zzzzzz_AMC_C1Mats_P24_P.pak` (sorts after `P23`), and `P23` is deleted in the **same**
   closed-game window. Never two material paks claiming the same 445 instances.
3. **`road_signs` stays in the paint mesh's blend path** (`translucent: true`,
   `translucentZWrite: true` is source truth) — it is not re-classified as opaque, and the merged
   paint mesh keeps its transparent material slot.
4. **Baselines are always taken from the currently installed pak set**, never from an older build
   (see §2a — the installed set changed under us on 2026-11-09).

Remaining open, non-blocking: pruning `Mods/C1/Materials`, `Mods/C1/Meshes`, `Mods/C1Full/Textures`
(superset rule, own commit); texture-resolver `colorMap` variant work.
