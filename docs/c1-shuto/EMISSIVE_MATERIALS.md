# C1 Shuto — emissive materials

The ported C1 corridor ships **57 self-illuminated materials**: window grids, street
and tunnel lamps, sign boxes, and the Tokyo Tower glow. This is the inventory, where
the data comes from, why none of it used to render, and how the web viewer draws it now.

Test surface: `https://www.aseanmotorclub.com/shuto-map/` (`?emis=0` disables the pass).

## Where the data lives

`material` rows are cooked material instances. The extractor flattens each one into
`/opt/data/cache/scratch/c1/mod_full/materials_ue_v2.json`:

```json
{
  "material": "building_window1",
  "mi": "MI_C1_building_window1",
  "master": "M_C1_Surface_Tex",
  "slots": { "basecolor": "/Game/Mods/C1/Textures/glass/building_window1",
              "emissive":  "/Game/Mods/C1/Textures/lamp/building_internal_lights1",
              "roughness": "/Game/Mods/C1/Textures/glass/building_window1" },
  "scalars": { "Roughness": 0.65, "Metallic": 0.0, "EmissiveStrength": 1.0, "Specular": 0.6 }
}
```

Two independent signals make a material emissive:

- `slots.emissive` — the glow texture the master samples;
- `scalars.EmissiveStrength` — the multiplier on it.

All 1,609 materials carry `EmissiveStrength`; **57 have it non-zero (1.0) and all 57 also
have an emissive slot**. That one-to-one mapping is why the atlas can key off the slot
alone, but the strength is still read (a future pass may vary it per material).

## Inventory

57 of 1,609 materials (3.5%), covering 151,875 of 1,589,112 vertices at LOD 2 — **9.6%
of the decoded geometry**, so this is not a rounding-error detail. By role:

- **window (6)** — building curtain walls and window grids
- **lamp/sign (13)** — street/tunnel-bridge lamps, sign boxes, Tokyo Tower glow
- **tunnel (6)** — tunnel wall and portal lighting strips
- **prop/sign (32)** — lit signage, vending machines, internal lights, misc glow props

Emissive texture families: `other` 30, `lamp` 13, `tunnel` 9, `wall` 3, `road` 1, `glass` 1.

Full table, sorted by geometry weight (LOD 2 vertex counts across all 554 tiles):

