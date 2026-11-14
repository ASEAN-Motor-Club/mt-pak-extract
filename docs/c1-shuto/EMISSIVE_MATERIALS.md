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

Three gaps, any one of which was enough to make the map look dead or wrong:

1. **The glow textures were never in any atlas.** `mktextures2.py` builds the three
   albedo tiers from the `basecolor` slot only. 51 of the 57 emissive textures had no
   atlas cell at all — the 6 that did were there by coincidence, because some *other*
   material uses the same image as its basecolor.
2. **The shader had no emissive term.** The only thing writing to
   `totalEmissiveRadiance` was the baked-lamp line
   (`diffuseColor * vIllum * uLightGain`, driven by `lights.json`). Nothing sampled a
   glow texture.
3. **The intensity data was the wrong data.** `scalars.EmissiveStrength` is 1.0 on all
   57 — it is not where the brightness lives. See the next section.

## The intensity and colour live in the BeamNG source, not in `EmissiveStrength`

Every material in the source archive (`/opt/data/inbox/c1src/c1_src.zip`, definitions
keyed by definition name and resolved through `mapTo`) carries
**`Stages[0].emissiveFactor`**: an HDR colour multiplier. It is per material, it is
tinted, and it spans **1.0 to 16.06**:

| material | emissiveFactor | reads as |
|---|---|---|
| `mat_obj_dkk_a_00` | `[16.06, 0, 0]` | saturated red beacon |
| `mat_lamp311`, `mat_lamp201_head` | `[10, 3, 0]` | sodium street lamp |
| `mat_singou_c` | `[6, 10, 10]` | cyan signal head |
| `building_window23` | `[6.36, 7.16, 8.30]` | cool white windows |
| `building_window1` | `[7.06, 4.48, 3.16]` | warm interior light |
| `mat_tokyotower_sh_glow` | `[2.35, 0.37, 0]` | red/orange tower flood |
| `mat_mat_window3_glass_sh` | `[1.20, 1.20, 1.20]` | barely-lifted glass |
| 15 more materials | `[3.92, 3.92, 3.92]` | neutral |

BeamNG adds `emissiveMap * emissiveFactor` in linear space and tone-maps the result.
The first viewer pass used a single white multiplier instead, which is why it read as
white walls rather than lit windows: the brightest window page in the map was pushed
2× white while the tower and the signals — which the source tints hard — came out
white as well. `mkemis.py` now reads the factors out of the archive and the shader
applies them per material.

## How it renders now

### Atlas (`mkemis.py`)

```
site/emis.bin   TXA1 | u16 cells | u16 size | u8 rgba[cells][size][size][4]
                64 cells @ 128 px, 4.2 MB, cell 0 = black
site/emis.json  {"cell":128,"cols":8,"rows":8,
                 "mats":{material:[cell, strength, u0, v0, u1, v1, fr, fg, fb]}}
```

**Each cell stores only the CONTENT rect of its source page, not the whole page.**
39 of the 57 glow maps are sprites on a mostly-black sheet — content coverage runs
from 0.1% (`mat_PA_tatsumi_parts`: a dot at x 0.55–0.58, y 0.16–0.18 of a 256×512
page) to 100%. Packing the whole page into 128 px spent almost all of it on black
and left the glow as mush; cropping to the content rect and shipping its normalised
corners gives the same cell 2–8× more effective resolution.

Everything outside that rect is black in the source (verified: max channel value
outside the content box is <= 8 across all 57), which is what makes the crop lossless.

Unlike the albedo tiers, emissive cells are **not** mean-normalised: emission is an
absolute colour that gets *added*, not a multiplier on vertex colour. Textures whose
brightest channel is below 8 are dropped as effectively black.

Published at `map_tiles/shuto/v8emis/emis.bin` and `shuto-map/emis.json`.

### The UE conversion dropped the emissive flag for 126 materials

The atlas used to be built from `materials_ue_v2.json` (the ported UE material
table), which kept an `emissive` slot for only **57** materials. BeamNG's own
definitions say **183 ported materials emit**. The 126 missing ones are exactly the
per-material emitters:

- 8 with a real `emissiveMap`: `mat_daisi_window_etc`, `mat_daisi_all_komono`,
  `mat_daisi_komono_etc`, `mat_heiwajima_all_komono`, `mat_ooi_w_all_komono`,
  `mat_all_komono_00`, `mat_singou_d`, `mat_singou_d_depth`.
- 118 **self-emissive** materials — `emissive: true` with no `emissiveMap`, so BeamNG
  makes their own colour map glow: `mat_u_window_sh`, `mat_windou2_siro8_sh`,
  `mat_window3_aka5_sh`, `mat_skg_hizyou_*`, every `sign_*`, vending machines
  (`mat_PA_siba_jihanki02`), station signs, `mat_kbj*` building lights.

