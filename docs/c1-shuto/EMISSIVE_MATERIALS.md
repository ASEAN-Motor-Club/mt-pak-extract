# C1 Shuto — emissive materials

The ported C1 corridor ships **183 self-illuminated materials**. The viewer lights **92** of
them: window glass, street and tunnel lamps, sign boxes, signal heads, vending machines,
station signs and the Tokyo Tower glow. This is what the source says, which of it we trust,
how it is packed, and why three earlier attempts rendered the wrong picture.

Test surface: `https://www.aseanmotorclub.com/shuto-map/`
(`?emis=0` off, `?emis=<gain>` tunes, `?emisdebug=1` prints live counts, `?emat=` / click
a surface for its material).

## Authority: the BeamNG archive, not the UE material table

`/opt/data/inbox/c1src/c1_src.zip` is the BeamNG source (16 `*.materials.json`, 1,643
definitions, keyed by definition name and reached through `mapTo`). Each definition has up to
four `Stages`; stage 0 is the one that matters:

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
- **`emissive: true` with no `emissiveMap`** — the colour map is the emitter.
- **`emissiveFactor`** — HDR colour multiplier, 1.0 → 16.06, tinted per material. Brightness
  lives here; BeamNG has no scalar strength.
- **`sequenceSegmentSize`** (+ `animFlags 16`) — the sheet is a flipbook of 2–4 frames.
- **`instanceEmissive`** — the object's `instanceColor` gates the glow (see "Day/night gating").

`/opt/data/cache/scratch/c1/mod_full/materials_ue_v2.json` is the *ported* UE table (1,609
materials). Useful for base colour and masks; **not** the authority for emission.

## The UE conversion dropped the emissive flag for 126 materials

The port kept an `emissive` slot for only **57** materials while BeamNG declares **183**. The
126 missing ones are the per-material emitters — exactly what a viewer notices:

- **8 with a real `emissiveMap`** — `mat_daisi_window_etc`, `mat_daisi_all_komono`,
  `mat_daisi_komono_etc`, `mat_heiwajima_all_komono`, `mat_ooi_w_all_komono`,
  `mat_all_komono_00`, `mat_singou_d`, `mat_singou_d_depth`.
- **118 self-emissive** (`emissive: true`, no map) — `mat_u_window_sh`,
  `mat_windou2_siro8_sh`, `mat_window3_aka5_sh`, `mat_skg_hizyou_*`, every `sign_*`, the
  vending machines, station signs, `mat_kbj*` building lights.

Building the atlas from the UE table reproduced that loss faithfully: those surfaces were
never lit. `mkemis.py` reads the archive instead.

## Which of the 183 actually ship: 92

The 65 `emissiveMap` materials ship as-is. The 118 self-emissive ones do **not** all ship,
because `emissive: true` makes the *whole colour map* the emitter — and 91 of those colour
maps are bright (mean luminance up to 0.90). Making them emit turns entire facades into
lamps, which is what "the viewer is sampling textures it shouldn't" looked like. A material
is kept only if:

- its colour map is dark enough to be a light map (**mean ≤ 0.30**), or
- the artist gave it an explicit HDR tint (`emissiveFactor` max > 1.5).

That keeps 27 (`mat_u_window_sh`, `mat_window3_aka5_sh`, `mat_windou2_siro8_sh`,
`building_internal_lights1/2`, `building_black3/4`, `building_flash1`, `sign_60`,
`mat_RKJ_edo_u_llight01`, …) and drops 91 (e.g. `mat_Wab18_sh` mean 0.90,
`mat_kbm01_010` 0.81, `mat_kyuanbashi_br_light` 0.78).

| kind | count | how it is drawn |
|---|---|---|
| `emissiveMap` present | 65 | own rect in the packed atlas |
| `emissive: true`, dark map or HDR tint | 27 | **albedo sentinel**: reuses the albedo texel the shader already sampled |

The sentinel costs no atlas space and no extra fetch. Because albedo atlas cells are
mean-normalised (stored at 0.5× and doubled in the shader), the emissive branch compensates
with `clamp(texel.rgb * 2.0, 0.0, 1.0)`.

Textures the conversion never extracted — the `mat_daisi_*` and `mat_singou_*` sheets — are
read straight out of `c1_src.zip` with PIL, which handles DDS (BC1/BC2/BC3) and PNG alike.
BeamNG capitalises suffixes (`_file0EM.dds`) while the archive stores lowercase, so the
lookup is case-insensitive.