| material | kind | emissive texture | cell | strength | LOD2 verts | master | slots |
|---|---|---|---|---|---|---|---|
| `mat_mat_window3_glass_sh` | window | `area_zz_01_gtf_tex_273_aem_color` | 40 | 1 | 143,315 | `M_C1_Surface_Tex` | basecolor,emissive,metallic,roughness |
| `building_black1` | prop/sign | `building_black1` | 1 | 1 | 2,783 | `M_C1_Surface` | basecolor,emissive |
| `building_window8` | window | `building_internal_lights1` | 6 | 1 | 865 | `M_C1_Surface_Tex` | basecolor,emissive,roughness |
| `mat_wal_tnl_08_01` | tunnel | `mat_wal_tnl_08_01_file0em_color` | 54 | 1 | 861 | `M_C1_Surface` | basecolor,emissive |
| `mat_lamp_tnl_01` | lamp/sign | `area_zz_01_gtf_tex_130tnl` | 38 | 1 | 816 | `M_C1_Surface_Masked` | basecolor,emissive,opacity |
| `building_window20` | window | `building_internal_lights1` | 4 | 1 | 664 | `M_C1_Surface_Tex` | basecolor,emissive,roughness |
| `mat_kb_light_a` | lamp/sign | `area_zz_02_gtf_tex_099em_color` | 21 | 1 | 542 | `M_C1_Surface_Masked` | basecolor,emissive,opacity |
| `mat_heiwajima_u_parts01` | prop/sign | `mat_heiwajima_u_parts01_file0em_color` | 16 | 1 | 521 | `M_C1_Surface` | basecolor,emissive |
| `building_window1` | window | `building_internal_lights1` | 2 | 1 | 362 | `M_C1_Surface_Tex` | basecolor,emissive,roughness |
| `mat_tokyotower_sh_glow` | lamp/sign | `area_zz_01_gtf_tex_189em_color` | 53 | 1 | 241 | `M_C1_Surface_Masked` | basecolor,emissive,opacity |
| `building_window12` | window | `building_internal_lights1` | 3 | 1 | 157 | `M_C1_Surface_Tex` | basecolor,emissive,roughness |
| `mat_wal_tnl_09_01_w` | tunnel | `mat_wal_tnl_09_01_w_file0_g` | 57 | 1 | 124 | `M_C1_Surface` | basecolor,emissive |
| `mat_wal_tnl_08_03` | tunnel | `mat_wal_tnl_08_03_file0em_color` | 55 | 1 | 117 | `M_C1_Surface` | basecolor,emissive |
| `mat_botom_u_09` | prop/sign | `area_zz_01_gtf_tex_016em_color` | 9 | 1 | 105 | `M_C1_Surface_Tex` | ao,basecolor,emissive,metallic,normal,roughness |
| `mat_kan_p1_00_sh` | prop/sign | `ferris_glow_color` | 19 | 1 | 105 | `M_C1_Surface` | emissive |
| `mat_kb_obj_a` | prop/sign | `area_zz_01_gtf_tex_100em_color` | 22 | 1 | 46 | `M_C1_Surface` | basecolor,emissive |
| `mat_lamp201_head` | lamp/sign | `area_zz_01_gtf_tex_127_color` | 35 | 1 | 35 | `M_C1_Surface` | basecolor,emissive |
| `mat_tate_kanban00_sh` | prop/sign | `area_zz_02_gtf_tex_184` | 52 | 1 | 32 | `M_C1_Surface` | basecolor,emissive |
| `mat_honsen_daisi01` | prop/sign | `mat_honsen_daisi01_file0_e_color` | 17 | 1 | 27 | `M_C1_Surface` | basecolor,emissive |
| `mat_shock_shingou` | prop/sign | `area_zz_01_gtf_tex_176_g_color` | 47 | 1 | 27 | `M_C1_Surface_Tex` | ao,basecolor,emissive,metallic,normal,roughness |
| `mat_honsen_daisi05` | prop/sign | `mat_honsen_daisi05_file0em_color` | 18 | 1 | 24 | `M_C1_Surface_Masked` | basecolor,emissive,opacity |
| `mat_PA_tatsumi_parts` | prop/sign | `mat_pa_tatsumi_parts_file1_g` | 8 | 1 | 20 | `M_C1_Surface_Tex` | ao,basecolor,emissive,metallic,roughness |
| `building_window23` | window | `building_internal_lights1` | 5 | 1 | 18 | `M_C1_Surface_Tex` | basecolor,emissive,roughness |
| `mat_kbh_01_006` | prop/sign | `mat_kbh_01_006_file0` | 31 | 1 | 10 | `M_C1_Surface` | basecolor,emissive |
| `mat_kbm01_014` | prop/sign | `mat_kbm01_014_file0` | 34 | 1 | 8 | `M_C1_Surface` | basecolor,emissive |
| `mat_singou_e` | prop/sign | `area_zz_01_gtf_tex_180_g` | 50 | 1 | 8 | `M_C1_Surface` | basecolor,emissive |
| `mat_br_kameibashi_light` | lamp/sign | `mat_br_kameibashi_light_file0_g` | 10 | 1 | 7 | `M_C1_Surface` | basecolor,emissive |
| `lamp6` | lamp/sign | `lamp6e` | 7 | 1 | 6 | `M_C1_Surface` | basecolor,emissive |
| `mat_kbb02_007` | prop/sign | `mat_kbb02_007_file0` | 23 | 1 | 6 | `M_C1_Surface` | basecolor,emissive |
| `mat_kbf01_004` | prop/sign | `mat_kbf01_004_file0_g` | 24 | 1 | 4 | `M_C1_Surface` | basecolor,emissive |
| `mat_kbf_02_008` | prop/sign | `mat_kbf_02_008_file0` | 29 | 1 | 4 | `M_C1_Surface` | basecolor,emissive |
| `mat_kbf_02_009` | prop/sign | `mat_kbf_02_009_file0` | 30 | 1 | 4 | `M_C1_Surface` | basecolor,emissive |
| `mat_kbm01_011` | prop/sign | `mat_kbm01_011_file0` | 32 | 1 | 4 | `M_C1_Surface` | basecolor,emissive |
| `mat_singou_c` | prop/sign | `mat_singou_c_file0em_color` | 49 | 1 | 4 | `M_C1_Surface_Masked` | basecolor,emissive,opacity |
| `mat_obj_tnl_01` | tunnel | `mat_obj_tnl_01_file0m_color` | 43 | 1 | 3 | `M_C1_Surface` | basecolor,emissive,normal |
| `mat_br_light_tunnel_1` | lamp/sign | `mat_br_light_tunnel_1_file0_g` | 11 | 1 | 0 | `M_C1_Surface` | basecolor,emissive |
| `mat_br_shibabashi_light` | lamp/sign | `mat_br_shibabashi_light_file0_g` | 12 | 1 | 0 | `M_C1_Surface` | basecolor,emissive |
| `mat_chika2_01_00` | prop/sign | `area_zz_01_gtf_tex_028_g` | 13 | 1 | 0 | `M_C1_Surface` | basecolor,emissive |
| `mat_danseibashi_br_light` | lamp/sign | `mat_danseibashi_br_light_file0_g` | 14 | 1 | 0 | `M_C1_Surface` | basecolor,emissive |
| `mat_denko_r_00` | prop/sign | `area_zz_02_gtf_tex_038em` | 15 | 1 | 0 | `M_C1_Surface` | basecolor,emissive |
| `mat_kb_a_tsui_00` | prop/sign | `mat_kb_a_tsui_00_file0_e` | 20 | 1 | 0 | `M_C1_Surface` | basecolor,emissive |
| `mat_kbf01_005` | prop/sign | `mat_kbf01_005_file0` | 25 | 1 | 0 | `M_C1_Surface` | basecolor,emissive |
| `mat_kbf01_006` | prop/sign | `mat_kbf01_006_file0` | 26 | 1 | 0 | `M_C1_Surface` | basecolor,emissive |
| `mat_kbf01_007` | prop/sign | `mat_kbf01_007_file0` | 27 | 1 | 0 | `M_C1_Surface` | basecolor,emissive |
| `mat_kbf01_008` | prop/sign | `mat_kbf01_008_file0` | 28 | 1 | 0 | `M_C1_Surface` | basecolor,emissive |
| `mat_kbm01_013` | prop/sign | `mat_kbm01_013_file0` | 33 | 1 | 0 | `M_C1_Surface` | basecolor,emissive |
| `mat_lamp311` | lamp/sign | `area_zz_01_gtf_tex_128_color` | 36 | 1 | 0 | `M_C1_Surface` | basecolor,emissive |
| `mat_lamp701_head` | lamp/sign | `area_zz_02_gtf_tex_128_e_color` | 37 | 1 | 0 | `M_C1_Surface_Tex` | ao,basecolor,emissive,metallic,normal,roughness |
| `mat_lamp_tnl_01_mrc` | lamp/sign | `area_zz_01_gtf_tex_130tnl` | 39 | 1 | 0 | `M_C1_Surface_Masked` | basecolor,emissive,opacity |
| `mat_obj_dkk_a_00` | prop/sign | `area_zz_02_gtf_tex_140_g` | 41 | 1 | 0 | `M_C1_Surface` | basecolor,emissive |
| `mat_obj_dkk_b` | prop/sign | `mat_obj_dkk_b_file0em_color` | 42 | 1 | 0 | `M_C1_Surface_Masked` | basecolor,emissive,opacity |
| `mat_obj_tnl_box_B` | tunnel | `mat_obj_tnl_box_b_file0` | 44 | 1 | 0 | `M_C1_Surface` | basecolor,emissive |
| `mat_sglgta_00` | prop/sign | `area_zz_01_gtf_tex_168_g` | 45 | 1 | 0 | `M_C1_Surface_Masked` | basecolor,emissive,opacity |
| `mat_shlgta_00` | prop/sign | `area_zz_01_gtf_tex_173` | 46 | 1 | 0 | `M_C1_Surface` | basecolor,emissive |
| `mat_singou_b` | prop/sign | `mat_singou_b_file0_g` | 48 | 1 | 0 | `M_C1_Surface` | basecolor,emissive |
| `mat_takarabashi_br_light` | lamp/sign | `mat_takarabashi_br_light_file0_g` | 51 | 1 | 0 | `M_C1_Surface` | basecolor,emissive |
| `mat_wal_tnl_08_04` | tunnel | `mat_wal_tnl_08_04_file0em_color` | 56 | 1 | 0 | `M_C1_Surface` | basecolor,emissive |

