# C1 decal collision split — implementation plan (rev 2, after review)

Supersedes `2026-11-07_1635-c1-decal-collision-split.md` (rev 1). Rev 1 is kept for the diff — it had four real defects, one of them fatal to its main design decision.

**Goal:** stop the road-joint/marking decal sheets from being solid: remove `mat_joint_*` / `mat_mj_*` geometry from the collidable cell meshes and render it from separate NoCollision meshes, losing no visible geometry.

**Architecture:** split at the source-OBJ level (the only level where a per-material cut exists), re-import the structural cells under their existing names, and re-render the decal faces from a small number of region meshes whose actors carry `NoCollision`.

**Scope measured (2026-11-07, `obj_inventory.json` + dry run):** 187 of 555 cells, 92 material names, **20,851 tris** — `mat_joint_a` 14,001 (67%), `mat_mj_*` 6,850. Source-side total 9,141,505 tris; cooked/shipped 9,131,921.

**Why a split is the only option:** `import_local.py:26,86` sets `CTF_USE_COMPLEX_AS_SIMPLE` on every cell mesh, so a cooked StaticMesh collides as its whole triangle soup. UE has no per-material or per-section collision switch, and this port has no vertex-level collision authoring path.

---

## Review findings — what rev 1 got wrong

**1. The triangle gate compared source counts to cooked counts.**
Rev 1 gated structural tris at `9,131,921 − 20,851 = 9,111,070`. But 9,131,921 is the *cooked* total after degenerate faces are dropped at import; the splitter counts *source* triangles, 9,141,505. Correct source-side gate: **9,120,654**. The cooked side is checked separately against the fresh cook.

