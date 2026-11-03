# Plan — materials and textures for C1 (MVP project)

Status: assets are already *imported*; the open question is whether they *render*. Treat
every step as unproven until it is measured, because this is the part of the port that
fails silently.

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

The mesh import mirrors Y, so cancelling it with `y = -y` restores position but leaves UVs
mirrored: markings, arrows and any text on horizontal surfaces read upside down, while tiled
noise (asphalt, concrete) looks fine and hides the bug.

- Fix in UV data, not materials: negate **V** (`v = -v`) on every `vt`. Never `1 - v` —
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