Excluded on purpose: `emissiveFactor` parked at `1e-06` (BeamNG's "this is dead" value, e.g.
`lamp1_tunnel`) and definitions that were never ported (`godray_emitter`, `thunderbolt`).

## Intensity: `emissiveFactor`, not `EmissiveStrength`

`scalars.EmissiveStrength` in the UE table is `1.0` on every material — a decoy. The real
per-material data never left the archive:

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
largest glass page hardest while flattening the tower and the signals the source tints hard.
The shader applies `emissiveFactor` per material and Reinhard-compresses (`em / (1 + em)`) so
hue and relative intensity survive without flat-lining the building behind it.
`emisGainUniform` (default 1.2) is the overall level.

## Atlas: a packed rect atlas, not a cell grid

```
site/emis.png   4096x4096 RGBA8, 2.8 MB — sheets packed at (capped) native resolution
site/emis.json  {"size":[4096,4096],
                 "mats":{material:[ax0,ay0,ax1,ay1, su0,sv0,su1,sv1, fr,fg,fb]}}
                ax/ay = rect in atlas PIXELS (top-left origin)
                su/sv = rect inside the source page, normalised
                fr/fg/fb = BeamNG emissiveFactor (HDR tint)
                a negative ax marks the albedo sentinel (no atlas rect)
```

Three decisions, each one a bug fix:

- **Packed rects, not a uniform grid.** Source sheets span **16×32 to 1024×2048**; a fixed
  256 px cell grid cannot hold that range. `mat_mat_window3_glass_sh` (the biggest glass
  surface in the map) was being crushed 4:1 *and* squashed 2:1, while
  `mat_PA_tatsumi_parts` (13×13 content) was blown up 19.7×. Each material now carries its own
  rect and one source texel maps to one atlas texel.
- **Native resolution, capped at 1024 px** long side. No material is magnified; the two
  largest sheets (`mat_mat_window3_glass_sh` 1024×2048 → 512×1024) lose a uniform 0.5.
- **No content crop.** The first atlas cropped each sheet to its lit content box and stretched
  that crop over one UV unit. That changes the pattern's **scale and phase** relative to
  `texture2D(emissiveMap, uv)`: `building_internal_lights1` keeps its lit band at
  u 0.246–0.816 / v 0.305–0.672, and stretching that band to 0..1 magnified it 1.6× and
  shifted it, so facades showed a different slice of the sheet than the UV asks for. Rects are
  now `0,0 → 1,1` for 61 of 65 materials; the other 4 are flipbook frame-0 slices
  (`mat_denko_r_00`, `mat_kan_p1_00_sh`, `mat_shock_shingou`, `mat_singou_e`), which the
  engine also offsets.

Other invariants:

- **Not mean-normalised.** Emission is an absolute colour that gets *added*, not a multiplier
  on vertex colour. Copying the albedo path's `/mean` would shift every colour.
- **Textures whose brightest channel is below 8** are dropped as effectively black.
- **Verified against the source**: all 65 atlas rects correlate ≥ 0.98 with their source pages
  at the stated rects, so the packing is faithful and no rect overlaps a neighbour.

## Per-vertex mapping (no re-cook)

SVT4 tiles carry a per-tile material-name table plus a per-vertex material index
(`mats` / `mat`), so the viewer resolves emission at load time:

1. `loadEmis()` fetches `emis.json` + `emis.png`, uploads the texture, sets `uEmisOn = 1`.
2. `attachTileEmis(mesh)` walks the tile's material table and writes `aEmis` (1 = emissive,
   −1 = albedo sentinel), `aEs`, `aEmisUv` (source rect), `aEmisAtl` (atlas rect in px) and
   `aEmisTint` (`emissiveFactor`).
3. Tiles already resident get the attributes retroactively; later tiles get them at build
   time. A missing `aEmis` reads as 0 = no emission, so old tiles stay valid.

`attachTileEmis` also feeds the additive glow billboards (see "Reading at distance").

## Shader

