# C1 NoCollision split — plan (extends the decal-split rev3 + rev4)

Date: 2026-11-08. Supersedes nothing; **extends** `2026-11-07_1730-c1-decal-collision-split-rev3.md`
and its rev-4 amendment, which stay authoritative for the decal geometry math, the slot-array
reconstruction, the `CTF_UseDefault` semantics and the cook/level chain. This plan adds two
material families that rev3 never covered and folds in three defects found on 2026-11-08.

**Goal:** every surface that should not be drivable — road paint, road markings, `road_signs`,
foliage — renders from meshes that carry **no collision**, while the cell meshes keep collidable
road. No visible geometry is lost or moved.

---

## Verified findings (2026-11-08)

1. **`import_local.py` leaves stale LODs.** `:49` sets `replace_existing = True` and imports into
   the existing asset; on a mesh that already has LOD1+, that rewrites LOD0 and keeps the old
   levels (`rebuild_cells.py:7-11`). `rebuild_cells.py` exists precisely to avoid this (delete the
   asset first, `:38-43`) but has only ever run for the cells in `D:\slotmap.json`, which holds
   **3 entries**: `c-1_-3`, `c1_-8`, `c-2_-15`.
2. **The import gate cannot see the bug.** `import_local.py:126-149` checks existence and
   `CTF_UseComplexAsSimple` only — no `get_num_lods()` — so 555 meshes with stale LODs still
   reported `IMPORT_GATE_OK`.
3. **The marking split was never implemented.** `extract_source_markings.py` is an inventory
   (`:88-108` writes `c1_source_markings.json` and prints a summary). No `cells_marks` asset, no
   `Meshes_Marks` folder, no sublevel, and no repo script references one.
4. **The marking predicate provably excludes `road_signs`.** `MARK = re.compile(r'mat_(kbs|mj)_')`
   (`:27`) for cells and `mat_((?:kbs|mj)_[A-Za-z0-9_]+)-material` (`:48`) for the `.dae` side.
   The inventory's 214 distinct materials contain **no** `road_signs`.
5. **Scale of the marking gap:** `road_signs` appears in **28 cells**, all in the southern band
   (`-14_-31`, `-19_-33`, `-22_-30`, `-22_-27`, `-17_-24`, `-14_-23`, …), one of them as
   `road_signsy1`. Those same cells carry no `mat_kbs_*` / `mat_mj_*` slots at all.
6. **Foliage inventory:** 29 slots across **239 of 554 cells**. Largest: `mat_tree_02` 183,
   `mat_tree04_sh` 160, `mat_tree_01` 55, `mat_tree_03_sh` 50, `mat_tree_04` 49, `mat_tree_03` 47,
   `mat_bush_04c` 47, `bush_04a/04b` 43, `bush_05a/b/c` ~32, `bush_06` 25, `bush_03a/b` 12,
   `grass_seitaka` 6, `tree_06*` 2-6, `tree_2a/2b` 5, `ikegaki_*` 10+1, `planter01` 1,
   `hanaharu_a/b_00_sh` 1.
7. **No trunk/bark material exists** in `merged.materials.json` (no `mat_tree_trunk`, no `miki`).
   A tree is one material for canopy and trunk, so ghosting a tree material ghosts trunks too.
8. **`M_AlphaTest` is `TwoSided: True`** (`masters/M_AlphaTest.uasset`, dump line 110) and
   `build_materials.py` reparents *every* masked instance onto it, so all masked materials render
   two-sided regardless of the source `doubleSided` flag — the guardrail z-fighting.
   `guard_rail2` has `alphaTest: true, alphaRef: 139` and **no** `doubleSided` key.
9. **Texture mip chains are truncated**: `mat_pa_siba_komono01_file0` (256×256 DXT5) ships
   2 mips of ~8; `mat_br_kameibashi_top01_file0_d_color` (512×512) ships mips 0-2 of 9.
10. **Guest state**: `meshes_local` = 555 rebased OBJs (canonical, whole map);
    `meshes_local_predecal` = 187 (backup); `meshes_local_decals` = 3 OBJs (`C1_Decals.obj` 19.9 MB,
    `C1_Decals_badYmirror.obj`, `C1_Decals_grouped.obj`); **`C1_Decals.uasset` does not exist** in
    the project — the decal split was emitted but never imported. The working scripts live in
    `D:\C1FullMirror\Scripts` (`split_decals.py`, `spawn_decals.py`, `joint_support.py`,
    `joint_depth.py`, `verify_split_bbox*.py`), not in the repo.
