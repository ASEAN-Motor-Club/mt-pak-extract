# PLAN — alpha / cutouts (trees, fences, wires, signs)

Status: measured, not yet implemented. 2026-11-03.

## Symptom

Vegetation and other cutout geometry renders with a **black background** where the texture is
transparent, instead of being clipped.

## Measured evidence (all from data, not guesswork)

1. **Alpha exists in the source.** e.g. `area_zz_01.gtf_tex_020.dds` — 1024x256, **DXT5** (BC3,
   carries alpha), 11 mips.
2. **Alpha survives the PNG conversion.** `textures_png/other/area_zz_01.gtf_tex_020.png` is
   `colortype 6` (RGBA8).
3. **413 of 1,447 colour-bearing materials actually have transparent pixels** (>=2% of pixels
   with alpha <128), measured by decoding every colour texture:

   | master | count |
   |---|---|
   | M_C1_Default | 282 |
   | M_C1_Emissive | 98 |
   | M_C1_Building | 11 |
   | M_C1_Metal | 11 |
   | M_C1_Glass | 10 |
   | M_C1_Surface | 1 |

   Includes `mat_bush_*` (0.84 transparent), `fence1`/`mat_fence_b` (0.83), `wire1` (0.90),
   `lamp2`/`lamp4` (0.84-0.86), `mat_name_tamakawa_tnl` (0.83).
4. **Textures import at `TC_DEFAULT`** and `sRGB=True`. Default compression is not guaranteed to
   keep alpha, so even a masked material could sample a dead alpha channel.
5. **Runtime instances point at the opaque master.** `UAssetTool --dump mats_out/MI_C1_mat_bush_03a`:
   `Parent (Object): Index=-9` = `M_PropMaster`. Opaque masters discard alpha, so transparent
   texels render as their RGB — black.

Root cause: the retarget sweep routed only the 78 `M_C1_Glass` materials to a masked master.
Everything else, including all 413 with real cutouts, went to opaque `M_PropMaster`.

## Fix

### Step 1 — texture side
- For the **413 colour maps that carry a cutout**, set `compression_settings = TC_BC7` and keep
  `sRGB = True`. BC7 preserves alpha; TC_Default may not.
- Leave the other ~1,034 colour maps alone (no alpha, no reason to pay BC7 cost).
- Verify: `compression_no_alpha == False` and alpha is present after recook for a sample.

### Step 2 — instance side
- Reparent the 413 MIs to **`M_PolygonMaster`** (documented `Use_OpacityFromAlpha` — the cutout
  switch MT's own art masters use). Never author a master: our own masters cook without shader
  maps and render the checker.
- On each of those MIs set `BasePropertyOverrides`:
  `blend_mode = BLEND_Masked`, `opacity_mask_clip_value = 0.333`, and preserve existing
  `two_sided`.
- Do **not** touch `M_Decal_Base` / `M_PlantMaster` / `M_Transparent`: they declare `Opacity` as a
  **scalar** (binding a texture does nothing) or declare no parameters at all.

### Step 3 — one cell first
- Apply to `c3_13` (spawn cell) only, rebuild the zzzz override pak, verify in game at the
  spawn: bushes, fences and signage should cut out cleanly and the trees should lose the black
  box.
- Only then sweep all 74 cells.

### Step 4 — verification gates
1. Dump >=3 cooked MIs: parent must be `M_PolygonMaster`, `BlendMode=BLEND_Masked`, clip 0.333.
2. Count masked MIs in the built pak == 413 (+ the 78 glass already masked, minus any overlap).
3. Dump the **installed** pak, not the build output.
4. Night pass: lamp strips, shop signs, window glow — these fail silently in daylight.
5. Record the measured pak delta, not an estimate.

## Risks

- **Alpha used for something other than cutout.** A texture can carry alpha for non-cutout
  reasons. Mitigation: the 2% threshold plus a manual spot check of the top offenders (wire1,
  fence1, mat_saku_08_02) before sweeping.
- **Emissive windows (98)** may have alpha used as a glow mask rather than a cutout. Masking them
  could punch holes in lit windows. Mitigation: split the sweep — bushes/fences/wires/signs first,
  emissive separately after a visual check.
- **`M_PolygonMaster` shared with 78 glass instances.** Confirm on `c3_13` that glass still looks
  right before the full sweep.
- Collision is unaffected (complex-as-simple uses render triangles), but masked surfaces will now
  visually clip where collision still exists — expected, matches the source mod.
