# C1 Shuto — emissive materials

The ported C1 corridor ships **183 self-illuminated materials**: window glass, street and
tunnel lamps, sign boxes, signal heads, vending machines, station signs and the Tokyo
Tower glow. This is what the source actually says, how each kind is resolved, why most of
it used to render as nothing, and how the web viewer draws it now.

Test surface: `https://www.aseanmotorclub.com/shuto-map/`
(`?emis=0` off, `?emis=<gain>` tunes, `?emisdebug=1` prints live counts).

## Authority: the BeamNG archive, not the UE material table

`/opt/data/inbox/c1src/c1_src.zip` is the BeamNG source (16 `*.materials.json`, 1,643
definitions, keyed by definition name and reached through `mapTo`). Each definition has
up to four `Stages`; stage 0 is the one that matters:

```json
{
  "name": "building_window1", "mapTo": "building_window1", "class": "Material",
  "Stages": [{
    "baseColorMap": "/levels/c1/art/textures/building_window1.dds",
    "emissiveMap":  "/levels/c1/art/textures/building_internal_lights1.dds",
    "emissiveFactor": [7.06, 4.48, 3.16],
    "instanceEmissive": true,
    "roughnessMap": "/levels/c1/art/textures/building_window1.dds"
  }]
}
```

Fields that decide emission:

- **`emissiveMap`** — a dedicated glow sheet, sampled with the same UVs as the base colour.
- **`emissive: true` with no `emissiveMap`** — the *colour map itself* is the emitter. This
  is how the majority of lit surfaces in this map are authored.
- **`emissiveFactor`** — HDR colour multiplier, 1.0 → 16.06, tinted per material. This is
  where brightness lives.
- **`sequenceSegmentSize`** (+ `animFlags 16`) — the sheet is a flipbook of 2–4 frames.
- **`instanceEmissive`** — the emissive is gated by the object's `instanceColor`. See
  "Day/night gating" below.

`/opt/data/cache/scratch/c1/mod_full/materials_ue_v2.json` is the *ported* UE material
table (1,609 materials). It is useful for base colour and masks, but it is **not** the
authority for emission — see the next section.

## The UE conversion dropped the emissive flag for 126 materials

The port kept an `emissive` slot for only **57** materials. The BeamNG definitions say
**183 ported materials emit**. The 126 missing ones are exactly the per-material emitters,
i.e. the ones a viewer notices:

- **8 with a real `emissiveMap`** — `mat_daisi_window_etc`, `mat_daisi_all_komono`,
  `mat_daisi_komono_etc`, `mat_heiwajima_all_komono`, `mat_ooi_w_all_komono`,
  `mat_all_komono_00`, `mat_singou_d`, `mat_singou_d_depth`.
- **118 self-emissive** (`emissive: true`, no map) — `mat_u_window_sh`,
  `mat_windou2_siro8_sh`, `mat_window3_aka5_sh`, `mat_skg_hizyou_*`, every `sign_*`,
  the vending machines (`mat_PA_siba_jihanki02`), station signs, `mat_kbj*` building
  lights.

Building the atlas from the UE table therefore reproduced the loss faithfully: those
surfaces were simply never lit. `mkemis.py` now reads the archive instead.

## Two kinds, two resolutions

| kind | count | how it is drawn |
|---|---|---|
| `emissiveMap` present | 65 | own atlas cell (256 px), sampled through the cell's content rect |
| `emissive: true`, no map | 118 | **cell 255 sentinel**: the shader reuses the albedo texel it already sampled |

The sentinel costs no atlas space and no extra fetch. Because albedo atlas cells are
mean-normalised (stored at 0.5× and multiplied by 2 in the shader), the emissive branch
compensates with `clamp(texel.rgb * 2.0, 0.0, 1.0)`.

Materials the conversion never extracted — the `mat_daisi_*` and `mat_singou_c_*` sheets —
are read straight out of `c1_src.zip` with PIL, which handles DDS (BC1/BC2/BC3) as well as
PNG. BeamNG capitalises suffixes (`_file0EM.dds`) while the archive stores lowercase, so
the lookup is case-insensitive.

