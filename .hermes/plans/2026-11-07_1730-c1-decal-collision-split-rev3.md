# C1 decal collision split — implementation plan (rev 3, after reading `c1/GOTCHAS.md`)

Supersedes rev 1 (`…_1635-…md`) and rev 2 (`…_1700-…-rev2.md`).

**Goal:** stop the road-joint/marking decal sheets being solid: take `mat_joint_*` / `mat_mj_*` faces out of the collidable cell meshes and render them from separate NoCollision meshes, losing no visible geometry.

**Scope:** 187 of 555 cells, 92 material names, **20,851 tris** (`mat_joint_a` 14,001; `mat_mj_*` 6,850). Source total 9,141,505 tris; cooked 9,131,921.

**Why a split:** `import_local.py:26,86` sets `CTF_USE_COMPLEX_AS_SIMPLE`, so a cell collides as its whole triangle soup. No per-material collision switch exists in UE.

---

## What the gotchas changed from rev 2

**G1 — §36.3: empty slots are intentional and dropping one shifts every later slot.**
Rev 2 said "a decal-only slot may legitimately disappear". That is the documented failure: seven shipped cells already carry *intentional* empty slots (counts 1, 2, 1, 2, 2, 1, 5), and a restore that skips null interfaces makes the mesh render **wrong materials on its faces** while the non-null count still matches. Rev 3 rebuilds each cell's `StaticMaterials` array from the **shipped pak's own array** — order, nulls and `ImportedMaterialSlotName` — and gates on `got_slots == want_slots` **and** `got_nonnull == want_nonnull`. A slot that `mat_joint_a` used to occupy stays in the array as an *empty* slot; it does not vanish.

**G2 — §36.1/§36.2: triangle count proves nothing about scale, and orphan verts poison the bbox.**
Rev 2 gated geometry on tri counts alone. Add the documented gate: mesh `2 * bounds.box_extent` vs the OBJ bbox ×100, all three axes, computed over **referenced** vertices only. That has a direct consequence for the splitter: leaving the decal faces' vertices behind as orphans is precisely how `c-1_-3` and `c1_-8` produced a 409 m false bbox. **The splitter must compact each rewritten cell OBJ to referenced vertices** (remap indices, faces and UVs unchanged) instead of keeping the full vertex array as rev 2 planned.