11. **`meshes_local` is a half-applied decal split.** `c-14_-31.obj` is headed
    `# C1 geometry (decal split)` and carries no `mat_joint*`/`mat_mj*`; across the 555 OBJs only
    **41 cells still contain `mat_joint*`** and **17 contain `mat_mj*`** (67,245 joint tris in
    total), while 307 cells carry no paint at all. The 187 stripped cells lost their joints to
    `C1_Decals.obj`, which was never imported — so that geometry exists in no shipped asset.
    Consequence: **do not layer a second split onto these OBJs.** Regenerate them from the
    canonical source first.

---

## Decisions (settled 2026-11-08)

- **`ikegaki_*` (hedges, 11 cells): solid.** They read as garden walls; ghosting them would let
  cars pass through a visual barrier.
- **`mat_PA_siba_planter01`: solid.** It is a prop, not foliage.
- **Foliage granularity: per cell.** One mesh per source cell, placed in `C1Full_NoCollision`.
  Preserves frustum/HLOD culling; a single 26 km foliage mesh would never be culled. Each foliage
  mesh carries only the foliage materials its own cell uses (per-cell slot tables, not a shared
  table).

### Material generation — settled, do not re-litigate

- **The shipped pak is the authoritative instance source; the project trees are not.**
  `GOTCHAS.md:742-749`: a cook writes texture parameter values as **NULL** (`Index=0`) and the
  surface renders flat white; measured again 2026-11-08 in `D:/C1FullMirror` — `MI_C1_guard_rail2`
  and `MI_C1_mat_tree_02` both report `BaseColor = None`, while the shipped pak's copies carry a
  real `Texture2D`. So `M_C1_Surface` / `M_C1_Surface_Masked` parenting in the project is
  authoring state that the retargeting pass replaces with vanilla masters; it is never what ships.
- **Namespace is correct and verifiable by the cooked map.** `C1Full.umap` references
  `/Game/Mods/C1Full/Meshes` ×320 and `/Game/Mods/C1/` ×0; a shipped cell mesh references
  `/Game/Mods/C1Full/Materials/MI_C1_*` ×75 and `Mods/C1/Materials` ×0. The repoint recorded in
  `GOTCHAS.md:735-741` is done.
- **But `Mods/C1/Textures` is load-bearing, not legacy.** The shipped instances import their maps
  from `/Game/Mods/C1/Textures/<family>/...`, which is why the pak carries 6,445 entries under
  `Mods/C1` (textures only) and zero materials/meshes there. Any texture override must be written
  under `Mods/C1/Textures`, which is what the builder does.
- **`Mods/C1Full/Textures` (2,390 assets, newer than the C1 copy) is a dead duplicate** — not
  shipped, not imported by anything. Pruning it is safe only under the superset rule in
  `unreal-mod-namespace-separation` (diff identical / differing / only-in-old, then rewrite
  references via folder rename, never by byte patching).
- **Gate for any material build:** `UAssetTool --dump <mi> | grep 'ParameterValue (Object)'` must
  show a non-zero index for every texture parameter, sampled per family. `P23` passes: 445
  instances, 572 texture parameters, 0 null.

---

## Design

**One classification config, two output shapes.** `c1/source/nocollision_materials.json`:

```
groups: {
  road_paint:  [mat_joint_a, mat_joint_*, mat_mj_*, mat_line*, mat_kbs_*]      -> merged mesh
  road_signs:  [road_signs, road_signsy1]                                      -> merged mesh
  foliage:     [mat_tree*, mat_bush_*, mat_grass_*, mat_hanaharu_*]            -> per-cell meshes
}
solid_keep:    [mat_ikegaki_*, mat_PA_siba_planter01]   # settled: hedges read as walls, planter is a prop
```

Each entry carries `reason` and a `source` (`translucent+groundType:VOID`, `alphaTest`, explicit),
so the list stops being regex archaeology and can be audited.

- **road_paint + road_signs → one merged world-space mesh** (`C1_NoCollision_Paint`), per rev-4:
  ~21 k decal tris + the paint/sign triangles is small enough that one un-culled mesh costs less
  than 215 actors, and float32 precision at the map edge (+0.25 cm vs a 1 cm lift) is accepted as
  cosmetic.
