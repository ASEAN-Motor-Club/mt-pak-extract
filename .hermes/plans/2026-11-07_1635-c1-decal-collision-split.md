# C1 decal collision split — implementation plan

**Goal:** stop the road-joint/marking decal sheets from being solid: remove `mat_joint_*` and `mat_mj_*` geometry from the collidable cell meshes and render it from a separate NoCollision mesh, without losing any visible geometry.

**Architecture:** split at the source-OBJ level (the only level where a per-material cut is possible), re-import the structural cells unchanged in name, merge every decal face into one world-space mesh, and place that mesh with a single actor. Collision disappears because the decal mesh's BodySetup carries no collision and the structural cells simply no longer contain those triangles.

**Scope measured (2026-11-07, `obj_inventory.json`):** 187 of 555 cells, 92 distinct material names, **20,851 tris** total — `mat_joint_a` 14,001 (67%), `mat_mj_*` 6,850. That is 0.23% of the shipped 9,131,921 tris. Heights: `joint_a` +1.0 cm, `mj_*` +1.3…2.3 cm, paint +1.5 cm — i.e. the whole family lives inside a 1–2.6 cm band.

**Why a split is the only option:** `c1/scripts/import_local.py:26,86` sets `CTF_USE_COMPLEX_AS_SIMPLE` on every cell mesh. A cooked StaticMesh then collides as its entire triangle soup — there is no per-material or per-section collision flag in UE, and this port has no vertex-level collision authoring tool. Either the triangles leave the collidable asset or they keep colliding.

---

## Design decisions (with the alternatives that were rejected)

**Chosen: one merged world-space decal mesh + ONE actor at the origin.**
- 187 cells × 1 new actor = 187 instances of cooked-actor surgery, which the skill documents as the highest-risk operation in this pipeline (`SKILL.md` §"Adding an actor to a cooked level"). One actor cuts that exposure by 187×.
- The decal set is 20,851 tris / ~90 k verts — a single mesh is trivially small next to the 9.1 M-tri cell set.
- Placement maths already exists: `set_transforms.py` puts each cell actor at `(origin_x*100, -origin_y*100, 0)` with no rotation, and OBJs import at uniform scale 100. So a merged vertex, in metres, is `(x + origin_x, y - origin_y, z)` — verified against `cell_origins.json`.

**Rejected: per-cell `_decal` mesh.** Same visual result, 187 actor inserts, and 187 extra assets to keep owned by the mesh pak.

**Rejected: delete the decal faces.** Kills the expansion joints and the road markings the user is looking at; he asked for them to remain visible, just not solid.

**Rejected: approximate simple collision on the cells.** Replaces accurate building/road collision with convex hulls to work around 0.23% of the geometry — a much larger behaviour change than the bug.

**Note on the material bug:** `mat_joint_a` being parented to `M_GlassTrans` is a separate defect (a translucent master for a road joint). Fixing it is in this plan because the decal mesh is where those faces will live from now on — but it is a one-MI change, not a bulk reparent.

---

## Tasks

### Task 1 — Split the geometry (already written, not yet applied)
**Files:** `D:\C1FullMirror\Scripts\split_decals.py` (source copy: `c1/scripts/split_decals.py`)

**Behaviour:** rewrites `D:\C1FullMirror\meshes_local\<cell>.obj` without decal faces, and writes `D:\C1FullMirror\meshes_local_decals\C1_Decals.obj` in world metres. Keeps the vertex arrays intact (no index remap) so the structural OBJ cannot shift slot order or UVs.

**Step 1:** run `split_decals.py --check` → expect `SPLIT CHECK cells=555 touched=187 decal_tris=20851 merged=20851`.
    _Measured 2026-11-07: `ok: true`, `mismatch: []`, `touched=187`, `decal_tris=20851`, `merged=20851` — the regex and the independent inventory scan agree cell by cell._
    _The first version of the merge copied every vertex of every touched cell (21,055,098 verts, gigabytes of OBJ). Fixed to compact to the verts the decal faces actually reference; expect ~90 k, and `merged_verts` in the report is the number to sanity-check against `decal_tris` (roughly 3–5 verts per tri after welding)._
