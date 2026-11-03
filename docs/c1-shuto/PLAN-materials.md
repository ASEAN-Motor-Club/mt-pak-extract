# Plan — materials and textures for C1 (MVP project)

Status: **SOLVED for the opaque set (2026-11-03).** All surfaces went from checkerboard to
the C1 photographic textures by reparenting instances onto the game's masters. No authored
master is needed — that whole route is retired.

## Result

- `zzzz_AMC_C1Mats_P.pak` — 6,236,093 B, 3,218 entries — **retargeted=1609 masked=78
  opaque=1531 failed=0**.
- Opaque → `M_PropMaster`, masked → `M_PolygonMaster`.
- Verified in game: proper C1 textures render. They sample our texture assets through the
  game master's parameters, so the texture import/settings were never the problem.
- The vanilla master contributes shading only; the photographic content is ours.

Consequence: **stop authoring masters.** Our `M_C1_*` cooked masters carry no shader map
(`M_C1_Surface.uexp` 3,640 B vs `M_C1_Tex2.uexp` 17,289 B with shaders — and even the latter
rendered flat). The proven path is vanilla parens + our textures via parameter names.

## What exists today (measured 2026-11-03, `D:\UEProjects\C1`)

- `Content/Mods/C1/Materials` — 1,609 `MI_*` instances, 6 `M_*` masters
- `Content/Mods/C1/Textures` — 2,313 texture assets
- `Content/Mods/C1/Meshes` — 555 meshes (74 corridor cells in use)
- MVP pak stages 3,230 material files + 6,608 texture files and installs clean

So the pipeline already carries materials and textures. Nothing in the current pak needs
re-importing; what needs deciding is whether surfaces are textured, checkered, or flat, and
by which mechanism they fail.

## Step 0 — falsify before touching anything (1 build)

Make one master emit an unmistakable constant colour (magenta into BaseColor **and**
Emissive), cook, install, look.

- **Magenta appears** → the material renders; the fault is sampling (params/UVs) → Step 2.
- **Nothing changes** → the engine is substituting its default material; every graph/UV
  measurement describes an asset nothing draws → Step 1 immediately.

Cost: one build. Saves unbounded cycles in the wrong layer.

## Step 1 — shader-map reality check, then reparent

Ground truth is shader strings inside the cooked master's `.uexp`, not file size:

`strings <M_C1_*.uexp> | grep -cE 'VertexFactory|BasePass|FMaterialShaderMap|ShaderMap'`

- Reference mod's master: 23 matches. Our authored masters measured 0.
- An interactive editor session reporting `Shaders left to compile 0` is **not** evidence;
  `MaterialEditingLibrary.recompile_material` in a commandlet does not embed shaders either.
  Both routes are already measured failures — do not re-run them.

**Fix (confirmed previously):** reparent instances onto the game's own master.
`UAssetTool --retarget-mis <cooked>/Materials <out>` → `M_PropMaster`
(`BaseColor`, `Normal`, `Metallic`, `Roughness`, `Specular`, `Mask`, `Use_MaskTexture`,
`Use_NormalTexture`, `UV_Tiling`), packed as its own `zzzz_…_P.pak` that mounts *after* the
map pak. No re-cook needed for the instance reparent itself.

Param remap: `BaseColor→BaseColor`, `Normal→Normal`, `MetallicTex→Metallic`,
`RoughnessTex→Roughness`, `EmissiveTex`/`EmissiveStrength` → dropped.

Acceptance: in a dump, `Parent (Object): Index=-(N+1)` resolving to an import named
`M_PropMaster`, texture params renamed; in game, the asphalt look replaces the checker.

## Step 2 — texture correctness (only if Step 0 says "renders but samples wrong")

- DDS must be converted to PNG before import — UE rejects most of this corpus
  (`DDS DXGIFormat not supported : 71 : BC1_UNORM`). Measured 1,137/1,137 failed as DDS,
  1,137/1,137 imported as PNG. A batch that finishes in seconds reporting all-missing is this.
- sRGB **on** for base colour and emissive, **off** for normal/roughness/AO/metallic/opacity.
  Set after import on the loaded `Texture2D`, then re-save — factory options on an automated
  import task are not honoured.