`mkemis.py` now reads the **BeamNG archive** as the authority, not the UE table, and
resolves each material two ways:

- `emissiveMap` present → its own atlas cell (65 materials, 8x9 grid at 256 px).
- `emissive: true`, no map → **cell 255 sentinel**: the shader reuses the albedo
  texel already sampled for that vertex (`clamp(texel.rgb * 2.0, 0, 1)`, since the
  albedo atlas stores mean-normalised texels). No atlas space, no extra fetch.

Textures the conversion never extracted (the `mat_daisi_*`/`mat_singou_c_*` sheets)
are read straight out of `c1_src.zip` with PIL — it reads DDS (BC1/BC2/BC3) as well
as PNG. Note BeamNG capitalises suffixes (`_file0EM.dds`) while the archive stores
lowercase, so the lookup is case-insensitive.

Result: 183 materials emitting, 71 atlas cells, 18.9 MB (3.9 MB served brotli).

### Two defects found by review (2026-11-14, second pass)

**Animated materials showed every frame at once.** Four of the 57 are BeamNG
flipbooks — `animFlags 16` plus `sequenceSegmentSize` (0.25–0.5) — so the sheet holds
2–4 frames side by side and the game scrolls the UV to show one. Sampling the whole
sheet paints all animation states simultaneously (ferris wheel, crossing signal,
traffic signal). `mkemis.py` now clamps the UV rect to the first segment.

**128 px cells destroyed detail on the big pages.** Measured with a bottleneck test
(source → cell → back up, high-pass correlation): median 0.90 retained at 128 px, but
`mat_tate_kanban00_sh` 0.41, `mat_honsen_daisi01` 0.55, `mat_kan_p1_00_sh` 0.56 and
`mat_mat_window3_glass_sh` 0.60 — i.e. 40–60% of the glow pattern lost on the
materials that cover the most geometry. Cells are now 256 px (16.8 MB, 4.19 MB served
brotli), which lifts the median to 0.98 and the worst case to 0.70.

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
attribute float aEmis; attribute float aEs; attribute vec4 aEmisUv;
varying float vEmis; varying float vEs; varying vec4 vEmisUv;
vEmis = aEmis; vEs = aEs; vEmisUv = aEmisUv;