**Step 2:** confirm `mismatch == 0` and `missing_origin == []` in `D:\C1FullMirror\Scripts\split_decals.json`. A non-zero mismatch means the regex and the inventory disagree about what a decal is — stop and reconcile, do not write.
**Step 3:** back up the 187 originals to `D:\C1FullMirror\meshes_local_predecal\` (~size TBD), then run without `--check`.
**Step 4:** re-run `--check` on the written tree → expect `touched=0`, and `structural_tris` = 9,131,921 − 20,851 = **9,111,070**.

**Gate:** structural total equals the shipped total minus decal total, exactly. Any other number means faces were dropped or duplicated.

### Task 2 — Import the structural cells
**Files:** `c1/scripts/import_local.py` (unchanged)

**Step 1:** run it as before. The source signature changes, so it does a full 555-cell re-import; that is intended — a partial re-import is the failure mode the signature exists to prevent.
**Step 2:** expect `GATE meshes=555 missing=0 no_collision=0 -> IMPORT_GATE_OK`.
**Step 3:** verify `c0_-10` (308 joint tris removed) reads back with 308 fewer tris than the pre-split cook.

**Gate:** the import gate must print `IMPORT_GATE_OK`. Collision flag stays `COMPLEX_AS_SIMPLE` on the structural meshes — they still need to be solid.

### Task 3 — Import the decal mesh with no collision
**Files:** new `c1/scripts/import_decal.py`

Same `FbxImportUI` settings as `import_local.py` (`import_materials=False`, `import_uniform_scale=100`), destination `/Game/Mods/C1Full/Meshes`, name `C1_Decals`, but the collision step sets `CTF_USE_SIMPLE_AS_COMPLEX` and asserts **zero** convex elements, so the mesh has no collision at all rather than a fallback trimesh. Belt and braces: the placed component also gets `NoCollision`.

**Step 1:** import, then read back and assert `collision_trace_flag == CTF_USE_SIMPLE_AS_COMPLEX` and `body_setup.agg_geom` is empty.
**Step 2:** log `DECAL_GATE tris=20851 collision=none -> OK/FAIL` from the imported asset's triangle count.

**Gate:** imported tri count equals 20,851. A different count means the merge lost or duplicated faces across cell boundaries.

### Task 4 — Place the single decal actor
**Files:** new `c1/scripts/spawn_decal_actor.py`

Loads `C1Full`, spawns one StaticMeshActor from the `C1_Decals` asset at `(0, 0, 0)`, yaw 0 (no +180 rotation: this actor is at the world origin, not a newly placed point actor), sets `Mobility=Static`, `CollisionProfileName=NoCollision`, label `C1_Decals`, saves the level.

**Step 1:** run, expect `DECAL_ACTOR spawned=1 collision=NoCollision`.
**Step 2:** re-run `spawn_inventory.py` → `counts.StaticMeshActor` goes 554 → **555**, PlayerStart/garage unchanged at Shibaura.

**Gate:** exactly one new actor, and the two spawn anchors are untouched. Rollback for this task alone: delete the actor in the editor, no pak is involved yet.

### Task 5 — Cook
**Step 1:** `D:\cook_alllights.ps1`; expect `Done!` and the six level outputs printed.
**Step 2:** the 187 changed cell meshes must appear under `Saved\Cooked\...\Meshes\` with smaller sizes; `C1_Decals.uasset` must exist.
**Step 3:** record the six level hashes. `C1Full.umap`/`uexp` **will** change (one extra actor) — that is expected this time, unlike the previous recook.

### Task 6 — Level chain, mandatory order
**Step 1:** `06_postcook_patch.sh` → `SETCLASSREF_OK` ×3 + `REPAIR_OK` (run with cwd `csharp/UAssetTool` and `TOOL` at a wrapper that execs `/opt/data/dotnet10/dotnet`).
**Step 2:** `apply_map_edits_p22.sh` → `MAP_EDITS_OK`, and its log must still show `CLONE_OK BP_C1_Prop_C_1 … at (593234,-466784,87449)`.
**Step 3:** verify the shipped bytes: `SHIBAURA` ×2, `TATSUMI` ×1, old spawn ×0 (packed `<3d` triples in the uexp), plus the three class refs in the umap.

**Gate:** all three anchors survive. P22 runs after the cook, so a missing garage here means the clone step regressed, not the level.

### Task 7 — Fix `mat_joint_a`'s parent
**Files:** MI lives in the Mats pak (`zzzzz_AMC_C1Mats_P21_P`)
**Step 1:** `--set-mi-parent` on `MI_C1_mat_joint_a`: `M_GlassTrans` → `M_PropMaster`, and clear the opacity/opacity-mask params that the glass master was supplying.
**Step 2:** dump the MI back and confirm parent + param names match `M_PropMaster`'s documented set (`BaseColor`, `Normal`, `Roughness`, `Metallic`).
**Step 3:** rebuild as `zzzzz_AMC_C1Mats_P22_P`, manifest, `pakset.py check`.

**Gate:** no other MI changes in this pak — diff the asset list against P21 and confirm the count is identical (3,306 files).

### Task 8 — Package and install
**Step 1:** `build_meshpak.sh` → `zzzzzz_AMC_C1Mesh_v4_P` (549 cells smaller by the decal tris + 1 new `C1_Decals` asset + `C1_Decals.uexp`). Manifest swap, `pakset.py check`.
**Step 2:** `build_levelpak.sh <dir> <ABSOLUTE out.pak> C1Full` → `zzzzzz_AMC_C1Map_v5_P`.
**Step 3:** install with the game closed: copy mesh v4 + map v5, remove v3/v4 predecessors in the same step, then `repak list` every pak and confirm the map pak is still the only claimant of `C1Full.umap` and the mesh pak the only claimant of `Meshes/`.
**Step 4:** verify installed sizes/hashes against the manifests, not the build log.

**Gate:** `pakset.py check` = "every asset has exactly one owner", and the 8-pak set has no two versions of anything.

### Task 9 — In-game verification
- Drive over a Shibaura expansion joint and a marked lane at speed: the vehicle should no longer step/jolt.
- Confirm the joints and markings are still **visible** (this is the regression risk of the whole job).
- `/tp` to a `mat_mj_*`-heavy cell (`c2_11`, 1,035 decal tris) and check for z-fighting or a doubled surface.

---

## Files likely to change

- `c1/scripts/split_decals.py` (new, written)
- `c1/scripts/import_decal.py` (new)
- `c1/scripts/spawn_decal_actor.py` (new)
- `D:\C1FullMirror\meshes_local\*.obj` (187 rewritten + 368 untouched)
- `D:\C1FullMirror\meshes_local_decals\C1_Decals.obj` (new)
- `c1/GOTCHAS.md` (new section: per-material collision split)
- `c1/out/pakset/*.json` (v4/v5/P22 manifests)

## Risks

1. **Editor spawn crash.** Spawning actors in bulk previously crashed the editor inside the road subsystem; that was a full-level teardown. One actor spawn is a different code path but is still unverified here — Task 4 fails fast and is individually revertible.
2. **Doubled or shifted surfaces.** The decal mesh is at the world origin; if `cell_origins` sign convention is wrong, decals land mirrored across the map and are obvious in one look. Task 3's tri count and Task 9's visual check catch it.
3. **Triangle accounting drift.** Task 1's exact-total gate is the guard: 9,111,070 structural + 20,851 decal must sum to the shipped 9,131,921.
4. **Mesh pak growth/ownership.** `C1_Decals` must be owned only by the mesh pak; the pakset gate enforces it, but the new asset needs its manifest regenerated, not hand-edited.
5. **Scope creep into the material pass.** Task 7 is one MI. If it turns into "these all look wrong", it becomes its own job with its own evidence (`keep_authored.txt` is the authoritative list).

## Open questions

1. **One merged decal actor, or per-cell?** Merged is planned (1 actor vs 187). Per-cell gives independent transforms at 187× the risk.
2. **`mat_joint_a` target parent** — `M_PropMaster` (opaque, same family as the other authored MIs) is the plan. Say if you want something else, or two-sided.
3. **Decals on the *server* pak** — the dedicated-server pak ships the same meshes; splitting there too means a server pak rebuild. Planned, but after the client is verified.

## Rollback

Everything up to Task 5 is reversible on disk: `meshes_local_predecal\` holds the 187 originals, and the level change is one actor. From Task 8 on, the previous paks (`Mesh_v3`, `Map_v4`, `Mats_P21`) are still in `D:\c1full_paks\` and can be reinstalled in the same closed-game window.