Excluded on purpose: `emissiveFactor` parked at `1e-06` (BeamNG's "this is dead" value,
e.g. `lamp1_tunnel`), and definitions that were never ported (`godray_emitter`,
`thunderbolt`).

## Intensity: `emissiveFactor`, not `EmissiveStrength`

`scalars.EmissiveStrength` in the UE table is `1.0` on every material — it is a decoy and
carries no information. The real per-material data never left the archive:

| material | `emissiveFactor` | reads as |
|---|---|---|
| `mat_obj_dkk_a_00` | `[16.06, 0, 0]` | saturated red beacon |
| `mat_lamp311`, `mat_lamp201_head` | `[10, 3, 0]` | sodium street lamp |
| `mat_singou_c` | `[6, 10, 10]` | cyan signal head |
| `building_window23` | `[6.36, 7.16, 8.30]` | cool white windows |
| `building_window1` | `[7.06, 4.48, 3.16]` | warm interior light |
| `mat_tokyotower_sh_glow` | `[2.35, 0.37, 0]` | red/orange tower flood |
| `mat_mat_window3_glass_sh` | `[1.20, 1.20, 1.20]` | barely-lifted glass |
| 15 materials | `[3.92, 3.92, 3.92]` | neutral |

A single white multiplier (the first pass used 2.0) inverts the ordering: it pushes the
largest glass page hardest while flattening the tower and the signals that the source tints
hard. The shader now applies `emissiveFactor` per material and Reinhard-compresses
(`em / (1 + em)`) so hue and relative intensity survive without flat-lining the building
behind it. `emisGainUniform` (default 1.2) is the overall level.

## Atlas (`mkemis.py` → `site/emis.bin`, `site/emis.json`)

```
emis.bin   TXA1 | u16 cells | u16 size | u8 rgba[cells][size][size][4]
           72 cells @ 256 px, 8 cols x 9 rows, 18.9 MB (3.9 MB served brotli)
           cell 0 = black "not emissive"; cell 255 is the sentinel, not a cell
emis.json  {"cell":256,"cols":8,"rows":9,
            "mats":{material:[cell, strength, u0, v0, u1, v1, fr, fg, fb]}}
```

- **A `DataTexture` needs a full `cols*rows` grid.** 66 entries (65 materials + the black
  sentinel) pad to 72. A short buffer uploads garbage or fails `texImage2D` outright.
- **Each cell stores only the CONTENT rect of its source page.** Most glow sheets are a lit
  shape on a mostly-black page (content coverage runs from ~0.1% to 100%); packing the whole
  page spends the cell on black. The crop ships its normalised corners and the shader maps
  back into them. Outside the rect the source is black (max channel ≤ 8), which is what
  makes the crop lossless.
- **Cells are not mean-normalised.** Emission is an absolute colour that gets *added*, not a
  multiplier on vertex colour. Copying the albedo path's `/mean` would shift every colour.
- **Flipbooks clamp to frame 0.** Four materials (`mat_denko_r_00`, `mat_kan_p1_00_sh`,
  `mat_shock_shingou`, `mat_singou_e`) pack 2–4 animation frames side by side; sampling the
  whole sheet paints every state at once.
- **Textures whose brightest channel is below 8 are dropped** as effectively black.

### Why 256 px

Measured with a bottleneck test (source → cell → back up, high-pass correlation) at 128 px:
median 0.90 of the glow pattern retained, but `mat_tate_kanban00_sh` 0.41,
`mat_honsen_daisi01` 0.55, `mat_kan_p1_00_sh` 0.56, `mat_mat_window3_glass_sh` 0.60 — i.e.
40–60% lost on exactly the materials that cover the most geometry. At 256 px the median is
0.98 and the worst case 0.70.

## Per-vertex mapping (no re-cook)

SVT4 tiles carry a per-tile material-name table plus a per-vertex material index
(`mats` / `mat`), so the viewer resolves emission at load time:

1. `loadEmis()` fetches `emis.json` + `emis.bin`, builds the `DataTexture`, sets
   `uEmisOn = 1`.
2. `attachTileEmis(mesh)` walks the tile's material table, looks each name up, and writes
   `aEmis` (cell id, 0 = none, 255 = albedo sentinel), `aEs` (strength), `aEmisUv`
   (content rect) and `aEmisTint` (`emissiveFactor`).