`cell` is the cell in the emissive atlas (see below); cell 0 is the black "not emissive"
sentinel and is never assigned to a material.

## Why nothing rendered before

Two independent gaps; either one alone was enough to make the map look dead:

1. **The glow textures were never in any atlas.** `mktextures2.py` builds the three
   albedo tiers from the `basecolor` slot only. 51 of the 57 emissive textures had no
   atlas cell at all — the 6 that did were there by coincidence, because some *other*
   material uses the same image as its basecolor.
2. **The shader had no emissive term.** The only thing writing to
   `totalEmissiveRadiance` was the baked-lamp line
   (`diffuseColor * vIllum * uLightGain`, driven by `lights.json`). Nothing sampled a
   glow texture, and `EmissiveStrength` was published in `matslots.json` but never read.

So lit windows drew as plain lit geometry: correct albedo, no glow, indistinguishable
from unlit panels at night.

## How it renders now

### Atlas (`mkemis.py`)

```
site/emis.bin   TXA1 | u16 cells | u16 size | u8 rgba[cells][size][size][4]
                64 cells @ 128 px, 4.2 MB, cell 0 = black
site/emis.json  {"cell":128,"cols":8,"rows":8,"mats":{material:[cell,strength]}}
```

Unlike the albedo tiers, emissive cells are **not** mean-normalised: emission is an
absolute colour that gets *added*, not a multiplier on vertex colour. Textures whose
brightest channel is below 8 are dropped as effectively black.