**G3 — §17 correction: "no collision" comes from an empty body at `CTF_UseDefault`, and the cook can still emit ConvexElems.**
Rev 2 planned `CTF_USE_SIMPLE_AS_COMPLEX` + "assert zero convex". The gotcha records that `CTF_UseDefault` with an empty body setup is the state where you *see geometry and fall straight through*, that the cook still emits `ConvexElems`, and that "0 convex hulls" is not a state you can rely on. Rev 3: decal meshes get `CTF_UseDefault`, empty body, and the **component `NoCollision` profile is the guarantee**; per-mesh flag readback happens in a fresh process (§17's own rule). Also note §17/§22: **re-import discards BodySetup/CollisionTraceFlag**, so the 187 structural cells must be re-verified per mesh after import, not assumed.

**G4 — §38: masked masters read opacity from the colour texture's alpha, and 369 of 444 masked instances in this port are zero-alpha.**
`mat_joint_a` is masked (clip 0.333, two-sided) and parented to `M_GlassTrans`. The documented fix for this class is reparenting to `M_PropMaster` — but the entry also says to run the census first (`audit_mi_alpha.py --census`) rather than judge by eye, and that `OpacityMaskClipValue` is a red herring. Rev 3 makes Task 8 census-driven, before and after.

Two more, both cheap: §30 — a stage that skips on a missing input exits 0, so the `ALLOW_DELTA=1` in the level chain is now an explicit, logged choice rather than a habit; §31 — every transform write is re-read and gated in the same process (`set_actor_location` silently no-ops on component-less actors), which applies to the region actors' positions as well as their collision profile.

Still carried from rev 2: source-vs-cooked gate (`9,120,654`), region meshes instead of one world-space mesh (float32 ULP at the map's 26.6 km extent ≈ 0.25 cm vs a 1.0 cm lift), and the mesh+map **pair install**.

---

## Tasks

### Task 0 — Prove a joint has road underneath it (offline)
New `c1/scripts/joint_support.py`. For each `mat_joint_a` face centroid, cast down 5 cm and record whether a **non-decal** face is there. Report per cell `supported / unsupported / none`; same for `mat_mj_*`.

**Gate:** measured 2026-11-07 — `joint_a` 87/14,001 unsupported, `mj` 45/6,850. Depth re-test on those 132 faces (`joint_depth.py`, search to 200 cm): **37 sit over a 5–10 cm recess** (harmless, split them), **3 over 30–100 cm**, **92 over nothing within 2 m** — i.e. **95 faces genuinely span a void**, 69 `joint_a` + 26 `mj`, in 55 cells.

**Decision — exclude per FACE, not per cell.** The 95 void faces stay in the structural (collidable) mesh; every other decal face splits. Per-cell exclusion would re-solidify all of a cell's joints to save a handful of faces, and the splitter already works face by face, so the finer cut is free. The exclusion list is keyed on rounded face centroid from `joint_depth.json`, and the split report must show `excluded_faces == 95`.

### Task 1 — Split the geometry
`c1/scripts/split_decals.py` (dry run clean: `touched=187 decal_tris=20851 merged=20851 ok=true`).

Changes required before it runs for real:
- **compact** each rewritten cell OBJ to referenced vertices (G2);
- emit region decal OBJs with **pivot-relative** world metres (G-region precision);
- per-cell exclusion list from Task 0.

**Gates:** `mismatch == []`; source structural total exactly **9,120,654**; decal total exactly **20,851**; every rewritten cell's referenced-vertex bbox unchanged on X/Y/Z vs its pre-split bbox (decal faces are interior to the cell, so a bbox shift means an exclusion error).

### Task 2 — Capture the shipped slot arrays BEFORE any mesh is touched
`make_slotmap.py` over `UAssetTool --dump` of the 187 shipped cell assets from `zzzzz_AMC_C1Mesh_v3_P.pak` → `slotmap.json`, capturing **slot order, nulls and `ImportedMaterialSlotName`** (G1), not just name→MI.

**Gate:** 187 cells; `want_slots` and `want_nonnull` recorded per cell; every non-null resolves to a real MI. After the reimport this file is the only copy.

### Task 3 — Import the structural cells and restore their slot arrays exactly
`import_local.py` (full 555 pass, `IMPORT_GATE_OK`, `no_collision=0`) then new `apply_slotmap.py`, which rebuilds each array from `slotmap.json` **including nulls**.

**Gates:** `got_slots == want_slots` and `got_nonnull == want_nonnull` for all 187 (G1); per-mesh `collision_trace_flag` read back as `CTF_UseComplexAsSimple` in a fresh process (§17); scale gate per cell — `2 * box_extent` vs OBJ bbox ×100 on three axes (§36.1-2).

### Task 4 — Import the decal meshes
New `c1/scripts/import_decal.py`: same import options as `import_local.py`; `CTF_UseDefault` with an empty body (G3); assign the 92 MIs by name.

**Gates:** per-region tri count == source; 92 slots resolve; flag readback `CTF_UseDefault`; log `DECAL_GATE regions=N tris=20851 mats=92`.

### Task 5 — Place one actor per region
New `c1/scripts/spawn_decal_actors.py`: StaticMeshActor at each region pivot, `Mobility=Static`, `CollisionProfileName=NoCollision`, label `C1_Decals_<region>`.

**Gates (§31):** read location **and** rotation **and** collision profile back in the same process; `StaticMeshActor` = 554 + N; PlayerStart and both garages still at Shibaura/Tatsumi.

### Task 6 — Cook
`D:\cook_alllights.ps1` → `Done!`. Persistent level changes this time (new actors) — unlike every earlier recook here.

**Gates:** per-cell cooked tris drop by exactly that cell's decal tris (`verify_meshes.py`); bbox per cell unchanged; map total drops by 20,851 ± degenerate faces.

### Task 7 — Level chain, in order
`06_postcook_patch.sh` → `SETCLASSREF_OK` ×3 + `REPAIR_OK`; then `apply_map_edits_p22.sh` → `MAP_EDITS_OK` + `CLONE_OK … (593234,-466784,87449)`.

**Gates:** shipped-bytes search `SHIBAURA`×2 / `TATSUMI`×1 / old spawn×0, three class refs, N decal actors. No `ALLOW_DELTA` unless the skip is intended and named in the report (§30).

### Task 8 — (removed) `mat_joint_a` parent — deferred, out of scope

Per the user's decision this job is **geometry only**. `mat_joint_a`'s `M_GlassTrans` parent stays as it is and moves to the separate masked-material pass driven by `audit_mi_alpha.py` and GOTCHAS §38. Consequence to keep in mind while testing Task 10: the joint sheets keep their current (translucent, masked) look, so "still visible" is judged against what they look like today, not against an opaque ideal. The Mats pak is **not rebuilt** — `zzzzz_AMC_C1Mats_P21_P` stays installed and untouched.

Ship set after this change: **`Mesh_v4` + `Map_v5` only.**

### Task 9 — Package, install as a pair, verify from the installed pak (§18)
`build_meshpak.sh` → `Mesh_v4`; `build_levelpak.sh <dir> <ABSOLUTE path> C1Full` → `Map_v5`; regenerate both manifests; `pakset.py check`; install both in one closed-game step.

**Gates:** pull the installed paks back and hash the extracted entries against the manifests; map pak sole claimant of `C1Full.umap`; mesh pak sole claimant of `Meshes/`.

### Task 10 — In-game acceptance
Joints and markings still visible, correctly placed, no z-fighting, no seam at a region boundary; driving over a joint no longer steps, while a real kerb still does (control); `/tp` to `c2_11` and to a bridge joint.

---

## Risks

1. **Slot array drift** (G1) — highest; gated on exact order, nulls and `ImportedMaterialSlotName`.
2. **Orphan verts / false bbox** (G2) — compaction plus a per-cell bbox gate.
3. **`joint_a` load-bearing** — Task 0 exclusion list.
4. **Collision flags are not self-verifying** (§17) — read back per mesh, fresh process.
5. **Pair install** — one step, hash readback from the installed paks.
6. **Server pak** — follow-up after client acceptance.

## Open questions

1. ~~`mat_joint_a` parent~~ — **decided: out of scope, geometry only.** Deferred to the masked-material pass (Task 8 above).
2. Server pak — now or after acceptance? (Plan: after.)
3. Region granularity — ~1.5 km chunks (≈10–16 actors) vs per-cell (187). Plan: chunks.

## Rollback

Up to Task 6 everything reverts on disk (`meshes_local_predecal\`, `slotmap.json`, actor set). From Task 9, `Mesh_v3` / `Map_v4` / `Mats_P21` reinstall from `D:\c1full_paks\` in the same closed-game window.

---

## Rev 4 amendment — single merged decal mesh (supersedes every "region" instruction above)

Decision: **do not spend effort on z-fighting for now.** The precision analysis stands on the record (+0.25 cm worst-case float32 error against a 1.0 cm lift, at the map's far edge) but it is a cosmetic risk, not a functional one, and the collision fix does not depend on it.

What this changes:

- **Task 1:** emit **one** merged decal OBJ (`meshes_local_decals\C1_Decals.obj`) in world metres at the world origin. No pivots, no chunk boundaries. Vertex compaction to referenced verts still applies (G2).
- **Task 4:** import **one** asset, `/Game/Mods/C1Full/Meshes/C1_Decals`, `CTF_UseDefault` + empty body, 92 slots assigned by name.
- **Task 5:** spawn **one** StaticMeshActor at `(0,0,0)`, yaw 0, `Mobility=Static`, `CollisionProfileName=NoCollision`. Actor count gate becomes `StaticMeshActor = 555`.
- **Task 9:** mesh pak gains one asset instead of N.
- **Task 10:** the only extra check is a deliberate look at the far corner of the map for shimmer or sunken decals. If it shows, the fix is a later re-chunk, not a redesign — the geometry split and the material work are unchanged by it.
- **Open question 3 is closed:** single mesh.

Everything else in this plan is unaffected: the joint-support gate, slot-array reconstruction with nulls, vertex compaction, `CTF_UseDefault` semantics, stage-6 + P22 ordering, and the mesh+map pair install.