```glsl
// vertex
attribute float aEmis; attribute float aEs; attribute vec4 aEmisUv;
attribute vec4 aEmisAtl; attribute vec3 aEmisTint;
varying float vEmis; varying float vEs; varying vec4 vEmisUv;
varying vec4 vEmisAtl; varying vec3 vEmisTint;

// fragment, next to the baked-lamp term
if (uEmisOn > 0.5 && vEmis > 0.5) {
  vec3 eCol;
  if (vEmis < -0.5) {
    eCol = clamp(texel.rgb * 2.0, 0.0, 1.0);          // albedo sentinel
  } else {
    vec2 eRel = (cellUv - vEmisUv.xy) / (vEmisUv.zw - vEmisUv.xy);
    float eIn = step(0.0, eRel.x) * step(eRel.x, 1.0)
              * step(0.0, eRel.y) * step(eRel.y, 1.0);
    vec2 apx = vEmisAtl.xy + clamp(eRel, 0.0, 1.0) * (vEmisAtl.zw - vEmisAtl.xy);
    eCol = texture2D(uEmis, apx / uEmisSize).rgb * eIn;   // rect is in atlas pixels
  }
  vec3 em = pow(eCol, vec3(2.2)) * vEmisTint * vEs * uEmisGain;
  totalEmissiveRadiance += em / (vec3(1.0) + em);
}
```

- **Not multiplied by `diffuseColor`.** Emission is independent of albedo — window glass is
  nearly black by day and still glows at night. The lamp-irradiance term *is* multiplied by
  albedo, which is why the same lux brightens a white road line but not asphalt.
- **`pow(eCol, 2.2)`** because the atlas is RGBA8 while the rest of the shader works in linear
  space.
- **`eIn` is a no-op for full-page rects** and only matters for the flipbook slices; it is kept
  so a future cropped rect cannot smear the sheet across a whole surface (measured on
  `mat_shock_shingou` before it existed: mean frame luminance 27 → 39, bright pixels 80k →
  152k).
- **`uEmisSize` is in pixels**, so a rect can be stored in atlas pixels with no normalisation
  step in the data pipeline.

## Corrected reading: the shared window sheet is authored, not a bug

Five materials (`building_window1`, `building_window8`, `building_window12`,
`building_window20`, `building_window23`) take their glow from
`lamp/building_internal_lights1.dds` — a different page from their 32×16 glass albedo.
That is authored, not a mismatch:

- BeamNG's own definitions declare exactly that mapping for exactly those five, and no other
  material references that sheet.
- The glass albedo is **32×16** and the glow sheet **256×128**: in this map the light detail
  lives in the emissive sheet, the albedo only carries panel tint.
- Both maps sample the same UV channel — the definitions contain no scale/offset/tiling key of
  any kind. In all 66 building meshes using `building_window*`, TEXCOORD sets 1–3 are entirely
  `0.000, 0.000` (exporter placeholders) and UV0 is tiled, running outside 0..1 in 51 of 66.

The sheet itself is a **146×47 band of window light inside a 256×128 page**, with no pane
grid: at threshold 0.45 it is three blobs, and above 0.75 nothing. So the honest limit is that
window glow here is a tiled strip of light, authored to be read at speed at night — it does
not resolve pane-by-pane at close range, and no rect arithmetic can change that. The AC
original (Shutoko Revival Project) used CSP UV2-baked emissive; that second UV layout did not
survive the AC→BeamNG conversion.

## Day/night gating (not implemented in the viewer)

`levels/c1/mainlevel.lua` implements the mod's own switch: `getInstanceData()` collects every
material with `instanceEmissive = 1` (17 materials), stores each object's `instanceColor`, sets
it to `Black`; `enabledisableEmissionGlow(isEmissive)` restores the saved colours when the
level turns night on. The viewer adds emission in both looks, so windows glow in daylight where
the mod would not. The same flag means BeamNG lights a *different fraction* of each building
instance; we light every instance identically.

## Reading at distance

Emission alone does not make a night city read: the window sheets are sparse and cover a small
share of the frame. Two additive passes sit on top:

- **Lamp sprites** — the 10,474 baked positions in `lights.json` (8,087 street, 1,148 tunnel,
  1,116 sign, 123 bridge), coloured by family, with a **screen-space size floor** (2.5 px) so a
  light stays visible from any overview distance. `PointsMaterial` sizes in world units and
  vanishes when zoomed out, hence the custom shader.
- **Emissive billboards** — one sprite per ~3 emissive vertices, tinted by `emissiveFactor`.

Knobs: `?lamps=0`, `?lampstrength=`, `?glow=0`, `?glowsize=`, `?glowstrength=`.

