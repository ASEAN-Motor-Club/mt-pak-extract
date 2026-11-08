# P21 — `dum` geometry deleted from the cell meshes

Supersedes the material-side attempts to hide BeamNG's `dum` dummy volume (P19 `M_Hidden`
parent, P20 0-alpha mask). Confirmed in game: the cell at `c-1_-3` renders, the wall is
gone, and the road is drivable where it stood.

## Artifacts

- `zzzzz_AMC_C1Mesh_P.pak` — 11,406,291 B, sha256 `72d271b54a1ccafb…`
  - `c-1_-3` — `dum` group removed, 63,633 tris, 108 slots
  - `c1_-8` — `dum` group removed, 53,492 tris, 66 slots
  - `c-2_-15` — repaired control cell (no geometry change), 69,366 tris, 44 slots
  - `c3_17` — drain-grill slot retarget (`mat_sitamiti00_sh` off `WorldGridMaterial`)
- `zzzzz_AMC_C1Mats_P20_P.pak` — 3,074,002 B, sha256 `f34da5b456b26214…` (unchanged)
- Both archived at `/opt/data/releases/c1/` and installed on the client

The map, sun, sky, fog and game mode are untouched — they still come from
`zzzz_AMC_C1Test_P.pak`. Only mesh assets are overridden.

## Why materials could not hide it

`dum` is BeamNG's collision-only dummy (`colorMap: null.dds`). P19 reparented `MI_C1_dum` to
`M_Hidden`, which is `BLEND_Masked` + `MSM_Unlit`, not a discard-everything material. P20
reparented it to `M_AlphaTestOneSided` with `Texture` → `area_zz_02_gtf_tex_158` (alpha
coverage 0.0). Both instances are correct on paper and neither hid the slab.

Geometry deletion is the fix. `dum` occupies 12 faces in each of 15 cells; the two cells that
carry it as a **tall box** (4.4 × 80.4 × 125.1 m in `c-1_-3`, 218.5 × 128.1 × 409.8 m in
`c1_-8`) are the ones that read as a wall. The other 13 are flat 2.2 m ground sheets and were
left alone.

## What went wrong on the way (each cost a build)

1. **Absolute OBJ instead of the rebased one.** `meshes_local/*.obj` are produced by
   `rebase_obj.py`: x/y shifted by `-floor(min/500)*500` and V mirrored (`v' = 1 - v`).
   Importing a copy derived from `meshes/*.obj` applies the origin twice — the cell moves
   ~1.5 km and reads as "completely missing". Actor transforms are `origin*100` with Y
   negated, so the failure is a pure placement offset, not a render fault.
2. **`replace_existing=True` keeps the old LOD chain.** It rewrites LOD0 only. Dropping the
   `dum` slot left LOD1..3 indexing one past the end of the slot array. Delete the asset
   first (`EditorAssetLibrary.delete_asset`) so the import builds a single-LOD mesh.
3. **`material_slot_name` is an `unreal.Name`, not a `str`.** Every `dict.get` missed, and
   assigning the resulting empty list wiped all 108 slots. Cast before comparing.

## Gates this release establishes

- **Cooked-size gate**: a re-imported cell's cooked `.uexp` must land within a few percent of
  the shipped copy. Measured passes: 13,506,133 / 13,149,344; 11,778,521 / 11,479,456;
  15,345,921 / 15,199,210. A +38% delta (21,024,754 vs 15,199,210) reproduced on an
  **untouched** cell proved the importer was not reproducing the shipped asset — that A/B is
  how the importer itself gets tested.
- **Placement gate**: imported bounds must equal `(obj_metres - origin) * 100` with Y negated.
  `c-1_-3` post-import `x 46125..104664, y -101769..-40459`; with the actor at
  `(-100000, +200000, 0)` that is world `(-53875..4664, 98231..159541)` — the shipped world
  bounds to the centimetre.
- **No-duplicate gate**: freshly cooked map has 555 `StaticMeshComponent0` exports and 558
  `StaticMeshActor` entries, identical to the installed map, one package import per cell.
  Import never spawns actors; component count is the check.

## Known gaps

- `c11_9` (`_1_-_Default`, author-fallback material) still needs the BeamNG default material
  rebuilt and `mat_pa_tatsumi_parts_file0.dds` imported as a texture asset.
- The mirror's assets still carry the legacy 4-LOD chain everywhere except the three cells
  rebuilt here. Single-LOD is the project decision; a full re-import sweep is a separate job.
- `C1Full_Roads` cooks ~2.7 MB smaller than the shipped copy (57,539,639 vs 60,296,506),
  unexplained and irrelevant until a full map rebuild is attempted — that map must go through
  `06_postcook_patch.sh` or it ships with no game mode and no sun.
