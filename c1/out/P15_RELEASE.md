# P15 — full material reimport

The first build derived from the whole canonical source rather than patched family by family.
Confirmed in game by freeman ("this is looking better").

## Artifact

- `zzzzz_AMC_C1Mats_P15_P.pak` — 3,120,851 B, sha256 `dc8ff3b7565092fd…`
- 1,653 material instances, no shader archives
- Installed at `MotorTown/Content/Paks/`, overrides `Mods/C1Full/Materials/*` from the geometry pak
- Archived outside scratch at `/opt/data/releases/c1/` (scratch is collected after 24 h)

## Inputs

- **Source** `c1/source/merged.materials.json` — sha256 `9a828c5640c2d443…`, 1,605 materials
  (BeamNG *Tokyo's Shuto Expressway*, C1 loop; census re-verified against the port's baseline)
- **Plan** `c1/out/materials_plan.json` — sha256 `52e62287ee18d125…`, 1,653 rows
- **Compiler** `c1/tools/compile_materials.py`; **apply step** `UAssetTool --apply-plan`

## Decisions carried by the plan

- **1,173 opaque** → `M_PolygonMaster` (`BaseColor`)
- **355 masked** → `M_AlphaTest` (`Texture`), clip = `alphaRef/255` per material
- **79 bake** → separate opacity map composited into the colour alpha, clip 0.5
- **8 ownalpha** → masked off the colour's own alpha, clip 0.5
- **4 left translucent** — three DXT1 (no alpha channel to mask with), one with a 1/255 spread
- **34 `keep_authored`** — port-only instances with no canonical material
- **Two-sided: 79 rows**, from the source's own flag. Not a blanket setting.
- **Emissive: 186 rows accounted** — 66 map-carrying; 136 reported lost (120 on the masked
  master, which exposes no emissive parameter)
- **AO dropped and reported** on 156 rows; no non-foliage master takes an AO map

## What the build depends on

`M_AlphaTest`/`M_BaseTexture` take the colour map in **`Texture`**; `M_PolygonMaster`/`M_PropMaster`
in **`BaseColor`**; `M_BaseColor` has no texture slot at all (`Color` is a vector). The apply step
reads that from the plan row, so an instance can never be written with a parameter its master does
not have.

## Also fixed

Bushes: the background behind foliage and the balcony bushes is gone. That was never a
vegetation-specific defect — it was the same unbound parameter as the road markings, fixed by the
reimport without any per-family rule.

## Known gaps

- 95 secondary texture references (mostly `*em`/`*EM` emissive maps and a few `TNL`/`SMO` normals)
  point at assets the port never shipped. Reported per row.
- The 4 translucent leftovers sort badly over the road. Expected.