Published at `map_tiles/shuto/v8emis/emis.bin` and `shuto-map/emis.json`.

### Per-vertex mapping (no re-cook)

SVT4 tiles already carry a per-tile material name table plus a per-vertex material index
(`mats` / `mat`). The viewer therefore resolves emissive cells at load time:

1. `loadEmis()` fetches `emis.json` + `emis.bin`, builds a `DataTexture`, flips
   `uEmisOn` to 1.
2. `attachTileEmis(mesh)` walks the tile's material table, looks each name up in
   `emis.json`, and writes `aEmis` (cell id, 0 = none) and `aEs` (strength) attributes.
3. Tiles already resident when the atlas arrives get the attributes retroactively, the
   same way `attachTileIllum` handles late `lights.json`.

Tiles published before this change keep working: a missing `aEmis` reads as 0, which is
"no emission", so the worst case is the old look.

### Shader

```glsl
// vertex
attribute float aEmis; attribute float aEs;
varying float vEmis; varying float vEs;
vEmis = aEmis; vEs = aEs;

// fragment, next to the lamp term
if (uEmisOn > 0.5 && vEmis > 0.5) {
  vec2 ec = vec2(mod(vEmis, 8.0), floor(vEmis / 8.0));
  vec3 eCol = texture2D(uEmis, (ec + cellUv) / vec2(8.0, 8.0)).rgb;
  totalEmissiveRadiance += pow(eCol, vec3(2.2)) * vEs * uEmisGain;
}
```

Deliberate choices:

- **Not multiplied by `diffuseColor`.** Emission is independent of albedo — window glass
  is nearly black by day and still glows at night. The lamp term *is* multiplied by
  albedo, which is why the same lux brightens a white line and not asphalt.
- **Gamma-decoded with `pow(..., 2.2)`** because the atlas is uploaded as plain RGBA8
  while the rest of the shader works in linear space.
- **Gain** lives in `emisGainUniform` (currently `2.0`) if the glow needs to be hotter.

## Verifying it

`?emis=0` exists so the pass can be A/B'd rather than eyeballed. Headless Chromium
(swiftshader), same camera, `?look=night&mat=mat_mat_window3_glass_sh`:

- pixels with luminance >120: **11,774 → 17,876** (+52%); >200: 2,723 → 4,405 (+62%)
- 49,964 px (3.1% of a 1600×1000 frame) change, concentrated on window bands and lamp rows

Reproduce:

```bash
chromium --headless=new --use-gl=angle --use-angle=swiftshader --enable-unsafe-swiftshader \
  --virtual-time-budget=45000 --screenshot=on.png \
  'https://www.aseanmotorclub.com/shuto-map/?look=night&mat=mat_mat_window3_glass_sh'
# then again with &emis=0 and diff the two PNGs
```

## Gotchas

- **A `DataTexture` needs a full `cols*rows` grid.** `emis.bin` holds exactly 64 cells
  (57 materials + sentinel + black padding). A short buffer uploads garbage or fails the
  `texImage2D` call outright — pad, do not trim.
- **Tiles are fetched as `<tile>.bin`, not `.svt`.** The publish step renames the
  extractor's `.svt` (and its `.br` twin) to `.bin`; renaming is also what makes
  `brotli_static` serve the compressed copy.
- **Do not mean-normalise emissive cells.** The `2.0 * texel` multiplier in the albedo
  path only works because those cells were divided by their own mean; copying that here
  would shift every colour.
- **`manifest.json` `override` tiles come from `v6f/`.** If an emissive tile is patched,
  publish it into `v6f/` and list it in `override` — never overwrite a `v6/` tile that
  carries a one-year immutable cache header.
- **Re-run `mkemis.py`, then bump the `?v=` query** on `app.js` (and `emis.json?v=`) when
  the atlas changes, or browsers keep the old copy.

## Limits / next steps

- Cells are 128 px: fine for window bands and glow pools, soft up close on lit signage.
  256 px is a one-line change in `mkemis.py` (~16.7 MB instead of 4.2 MB).
- Emissive and baked lamp irradiance are independent and can double-count where a lamp
  material also sits inside a light's radius. It reads as "bright lamp housing", not as
  an error, but a per-material weight (0.5 for lamp housings) is the knob if it looks hot.
- Masked emissive (glass seen through an alpha-test master) is not special-cased: the
  emissive cell alpha is forced opaque, so an emissive material on a masked master glows
  over its whole card.
- Per-material `EmissiveStrength` is read but always 1.0 in this content; the atlas
  format already carries it, so varying it later needs no format change.