- **foliage → per-cell meshes in the same sublevel** (settled — see Decisions). Each mesh carries
  only the foliage materials its own cell uses. Chunking is not a fallback here: per-cell is the
  decided granularity, because a single 26 km foliage mesh would never be culled.
- **One sublevel** `C1Full_NoCollision`, referenced from the persistent level, owned by the **map
  pak** (`build_levelpak.sh` ships exactly one level asset per pak; a second silently drops the
  reference).
- **Collision is disabled per component** (`CollisionProfileName = NoCollision`), because
  `ECollisionTraceFlag` has no NoCollision member (`GOTCHAS.md:530`). Meshes additionally get
  `CTF_UseDefault` + empty body per rev-3 G3.

---

## Tasks

### Task 0 — Measure before moving anything (offline, read-only) — **DONE 2026-11-08**

Results (555 OBJs, 2.8 GB, `scan_nocollision.py`, 61 s):

- `road_paint` — 248 cells, 43,539 sections, 139 materials, **374,571 tris**, 1,123,713 referenced verts
- `road_signs` — 28 cells, 2,192 sections, 2 materials (`road_signs`, `road_signsy1`), **15,080 tris**
- `foliage` — 237 cells, 149,537 sections, 21 materials, **444,068 tris**, 1,332,204 verts
- `solid_keep` — 14 cells, 24,324 sections, 6 materials, 43,709 tris
- heaviest foliage cells: `c0_-6` 27,868 tris, `c4_4` 19,799, `c5_5` 18,571, `c7_-10` 16,108
- heaviest `road_signs` cells: `c-18_-33` 1,832 tris, `c-14_-32` 1,574, `c-14_-31` 1,337

LOD survey (three passes, editor commandlet):

- `/Game/Mods/C1Full/Meshes` — 556 assets, **`lods_gt1 = 0`**
- whole `/Game/Mods/C1Full` — 5,380 assets, 1,217 static meshes, **`lods_gt1 = 0`**
- loaded `C1Full`: 11,191 actors — 555 StaticMeshActors, 555 distinct meshes, all under
  `/Meshes/`, **no HLOD actors**, 9,235 spot + 1,239 point lights, 156 `MotorTownRoad`

**Consequence — the stale LODs are NOT in the project.** They must be inside the shipped pak.
Follow-up: pull `zzz_AMC_C1Full_P.pak` (658 MB, built 2026-11-08 19:33 local) and check whether
its cell meshes carry LOD1+ while the project's do not.

Second baseline: summed mesh LOD0 tris = **9,131,921** vs OBJ total **9,141,527** — 9,606 tris
(0.105%) fewer, spread over 212 cells; the OBJ importer drops degenerate faces. Split gates must
use the *shipped* tri count per cell, never the OBJ count.
Delivered as `scan_nocollision.py` (OBJ side, guest Python 3.10, writes
`D:/C1FullMirror/nocollision_scan.json`) and `lod_scan{,2,3}.py` (editor commandlet side,
`-run=pythonscript`).

**Gate status:** tri/vertex volume printed and accepted. The stale-LOD list came back **empty**,
which contradicts the reported symptom and is therefore recorded as an open finding rather than
a satisfied gate.

### Task 1 — Fix the two import defects — **DONE (code), not yet run**

`c1/scripts/import_local.py`:
- `DELETE_BEFORE_IMPORT = True` + `drop_existing()` — deletes the asset (raises on a failed
  delete instead of importing over it) so the importer builds a fresh single-LOD chain;
- `TARGET_LODS = 1`, `num_lods()` helper, and the gate now fails on `lods != 1`, logging a
  `bad_lods` sample;
- the summary line records `deleted_first=`;
- docstring states the ordering rule: `apply_slotmap.py` must follow any delete-import pass,
  because the delete takes the slot array with it.

`c1/scripts/apply_slotmap.py` (new) — rebuilds each cell's `static_materials` array from
`slotmap.json` in the editor, including EMPTY slots, then re-reads the asset and fails unless
slot count, every slot name and every MI path match the dump, plus `want_nonnull`.
`c1/scripts/rebuild_cells.py` stays the only path that touches cell assets outside a full pass.