3. Tiles already resident when the atlas arrives get the attributes retroactively; tiles
   built later get them at build time. A missing `aEmis` reads as 0 = no emission, so old
   tiles stay valid.

`attachTileEmis` also feeds the additive glow billboards (see "Reading at distance").

## Shader

```glsl
// vertex
attribute float aEmis; attribute float aEs; attribute vec4 aEmisUv; attribute vec3 aEmisTint;
varying float vEmis;  varying float vEs;  varying vec4 vEmisUv;  varying vec3 vEmisTint;
vEmis = aEmis; vEs = aEs; vEmisUv = aEmisUv; vEmisTint = aEmisTint;

// fragment, next to the baked-lamp term
if (uEmisOn > 0.5 && vEmis > 0.5) {
  vec3 eCol;
  if (vEmis > 200.0) {
    // self-emissive: the colour map is the emitter (cell 255 sentinel)
    eCol = clamp(texel.rgb * 2.0, 0.0, 1.0);
  } else {
    vec2 ec = vec2(mod(vEmis, 8.0), floor(vEmis / 8.0));
    vec2 eRel = (cellUv - vEmisUv.xy) / (vEmisUv.zw - vEmisUv.xy);  // into the content rect
    float eIn = step(0.0, eRel.x) * step(eRel.x, 1.0)
              * step(0.0, eRel.y) * step(eRel.y, 1.0);               // outside it: nothing
    eCol = texture2D(uEmis, (ec + clamp(eRel, 0.0, 1.0)) / vec2(8.0, 9.0)).rgb * eIn;
  }
  vec3 em = pow(eCol, vec3(2.2)) * vEmisTint * vEs * uEmisGain;
  totalEmissiveRadiance += em / (vec3(1.0) + em);
}
```

- **Not multiplied by `diffuseColor`.** Emission is independent of albedo — window glass is
  nearly black by day and still glows at night. The lamp-irradiance term *is* multiplied by
  albedo, which is why the same lux brightens a white road line but not asphalt.
- **`pow(eCol, 2.2)`** because the atlas is uploaded as RGBA8 while the rest of the shader
  works in linear space.
- **The `eIn` mask is not optional.** `cellUv` is whole-page UV; `eRel` is the same point
  inside the content rect. Skipping the mask stretches the crop over the entire surface —
  measured on `mat_shock_shingou`: mean frame luminance 27 → 39, bright pixels 80k → 152k.

## Corrected reading: the shared window sheet is authored, not a bug

Five materials (`building_window1`, `building_window8`, `building_window12`,
`building_window20`, `building_window23`) take their glow from
`lamp/building_internal_lights1.dds` — a different page from their 32×16 glass albedo. It
is tempting to call that a mismatch. It isn't:

- BeamNG's own definitions declare exactly that mapping for exactly those five materials,
  and the port's UE table carries the same paths. No other material references that sheet.
- The glass albedo is **32×16** and the glow sheet is **256×128**: the window detail is
  *designed* to live in the emissive sheet, and the albedo only carries the panel tint.
- Both maps sample the same UV channel — the definitions contain no scale/offset/tiling key
  of any kind, and the geometry's extra UV sets are dead. In all 66 building meshes that use
  `building_window*`, TEXCOORD sets 1–3 are entirely `0.000, 0.000` (exporter placeholders);
  UV0 is tiled, running outside 0..1 in 51 of the 66.

So the shared sheet, the tiling and the repetition are the mod's authored design — the AC
original (Shutoko Revival Project) used CSP UV2-baked emissive, and that second UV layout did
not survive the AC→BeamNG conversion.

## Day/night gating (not implemented in the viewer)

`levels/c1/mainlevel.lua` implements the mod's own switch: `getInstanceData()` collects every
material with `instanceEmissive = 1` (17 materials), stores each object's `instanceColor`,
sets it to `Black`; `enabledisableEmissionGlow(isEmissive)` restores the saved colours when
the level turns night on. The viewer adds emission in both looks, so windows glow in daylight
where the mod would not.

## Reading at distance