// fragment, next to the lamp term
if (uEmisOn > 0.5 && vEmis > 0.5) {{
  vec2 ec = vec2(mod(vEmis, 8.0), floor(vEmis / 8.0));
  // cellUv -> position inside the cell's content rect; outside it, emit nothing
  vec2 eRel = (cellUv - vEmisUv.xy) / (vEmisUv.zw - vEmisUv.xy);
  float eIn = step(0.0, eRel.x) * step(eRel.x, 1.0)
            * step(0.0, eRel.y) * step(eRel.y, 1.0);
  vec3 eCol = texture2D(uEmis, (ec + clamp(eRel, 0.0, 1.0)) / vec2(8.0, 8.0)).rgb * eIn;
  // vEmisTint = BeamNG emissiveFactor (HDR, 1.0..16.06); Reinhard maps that range
  // into display range monotonically, so hue and relative intensity survive and
  // nothing flat-lines the building behind it.
  vec3 em = pow(eCol, vec3(2.2)) * vEmisTint * vEs * uEmisGain;
  totalEmissiveRadiance += em / (vec3(1.0) + em);
}}
```

The `eIn` mask is not optional: `cellUv` is the *whole-page* UV, `eRel` is the
same point expressed inside the content rect. Skipping the mask stretches the
sprite over the entire surface — measured on `mat_shock_shingou`: mean frame
luminance 27 → 39 and bright pixels 80k → 152k, i.e. every facade lit. With the
mask the pass adds light only where the authored page has glow, so the UV
mapping is bit-identical to sampling the full page, just sharper.

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

## UV review (2026-11-14)

What the sampling chain actually does, and where it can go wrong:

- **Same UV space as albedo.** `cellUv = clamp(fract(vec2(vUvT.x, -vUvT.y)), 0.002, 0.998)`
  is shared by every atlas lookup, so the emissive lands exactly where the basecolour
  does: tiling comes from `fract`, the Y flip is the decoder's negation undone, and
  filtering matches (`ClampToEdgeWrapping`, `LinearFilter`, `generateMipmaps = false`).
  Verified cell-by-cell: all 57 cells byte-match their downscaled source PNGs (max
  mean absolute error 0.0), so no material is sampling the wrong texture.
- **9 materials draw their glow from a different page than their basecolour**
  (`building_window1/8/12/20/23` → `lamp/building_internal_lights1` over a 32×16 glass
  tile; `mat_kan_p1_00_sh` → `ferris_glow_color` with no basecolour at all;
  `mat_botom_u_09`, `mat_lamp701_head`, `mat_shock_shingou` → the `em`/`e`/`g` variant of
  their own page). For the `_em`/`_e`/`_g` variants the layout matches the `_d` page and
  the UVs line up. For the five window families the glow sheet is authored for a
  different UV layout than the glass tile, so its lit rectangles cannot coincide with
  the window frames — that is an authored-material property, not a viewer bug, and it is
  what to check first if a facade looks lit in the wrong pattern.
- **Cell aspect is square, sources are not** (8:1 for `mat_denko_r_00`, 1:2 for
  `mat_mat_window3_glass_sh`, everything in between). Squashing is applied identically
  in the albedo tiers, so alignment holds, but the long axis loses resolution. Aspect-
  preserving cells would need a matching change in `mktextures2.py`, otherwise the glow
  would drift relative to the basecolour.
- **No UV transform is available.** The extractor records slots, scalars and masters,
  not TexCoord scale/offset or a second UV channel. If a material instance samples its
  emissive with a different tiling than its basecolour, the viewer cannot reproduce it
  without extending the MI dump. Nothing in the current content proves that it does, but
  this is the one known blind spot.
- **Emissive textures carry no meaningful alpha** (max 1.7% transparent pixels across all
  57), so storing cells opaque loses nothing.

## Gotchas

- **A `DataTexture` needs a full `cols*rows` grid.** `emis.bin` holds exactly 64 cells
  (57 materials + sentinel + black padding). A short buffer uploads garbage or fails the
  `texImage2D` call outright — pad, do not trim.
- **Tiles are fetched as `<tile>.bin`, not `.svt`.** The publish step renames the
  extractor's `.svt` (and its `.br` twin) to `.bin`; renaming is also what makes
  `brotli_static` serve the compressed copy.
- **The atlas URL must be versioned, not just query-busted.** `/map_tiles/shuto/` is
  served `immutable, max-age=31536000` and sits behind Cloudflare, which pins the bare
  URL (`cf-cache-status: HIT`, age 2000 s) — a republish at the same path is invisible.
  The atlas now lives at `map_tiles/shuto/v9emis/emis.bin`; bump that directory and the
  `?v=` query together whenever the atlas content changes. This was hit for real while
  verifying: `curl` kept reporting the old 4.19 MB file while the origin had 16.8 MB.
- **Do not mean-normalise emissive cells.** The `2.0 * texel` multiplier in the albedo
  path only works because those cells were divided by their own mean; copying that here
  would shift every colour.
- **`manifest.json` `override` tiles come from `v6f/`.** If an emissive tile is patched,
  publish it into `v6f/` and list it in `override` — never overwrite a `v6/` tile that
  carries a one-year immutable cache header.
- **Do not ship a flat emissive multiplier.** A uniform white 2.0 gain with no tone
  mapping blew the map out: the emissive region sat 3× above a ~20/255 night frame and
  every lit surface read as a light panel. Measured on `mat_shock_shingou`: 16.9% of
  emissive pixels above luminance 200. `emissiveFactor` + Reinhard fixes both the hue
  and the ceiling; `?emis=<gain>` (default 0.45) tunes the overall level without a
  rebuild.
- **`scalars.EmissiveStrength` is a decoy.** It is 1.0 for all 57 materials in the UE
  side of the pipeline; the real per-material data never made it out of the BeamNG
  archive. If a future port re-imports materials, import `emissiveFactor` as a vector.
- **Re-run `mkemis.py`, then bump the `?v=` query** on `app.js` and on the `emis.json` /
  `emis.bin` fetches when the atlas changes, or browsers keep the old copy. `emis.json`
  and the shader are a matched pair: the shader assumes the 6-field
  `[cell, strength, u0, v0, u1, v1]` entry and will read garbage from a 2-field file.

## Limits / next steps

- Cells are 128 px over the *content rect*: adequate for window bands and glow pools,
  soft up close on lit signage. 256 px is a one-line change in `mkemis.py` (~16.7 MB
  instead of 4.2 MB). The `mat_PA_tatsumi_parts` class of materials cannot improve —
  their content is 8×10 px in the source.
- Emissive and baked lamp irradiance are independent and can double-count where a lamp
  material also sits inside a light's radius. It reads as "bright lamp housing", not as
  an error, but a per-material weight (0.5 for lamp housings) is the knob if it looks hot.
- Emissive cells are always stored opaque, so mask clamping comes only from the
  *albedo* cell alpha: on `M_C1_Surface_Masked` materials (`mat_lamp_tnl_01`,
  `mat_kb_light_a`, `mat_tokyotower_sh_glow`, …) the fragment still discards on the
  basecolor/opacity mask, but a glow texture is never clipped by its own alpha. If a
  glow map ever needs its own cutout, that is a format change (it has no spare channel
  once the emissive colour is in RGB).
- Per-material `EmissiveStrength` is read but always 1.0 in this content; the atlas
  format already carries it, so varying it later needs no format change.
