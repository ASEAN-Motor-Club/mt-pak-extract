# Lane ropes (`mat_saku_08_02`) — collision removal, shipped 2026-11-15

Goal: let cars cross the lane-separator ropes on C1. The material was already in
`c1/source/nocollision_materials.json` (`props` group), but the shipped mesh pak
predated that rule, so the triangles were still collidable in 68 cells.

## What shipped

`zzzzzz_AMC_C1Mesh_v16_NoRopes_P.pak` — 68 rebuilt cells only, mounted after
`zzzzz_AMC_C1Mesh_v15_P.pak`. 18,716 rope faces removed, nothing else changed.
Ropes disappear visually where a cell has no separate no-collision layer;
elsewhere they remain visible but non-solid.

## Recipe (the order matters)

1. `c1/scripts/filter_noropes.py` — drop the family's `f` lines from the
   **canonical** `D:\C1FullMirror\meshes_local` OBJs into `D:\C1FullMirror\noropes`.
   Do NOT use the split's `nc_out/cells_v2` re-export as an import source; it is
   lossy and shredded the map when used structurally.
   Cross-check: the filter's `faces_dropped` equals the split report's delta for
   the same family (both 18,716 here) — two independent methods agreeing.
2. `c1/scripts/import_noropes.py` (an `import_local.py` variant pointed at the
   filtered directory). **Delete its `*_state.json` first**: an unchanged source
   signature makes it report `import_done=0` and skip every cell, and every later
   step then runs on stale assets while looking successful.
3. `c1/scripts/ensure_material_dummies.py` — create placeholder
   `MaterialInstanceConstant`s for every path `slotmap.json` names. The C1 project
   only holds the emissive subset; without placeholders the slot restore aborts
   and the cooked mesh ships with **zero** material references. Placeholders never
   ship: the pak carries meshes only and the real instances resolve from the
   installed material paks at runtime.
4. `c1/scripts/remap_slots_by_name.py` — **not** `apply_slotmap.py`. Removing the
   rope section shifts every later section's material index, so a position-based
   restore paints wrong textures while every material path still looks correct in
   a dump. Bind by slot NAME, keeping the importer's array order.
5. Verify the **source** asset before cooking (one cell's slots must read
   `MI_C1_*`, not `WorldGridMaterial`), then `cook_client.ps1`, then verify the
   cooked `.uasset` material-reference count against the previously shipped one
   (120 vs 122 here), then pack only the affected cells.

## Two failure modes worth remembering

- **Unreal Python yields struct copies** when iterating `static_materials`.
  Mutating the iterated entry writes nothing; the mesh keeps `WorldGridMaterial`
  on every slot while the script reports success. Build fresh
  `unreal.StaticMaterial()` entries and assign the new array.
- **A remap is a no-op on an array `apply_slotmap.py` already overwrote** — the
  slot names are then the old positional ones. Re-import first, then remap.

Windows zips from `Compress-Archive` use backslash entry names; normalise to `/`
when extracting on Linux or the pak gets garbage paths. `unzip` is not installed
in the container — use Python `zipfile`.