**2. "One world-space decal mesh + one actor" was a precision bug.**
The map spans x −1,104,777…611,734 cm and y −1,002,062…1,658,899 cm (≈17 × 26.6 km — `set_transforms.py`'s own gate asserts those bounds). UE stores StaticMesh positions as float32; at |y| ≈ 1.66e6 cm the ULP is 0.125–0.25 cm, the same order as `mat_joint_a`'s **1.0 cm** lift. Merging the map into one mesh makes decals z-fight or sink at the far end, silently.
**Fix:** region meshes with pivot-relative vertices, chunk ≤ ~1.5 km (ULP ≤ 0.015 cm), one actor per chunk — ≈10–16 actors, not 1 and not 187.

**3. Re-import destroys the slot→material binding and rev 1 had no restore step.**
`make_slotmap.py` documents it: the shipped slot name is the OBJ `usemtl` name **minus its numeric suffix** (`mat_botom_u_10` → `mat_botom_u`), MIs resolve exact-first then longest-prefix, and "delete-then-import destroys the only copy of the binding". Removing decal faces also removes their `usemtl` entries, so slot lists shrink or reorder. Without an explicit re-assignment pass the 187 cells ship with missing or shuffled materials — worse than the bug being fixed.
**Fix:** capture a slotmap **from the shipped Mesh_v3 assets before any geometry is written**, then re-assign by name after import; the same mechanism assigns the decal meshes' 92 slots.

**4. `CTF_USE_SIMPLE_AS_COMPLEX` is not a reliable "no collision".**
With zero convex elements the flag can still fall back to complex on some query paths. The authoritative switch is the component: `CollisionProfileName = NoCollision` on every decal actor. The mesh flag stays as defence in depth; acceptance is in-game, not a flag readback.

**5. `mat_joint_a` may be load-bearing, and rev 1 never checked.**
14,001 tris sit on expansion joints, including bridge joints where the plate can be the only surface spanning the gap. Removing its collision there opens holes instead of fixing bumps. Now Task 0, gating the whole split.

Smaller: `merged_verts` should land near 62 k (≈3 per tri, unwelded), not the ~90 k I estimated; and **mesh pak and map pak must ship as a pair** — map v5 without mesh v4 points actors at meshes that are not installed.

---

## Tasks

### Task 0 — Prove a joint has road underneath it (offline, writes nothing)
**Files:** new `c1/scripts/joint_support.py`; input `D:\C1FullMirror\meshes_local\*.obj`

For every cell with `mat_joint_a`, take each decal face centroid, cast straight down, record whether a **non-decal** face lies within 5 cm below it. Report per cell `supported / unsupported / none`; same for `mat_mj_*`.

**Gate:** `unsupported == 0` everywhere → split everything. Otherwise exclude `joint_a` from exactly those cells (splitter takes a per-cell exclusion list) and publish the list. No "probably fine".

### Task 1 — Split the geometry
**Files:** `c1/scripts/split_decals.py` (dry run clean), `D:\C1FullMirror\Scripts\split_decals.json`

Rewrites `meshes_local\<cell>.obj` without decal faces (vertex arrays untouched, no index remap, so UVs and slot order cannot drift) and emits region decal OBJs with pivot-relative world metres.

**Step 1:** `--check` → `touched=187 decal_tris=20851 merged=20851 ok=true` (measured), `mismatch == []`.
**Step 2:** measure and record `meshes_local` size, then back up the 187 originals to `meshes_local_predecal\`.
**Step 3:** run for real; re-run `--check` → `touched=0`, `structural_tris = 9,120,654`.
**Step 4:** per-region tri counts sum to 20,851.

**Gate:** source structural total exactly 9,120,654, decal total exactly 20,851. Nothing else passes.

### Task 2 — Capture the shipped slotmap BEFORE touching any mesh
**Files:** `c1/scripts/make_slotmap.py` (existing); source `D:\c1full_paks\zzzzz_AMC_C1Mesh_v3_P.pak`

**Step 1:** `UAssetTool --dump` each of the 187 shipped cell assets out of Mesh_v3 → `make_slotmap.py` → `slotmap.json`.
**Step 2:** every slot name must resolve to a real MI (exact-first, longest-prefix); any `?` is a stop.

**Gate:** 187 cells, 0 unresolved slots. After the reimport this file is the only copy of the binding.

### Task 3 — Import the structural cells and restore their materials
**Files:** `c1/scripts/import_local.py` (unchanged), new `c1/scripts/apply_slotmap.py`

**Step 1:** import — signature changes, so a full 555-cell pass; expect `IMPORT_GATE_OK`, `no_collision=0` (cells stay solid).
**Step 2:** apply `slotmap.json` by name to the 187 cells; re-read every asset and compare slot→MI against the map.
**Step 3:** dump three cells (`c0_-10` heaviest joint user, `c2_11` heaviest `mj_*`, one untouched control) and diff against their pre-split dumps: surviving slots identical in name and MI; a decal-only slot may legitimately vanish.

**Gate:** 187/187 match. One mismatched slot means wrong textures on an entire cell.

### Task 4 — Import the decal meshes and their materials
**Files:** new `c1/scripts/import_decal.py`, `apply_slotmap.py` reused

Import each region OBJ (`/Game/Mods/C1Full/Meshes/C1_Decals_<region>`) with `import_local.py`'s settings; set `CTF_USE_SIMPLE_AS_COMPLEX`, assert zero convex elements; assign the 92 MIs by name.

**Gate:** imported tris == source tris per region (sum 20,851); every slot resolves; log `DECAL_GATE regions=N tris=20851 mats=92`.

### Task 5 — Place one actor per region
**Files:** new `c1/scripts/spawn_decal_actors.py`

Per region: spawn a StaticMeshActor from its mesh at the region pivot, `Mobility=Static`, **`CollisionProfileName=NoCollision`**, label `C1_Decals_<region>`; save the level.

**Gate:** `StaticMeshActor` count = 554 + N; PlayerStart and both garages still at Shibaura/Tatsumi; every new actor reads back `NoCollision`.

### Task 6 — Cook
`D:\cook_alllights.ps1` → `Done!`, six level outputs. The 187 cell assets must shrink; region meshes must exist. The persistent level changes this time (new actors) — unlike every earlier recook here.

**Gate:** per-cell cooked tri counts drop by exactly that cell's decal tris (`verify_meshes.py`); map total drops by 20,851 ± degenerate faces.

### Task 7 — Level chain in mandatory order
`06_postcook_patch.sh` (cwd `csharp/UAssetTool`, `TOOL` wrapping `/opt/data/dotnet10/dotnet`) → `SETCLASSREF_OK` ×3 + `REPAIR_OK`; then `apply_map_edits_p22.sh` → `MAP_EDITS_OK` + `CLONE_OK … (593234,-466784,87449)`.

**Gate:** shipped-bytes search — `SHIBAURA` ×2, `TATSUMI` ×1, old spawn ×0, three class refs, N decal actors.

### Task 8 — `mat_joint_a` parent
`--set-mi-parent` `MI_C1_mat_joint_a`: `M_GlassTrans` → `M_PropMaster`, drop glass-only params. Rebuild Mats as `P22`; **asset count stays 3,306**.

### Task 9 — Package and install as a pair
`build_meshpak.sh` → `Mesh_v4` (549 cells smaller + N region meshes); `build_levelpak.sh <dir> <ABSOLUTE path> C1Full` → `Map_v5`. Regenerate both manifests, `pakset.py check`, install **both in the same closed-game step**, remove predecessors together. Verify installed size+hash against manifests; map pak sole claimant of `C1Full.umap`.

**Gate:** a half install is worse than none — `Map_v5` without `Mesh_v4` points at missing meshes.

### Task 10 — In-game acceptance
- Drive over a Shibaura joint and a marked lane: no step. Control: a real kerb still jolts, so the result isn't placebo.
- Decals visible and correctly placed; no z-fighting; no seam at a region boundary.
- `/tp` to `c2_11` (1,035 decal tris) and to a bridge joint.

---

## Files that change

`c1/scripts/{split_decals,joint_support,import_decal,apply_slotmap,spawn_decal_actors}.py`; `D:\C1FullMirror\meshes_local\*.obj` (187 rewritten); `meshes_local_decals\*.obj` (new); `GOTCHAS.md`; `c1/out/pakset/*.json`.

## Risks

1. **Slot binding loss** (highest) — slotmap captured before any write, 187/187 name gate.
2. **Region seams / z-fighting** — pivot-relative vertices, ≤1.5 km chunks, inspect a boundary cell.
3. **`joint_a` load-bearing** — Task 0 gate plus per-cell exclusion.
4. **Editor spawn** — N actors instead of 187; still the operation with a crash precedent, revertible before Task 6.
5. **Pair install** — one step, hash readback.
6. **Server pak** — follow-up after client acceptance.

## Open questions

1. **`mat_joint_a` parent** — `M_PropMaster` now, or after the geometry is proven?
2. **Server pak** — now or after client acceptance? (Plan: after.)
3. **Region granularity** — 1.5 km chunks (≈10–16 actors) vs per-cell (187). Plan: chunks.

## Rollback

Up to Task 6 everything reverts on disk (`meshes_local_predecal\`, `slotmap.json`, the actor set). From Task 9, `Mesh_v3` / `Map_v4` / `Mats_P21` are in `D:\c1full_paks\` and reinstall in the same closed-game window.