There is still **no bloom** and no HDR pipeline: BeamNG's night look leans on both, so this is
an approximation, not a match.

## Verifying it

```bash
# live counts without the console
chromium --headless=new --dump-dom \
  'https://www.aseanmotorclub.com/shuto-map/?emisdebug=1' | grep -o 'emissive:.*'
```

A healthy load prints `[emis] 92 emissive materials, atlas 4096x4096 (packed rects, native
scale)` and `[lamps] 10474 sprites`, with **0 shader errors**. The overlay (bottom left,
`?emisdebug=1`) reports ON/FAILED, atlas size, tiles carrying `aEmis`, and emissive vertex
counts. A shader compile error still leaves the overlay reading ON — always grep the console
for `Shader Error` after touching the shader.

**Do not use screenshots as evidence for shading.** Two headless loads of the same URL differ
by ~28% of pixels and ~1 luminance unit, because tile streaming and camera settling are not
deterministic at a fixed virtual-time budget. Earlier "A/B" numbers in this document were
measuring that noise.

## Gotchas

- **A stale origin-wide service worker can fake every symptom.** The main site once shipped a
  service worker at scope `/`; `/sw.js` now returns the SPA fallback (8,084 B), so an installed
  copy can never update and its fetch handler throws `A ServiceWorker intercepted the request
  and encountered an unexpected error` on large assets. Symptoms: atlas/tiles failing
  *intermittently*, `[emis] FAILED to load: DOMException: The operation was aborted`, while a
  fresh browser profile works. `app.js` unregisters stale registrations once per session and
  reloads.
- **Atlas fetches retry.** `fetchRetry()` does 3 attempts with 600/2400/5400 ms backoff; one
  aborted request used to disable emissive for the whole session.
- **The atlas URL must be versioned, not just query-busted.** `/map_tiles/shuto/` is served
  `immutable, max-age=31536000` behind Cloudflare, which pins the bare URL
  (`cf-cache-status: HIT`) — a republish at the same path is invisible. The atlas lives at
  `map_tiles/shuto/v13emis/`; bump that directory **and** the `?v=` query together.
- **`emis.json` and the shader are a matched pair.** 11 fields per material
  `[ax0,ay0,ax1,ay1, su0,sv0,su1,sv1, fr,fg,fb]`; a negative `ax0` means sentinel. Adding a
  field means touching `emisAttributes()` and the shader together.
- **Re-run `mkemis.py` after any material change**, then bump `app.js?v=`, `emis.json?v=` and
  the atlas directory. Tiles are untouched, so nothing else needs a rebuild.
- **Tiles are fetched as `<tile>.bin`, not `.svt`.** The publish step renames the extractor's
  `.svt` (and `.br` twin); renaming is also what makes `brotli_static` serve the compressed
  copy. Override tiles go to `v6f/` and are listed in `manifest.json` — never overwrite a
  cached `v6/` tile.
- **Never ship a flat emissive multiplier.** A uniform white 2.0 with no tone mapping blew the
  map out: the emissive region sat 3× above a ~20/255 night frame and 16.9% of emissive pixels
  exceeded luminance 200.
- **`EmissiveStrength` is a decoy** (1.0 everywhere). If materials are ever re-imported, import
  `emissiveFactor` as a vector, not a scalar.
- **`?emis=0` disables the whole pass**, including the billboards' emissive source, and is the
  only honest A/B baseline.
- **4096×4096 is the atlas ceiling.** It is a common `MAX_TEXTURE_SIZE` floor; going bigger
  needs a tiled load, not just a larger pack.

## Limits / next steps

- No bloom, no tone mapping: the largest gap versus the mod, and the one thing that would make
  window light read as light rather than as a brighter wall.
- No day/night gate and no per-instance variation (see above). One condition on the dark look
  plus a per-instance hash would match the mod's own behaviour.
- Self-emissive materials reuse the albedo texel, so their emission inherits the albedo atlas
  cell size and the ±2 normalisation. Exactness would need their own rects.
- The shared window strip cannot line up with window frames — the source has no pane-level
  emissive. Pane-accurate windows would have to be generated (per-pane mask from geometry,
  tinted by `emissiveFactor`) rather than sampled.
- Emissive rects are stored opaque, so a glow map can never clip itself by its own alpha; on
  `M_C1_Surface_Masked` materials the fragment still discards on the base-colour mask.