- Compression BC7 colour, BC5 normal, BC4 mask; cap 1024 px for world surfaces, 2048 road only.
- Instance parameter names must equal the **target** master's names. Binding `'basecolor'`
  where the master declares `'BaseColor'` is silent and does nothing.

## Step 3 — inverted V (its own build)

**Measured 2026-11-03: the mirror is on U, not V.** With textures finally rendering, surfaces
read inverted *horizontally* and correct vertically — so the UV axis mapping to world Y is U
in this layout. Fix: `u = -u` on every `vt`.

Applied: `meshes_uflip/` written from the 74 corridor OBJs, **4,744,698 `vt` lines**
negated, reimported in place. Slot bindings survived the reimport (`replace_existing` with
unchanged `usemtl` names: c5_18 133/133 bound, c-2_12 107/107). New pak 229,486,767 B
(was 235,622,943).

Original note kept for reference: the OBJ import mirrors Y, so cancelling it with `y = -y`
restores position but leaves UV handedness mirrored. Which axis needs negating depends on
the UV layout — decide from the observed symptom (horizontal vs vertical), do not assume V.

**Second fault, same step:** the first reimport omitted `import_uniform_scale = 100.0`, so every
cell came back 100× too small ("geometry vanished — very far or very small"). The cell OBJs are
in metres; the importer converts to cm. Reimported with the scale block restored: bounds then
read `c0_14 min x -1264 … max 52713`, i.e. source ×100.

Because reimport re-applies the importer's Y mirror, the level frame is
`(x*100, -y*100, z*100)` and the previous translated-frame spawn became invalid. Spawn
recomputed from road spline point 102: `(169915, -692979, 84352)`, yaw `155.9`.
Pak 228,212,770 B.

- Fix in UV data, not materials: negate the mirrored axis — **U** for the C1 corridor (measured
  horizontal inversion), V for upside-down markings. Never `1 - u`/`1 - v` —
  ported UVs tile far past 0–1 (u measured up to 23,388), so `1 - v` shifts by a whole tile.
- Corpus scale for "complete": ~4.96M `vt` lines across the cells.
- This is a re-import → cook → pack cycle: ship it as its own build, separate from the
  material reparent, or a wrong frame cannot be attributed to one change.

## Step 4 — cutouts (glass, fences, light strips) — only after the opaque set renders

- No MT master samples a separate opacity map: the mask must be the **alpha of the base
  colour** bound to `BaseColor`, with `Use_OpacityFromAlpha` on the master (e.g.
  `M_PolygonMaster`) and `BasePropertyOverrides` → `BLEND_Masked` + clip on the instance.
- `M_DecalMaster` is not the answer: binding a mask to `BaseColor_A` made surfaces fully
  invisible. `M_Decal_Base`/`M_PlantMaster` declare `Opacity` as a **scalar** — binding a
  texture there does nothing. `M_Transparent` declares no parameters at all.
- Census before reparenting: of 60 instances carrying an `OpacityTex`, only 51 had a real
  binary `_o_data` cutout; the rest used colour/emissive as a pseudo-mask.

## Step 5 — verification gates

1. `UAssetTool --dump` a recooked cell: **zero** `WorldGridMaterial`, slot count equals that
   cell's `usemtl` count, slots point at the expected MI packages.
2. Slots assigned **by name**, never by index — an index-misordered list textures the world
   with wrong materials and still passes every non-visual check.
3. Dump the **installed** pak, not the build output; compare size/mtime on the client.
4. Night pass: road markings, window glass, tunnel strips — the ones that fail silently in
   daylight.
5. Record the measured pak delta and texture-pool size, not an estimate.

## Known traps, do not re-run

- `mesh:GetMaterial(i)` / `mi:GetMaterial()` return nil for everything in UE4SS — validate
  accessors against a vanilla asset before reporting "no materials at runtime".
- `get_num_uv_channels()` returning 0 was an API artefact; the meshes had 1 channel all along.
- `PKG_UnversionedProperties` absence is legitimate; shader platform SM5-only vs SM5+SM6 is
  dismissed — the working reference is SM5-only and ours ships both.
- `UAssetTool` resolves relative paths against the repo root — pass absolute paths.
- Cook-side measurement first: if the cooked master is already shader-less the cook is the
  fault; if it is large and the packed one small, the fault is staging.