**Gate:** a fresh full pass reports `lods=1` for every cell; `IMPORT_GATE_OK` fails if any mesh
carries more than one LOD. Dry-run on 3 cells first (not yet executed — running it means deleting
and reimporting assets in freeman's project, so it needs an explicit go).

### Task 2 — Regenerate `slotmap.json` for every cell — **parser DONE, batch pending**

`c1/scripts/make_slotmap.py` rewritten: it now walks the `StaticMaterials (Array[N])` block
positionally and emits one record per slot — `slot`, `imported`, `mi` or `null` — plus
`want_slots` and `want_nonnull` per cell. Validated against a real shipped asset:
`c-1_-3` → 108 slots, 108 non-null, `mat_botom_u` → `MI_C1_mat_botom_u_10` (longest-prefix
resolution confirmed). No null slots in that cell, so the null path is unproven until a cell with
gaps is dumped.

**Gate:** 554 cells; every non-null slot resolves to a real MI; `want_slots`/`want_nonnull`
recorded per cell. This file is the only surviving copy once assets are deleted.

### Task 3 — Write the classification config
`source/nocollision_materials.json` as above, with `road_signs`/`road_signsy1` in `road_paint`,
`ikegaki_*` + `planter01` in `solid_keep`, and a `reason` per entry.

**Gate:** every slot listed exists in `cells_full_manifest.json`; no slot appears in two groups;
counts reproduce 29 foliage slots / 239 cells and 28 `road_signs` cells.

### Task 4a — Regenerate the cell OBJs from canonical source (new, required)

`rebase_obj.py` over the canonical `c1_src.zip` export, into a **fresh** directory
(`meshes_local_v2`), so the split runs on a known state instead of on the half-applied
output in `meshes_local` (finding 11). Regenerating everything is the only way to get
consistent input: the 187 already-stripped cells are missing geometry that no shipped
asset contains.

**Gate:** 555 OBJs; per-cell tri totals equal the manifest totals exactly (9,141,527);
`mat_joint*` present in 187 cells; `mat_mj*` in 92; `road_signs` in 28; no OBJ headed
`(decal split)`. Keep `meshes_local` untouched as the rollback copy.

### Task 4 — Split the geometry
New `c1/scripts/split_nocollision.py`, generalising the guest `split_decals.py`:
- per cell, partition faces by `umtl` membership in the config;
- emit one world-metre merged OBJ for `road_paint` + `road_signs`;
- emit one OBJ per cell for `foliage` (pivot-relative, same convention as cells);
- **compact every rewritten cell OBJ to referenced vertices** (rev-3 G2 — orphan verts produced a
  409 m false bbox on `c-1_-3` and `c1_-8`);
- carry the `joint_support` / `joint_depth` face-exclusion list (95 void faces, 55 cells) so a
  joint spanning a void stays collidable.

**Gates:** per-cell `structural_tris + split_tris == shipped_tris`; merged decal total exactly the
rev-3 figure (20,851) plus the newly-added paint/sign triangles; foliage total matches Task 0;
every rewritten cell's referenced-vertex bbox unchanged on X/Y/Z.

### Task 5 — Import the split meshes
Cell meshes through `rebuild_cells.py` (delete-then-import, single LOD, slot array restored from
`slotmap.json` **including nulls**); paint mesh and foliage meshes through a `import_nocollision.py`
sharing the same options, `CTF_UseDefault` + empty body.

**Gates:** `lods == 1` per mesh; `got_slots == want_slots` and `got_nonnull == want_nonnull`;
per-mesh tri counts equal source; collision flag read back in a **fresh process** (rev-3 §17).

### Task 6 — Sublevel and actors
Create `C1Full_NoCollision`, add it to the persistent level's sublevel list, spawn one actor per
split mesh: `Mobility=Static`, `CollisionProfileName=NoCollision`, world rotation 0, labels
`C1_NC_Paint`, `C1_NC_<cell>`.

**Gates:** read back location, rotation **and** collision profile in the same process (rev-3 §31);
`StaticMeshActor` count `= 555 + N`; PlayerStart and both garages unchanged at Shibaura/Tatsumi.

### Task 7 — Cook, level chain, package
`cook_alllights.ps1` → `06_postcook_patch.sh` → `apply_map_edits_p22.sh` → `build_meshpak.sh`
(Mesh_v5) + `build_levelpak.sh … C1Full` (Map_v6) → `pakset.py check`. Ship mesh+map as a **pair**
in one closed-game step.

**Gates:** per-cell cooked tris drop by exactly that cell's split tris; bbox per cell unchanged;
`SHIBAURA`×2 / `TATSUMI`×1 / old-spawn ×0 in the shipped bytes; map pak sole claimant of
`C1Full.umap` and the new sublevel; mesh pak sole claimant of `Meshes/`.

### Task 8 — Materials, same window — **master selection DONE and verified 2026-11-08**

- `build_materials.py`: masked master now chosen from the source `doubleSided` flag —
  `M_AlphaTestOneSided` by default, `M_AlphaTest` (two-sided) only when the source says so.
  `MASKED_MASTERS` table + `finish(..., master_pkg, master_name)`; the post-condition verifies
  against the master it actually used; the game-pak preflight checks both packages exist.
- Verified both branches end-to-end: `guard_rail2` (no `doubleSided`) → output parent
  `M_AlphaTestOneSided`; `mat_br_sintomi_fence01` (`doubleSided: true`, masked) → output parent
  `M_AlphaTest`.
- **Shipped-pak evidence:** the installed `zzz_AMC_C1Full_P.pak` has **429** MIs parented to
  `M_AlphaTest` (two-sided) and **14** mentioning `M_AlphaTestOneSided`. The source declares only
  **13** masked materials as `doubleSided` — so roughly **416 masked instances in the shipped build
  are two-sided when the source says they are not**. That is the guardrail z-fighting, and it means
  the shipped material set predates the current pipeline.
- `compile_materials.py:426` already computes `two_sided`; the builder now derives it directly from
  the source entry, which is the same value.
- Texture resolver: honour the exact `colorMap` filename from `merged.materials.json` (the
  `(CUnet)(noise)(Level3).color` variant), and stop truncating mip chains. **Still open.**

**Gates:** no instance parented to `M_AlphaTest` whose source lacks `doubleSided` (mechanism now in
place, full run pending); every shipped texture carries a full mip chain to 1×1 (or the documented
minimum); spot-check `guard_rail2` renders one-sided and `mat_pa_siba_komono01` samples its source
texture.

**Two defects found only by running it (both fixed, both silent):**

- **`MI_C1X_` prefix.** `source_key()` stripped only `MI_C1_`, so the whole `MI_C1X_*` variant set
  resolved to `unknown` and was skipped by every group — 49 instances, foliage and fences among
  them, left on whatever master they shipped with.
- **Shared staging dir.** `--set-mi-parent` copies *every* instance in its input directory, not just
  the ones on its list. Both masked subsets staged into one directory, so the two-sided pass emitted
  a full copy of the set and the merge put 350 correctly one-sided instances back on `M_AlphaTest`
  while every gate reported OK. Each subset now stages separately, and the pass asserts its output
  set equals its own subset exactly.

### Task 9 — In-game acceptance
Drive the southern band: paint/signs/foliage draw, nothing is missing, no z-fighting on guardrails,
driving through foliage is smooth while a kerb still stops the car (control), joints no longer step.
`/tp` to `-19_-33`, `-14_-31`, plus one bridge joint and one tunnel mouth.

**Gate:** explicit pass/fail per item, from the shipped paks, game restarted.

---

## Risks

1. **Slot-array drift** (rev-3 G1) — highest; gated on order + nulls + `ImportedMaterialSlotName`.
2. **Orphan verts / false bbox** (rev-3 G2) — compaction plus per-cell bbox gate.
3. **Foliage asset count** — 239 extra actors/draw calls is fixed by the per-cell decision; the
   remaining risk is mesh-level cost, measured in Task 0. If a single cell's foliage mesh is
   oversized, the fix is splitting that mesh in two, not changing granularity.
4. **Ghosted trunks** — accepted explicitly: no trunk material exists, so trees become pass-through.
5. **Draw calls** — 239 extra actors is a real cost; monitor with the map open in the south.
6. **Pair install** — mesh + map must go in together; a mesh-only update leaves actors pointing at
   missing assets.
7. **Server pak** — follow-up after client acceptance, not in this pass.

## Rollback

Up to Task 6 everything reverts on disk (`meshes_local_predecal\`, `slotmap.json`, OBJ backups).
From Task 7, reinstall `Mesh_v4` / `Map_v5` / `Mats_P22` from `D:\c1full_paks\` in the same
closed-game window.

## Open questions

1. Paint merged mesh vs per-cell — rev-4 says merged; unchanged here. (Foliage is settled: per cell.)
2. Server pak timing — after client acceptance, out of scope for this pass.
3. `road_signs` material is `translucent: true, translucentZWrite: true` in source — confirm it stays
   in the paint mesh's blend path rather than being treated as opaque.