Emission alone does not make a night city read: it covers a small share of the frame and the
window sheets are sparse. Two additive passes were added on top of it:

- **Lamp sprites** — the 10,474 baked positions in `lights.json` (8,087 street, 1,148 tunnel,
  1,116 sign, 123 bridge), coloured by family, with a **screen-space size floor** (2.5 px) so
  a light stays visible from any overview distance. `PointsMaterial` sizes in world units and
  vanishes when zoomed out, hence the custom shader.
- **Emissive billboards** — one sprite per ~3 emissive vertices, tinted by `emissiveFactor`.

Knobs: `?lamps=0`, `?lampstrength=`, `?glow=0`, `?glowsize=`, `?glowstrength=`.

There is still **no bloom** and no HDR pipeline: BeamNG's night look leans on both, so this
is an approximation, not a match.

## Verifying it

```bash
# live counts without the console
chromium --headless=new --dump-dom \
  'https://www.aseanmotorclub.com/shuto-map/?emisdebug=1' | grep -o 'emissive:.*'
```

The page console prints `[emis] 183 emissive materials, 72 cells @ 256px` and
`[lamps] 10474 sprites` on a healthy load. The on-page overlay (bottom left, `?emisdebug=1`)
reports ON/FAILED, atlas size, tiles carrying `aEmis`, and emissive vertex counts.

A/B stills are only indicative: separate headless runs vary with tile streaming and camera
settling, so compare *structure* (`?emis=0` vs `?emis=3`) rather than exact pixel counts, and
judge the look in the real browser.

## Gotchas

- **The atlas URL must be versioned, not just query-busted.** `/map_tiles/shuto/` is served
  `immutable, max-age=31536000` behind Cloudflare, which pins the bare URL
  (`cf-cache-status: HIT`) — a republish at the same path is invisible. The atlas currently
  lives at `map_tiles/shuto/v10emis/`; bump that directory **and** the `?v=` query together.
- **Ship a `.br` twin.** The publish step brotles the atlas (18.9 MB → 3.9 MB) next to it;
  the location has `brotli_static on` for `application/octet-stream`.
- **`emis.json` and the shader are a matched pair.** The map is 9 fields
  `[cell, strength, u0, v0, u1, v1, fr, fg, fb]`; the shader assumes them, and the atlas
  grid is `8 x 9` in the sampler maths.
- **Re-run `mkemis.py` after any material change**, then bump `app.js?v=`, `emis.json?v=`
  and the atlas directory. Nothing else needs a rebuild — tiles are untouched.
- **Tiles are fetched as `<tile>.bin`, not `.svt`.** The publish step renames the extractor's
  `.svt` (and `.br` twin); renaming is also what makes `brotli_static` serve the compressed
  copy. Override tiles go to `v6f/` and are listed in `manifest.json` — never overwrite a
  cached `v6/` tile.
- **Never ship a flat emissive multiplier.** A uniform white 2.0 with no tone mapping blew the
  map out: the emissive region sat 3× above a ~20/255 night frame and 16.9% of emissive pixels
  exceeded luminance 200.
- **`EmissiveStrength` is a decoy** (1.0 everywhere in this content). If materials are ever
  re-imported, import `emissiveFactor` as a vector, not a scalar.
- **`?emis=0` disables the whole pass**, including the billboards' emissive source, and is the
  only honest A/B baseline.

## Limits / next steps

- No bloom, no tone mapping: the largest gap versus the mod, and the one thing that would make
  window light read as light rather than as a brighter wall.
- No day/night gate (see above). One condition on the dark look would match the mod's own
  behaviour.
- Self-emissive materials reuse the albedo texel, so their emission inherits the albedo atlas
  cell size (128 or 64 px for most) and the ±2 normalisation. Exactness would need their own
  cells.
- Cell aspect is square while sources are not (8:1 for `mat_denko_r_00`, 1:2 for
  `mat_mat_window3_glass_sh`). Aspect-preserving cells would require the same change in the
  albedo tiers, or the glow drifts relative to the base colour.
- Emissive cells are stored opaque, so a glow map can never clip itself by its own alpha; on
  `M_C1_Surface_Masked` materials the fragment still discards on the base-colour mask.
