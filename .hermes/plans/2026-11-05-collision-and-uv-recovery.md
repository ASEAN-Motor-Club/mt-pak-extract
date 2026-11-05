# C1Full recovery: placement, collision, UV — plan

Date: 2026-11-05
Status: active

## Why we regressed

The re-base fix was correct in principle but wrong in **mechanism**. Placement is an
*actor* problem: the mesh assets were already cell-local (asset bounds = OBJ coords
minus the 500 m cell origin, with the importer's Y negation), so moving actors is
enough. Instead we **re-imported all 554 meshes**, which rebuilds each asset from
the OBJ and throws away everything the asset carried: collision, and the UV
orientation we had been getting right.

Consequence: every re-import cycle costs collision + UVs. That is the regression
pattern — geometry that renders but has no collision, then upside-down textures.

## Principle from here

1. **One asset rebuild, one purpose.** Geometry comes from the OBJ importer exactly
   once per coordinate-convention change. Placement is fixed by actor transforms only.
2. **Collision is a property pass, not an import.** All map meshes get
   `CollisionTraceFlag = CTF_UseComplexAsSimple` (trimesh collision). Re-importing to
   "get collision" is not a thing the OBJ importer does.
3. **Every step has a numeric gate.** No step is "done" because the log looked fine.
4. **No step is retried more than once without new evidence.**

## Coordinate convention (settled, user-stated)

- BeamNG → MT: metres → centimetres, **and opposite Y**.
- UE's OBJ importer negates Y on import (verified on `c0_-1`: file `+99…+592 m` →
  asset `−592…−99 m`, X/Z unchanged). That negation *is* the conversion — do not
  pre-negate in the OBJ.
- Therefore actors: `x = +origin_x × 100`, `y = −origin_y × 100`.
- Therefore UVs: mirror V (`v' = 1 − v`) so the mirrored geometry keeps textures
  upright. Applied at import time in `rebase_obj.py`.

## Steps and gates

### 1. Verify current state (no changes)
- actor transforms still `xf2` (554 actors, tag present)
- level union: x −11.2…8.0 km, y −10.7…16.9 km (matches checklist facts ±0.4 km)
- `probe_col.py` reports `with_simple_collision` — expected 0, recorded as baseline

### 2. Collision pass (`set_collision.py`)
For every mesh under `/Game/Mods/C1Full/Meshes`:
- `body_setup.collision_trace_flag = CTF_USE_COMPLEX_AS_SIMPLE`
- save asset
**Gate:** re-run `probe_col.py` → `complex_as_simple == 554`, `with_body_setup == 554`.

### 3. Cook
**Gate:** `LogCook: Display: Done!`, `C1Full_Roads.uexp ≈ 60.7 MB`.

### 4. Post-cook patch
**Gate:** `REPAIR_OK` + `PATCH_OK`, spawner export `_1`, 4 vehicle classes.

### 5. Assemble + pack
**Gate:** 554 meshes / 1653 materials / 2 maps / 2148 textures, `grep -c ShaderArchive == 0`,
pak size ≈ 699 MB.

### 6. Install
**Gate:** `SHA_MATCH`.

### 7. In-game verification (user)
- drive outside the C1 corridor: solid ground, no falling through
- textures upright (no 180° V flip)
- masked foliage/fence cutouts two-sided and correctly clipped

## Rollback

v22 pak is retained at `D:\c1full_paks\zzz_AMC_C1Full_v22_P.pak`; v21 kept as the
last known-textured build. `install_test.ps1 -Src <pak>` swaps in one call.

## Open items (not part of this fix)

- textures still live under `Mods/C1/Textures`; plan step 3 (namespace move to
  `C1Full/Textures` + reference rewrite) still pending
- 196 road/race actors still at (0,0,0) — regeneration not implemented
- `check_hidden.py` gate not yet run
