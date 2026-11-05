# Materials, Alpha and Blending — what actually works in Motor Town

Written after seven failed material paks (A–F) on the C1 port. Every rule here is backed
by an in-game observation, not by reasoning about how Unreal "should" behave. Read this
before touching materials, cutouts, or road markings again.

The failure mode this document exists to prevent: rebuilding the same material pak over and
over with a different guess each time, while the actual defect (a parameter name, a parent
master, or a texture with no alpha channel) never changes.

---

## 0. The canonical model (web research, 2026-11-05)

Everything below in §1+ was learned the hard way. This section is the same knowledge stated the
way Unreal documents it, with sources, because the engine's own rules explain every failure we hit
and predict the ones we had not hit yet.

**Material instancing exists to change appearance without recompiling the shader.** Epic:
*"Material instancing in Unreal Engine is used to change the appearance of a Material without
incurring an expensive recompilation of the Material… a parameterized Material can be edited in a
Material instance without such recompilation."* — Instanced Materials, Epic docs
(`dev.epicgames.com/documentation/en-us/unreal-engine/instanced-materials-in-unreal-engine`).
The inverse is the important half: **anything that is not a parameter is compiled state.**

**Blend mode, shading model, two-sided and mask-clip are base-property overrides**, i.e. a separate
struct from parameters (`unreal.MaterialInstanceBasePropertyOverrides`, Epic Python API). They
change the compiled permutation. When the engine cannot find that permutation it says so, verbatim:

> `Couldn't find Shader TShadowDepthVSVertexShadowDepth_OutputDepthfalse for Material Resource
> BaseMaterial! … BlendMode=BLEND_Masked … Masked=1`

— Epic issue **UE-39754**. That is a *missing cooked shader permutation*, and it is reached simply by
overriding blend mode on an instance. In the editor the shader is compiled on demand so the override
appears to work; **in a cooked game it can silently fail or crash the material lookup.**

Consequence for modding a cooked game — this is the rule we should have followed from pak A:

1. **A mod pak cannot add a shader permutation.** Never rely on a blend-mode override to create a
   rendering mode the parent was not cooked with. Pick a parent that already has the blend you want.
2. **Override parameters only** — textures and scalars the parent declares. That is the one thing
   instancing guarantees is free of compilation.
3. Therefore: opaque things get an opaque parent, cutouts get a parent that is *already*
   `BLEND_Masked`, translucency gets a parent that is *already* translucent. The parent is the
   blend mode; the instance is only the appearance.

**Masked rendering is thresholded, not faded.** Epic: *"If BlendMode is BLEND_Masked, the surface is
not rendered where OpacityMask < OpacityMaskClipValue"*, and the default clip value is **0.3333**
(`MaterialInstanceBasePropertyOverrides.opacity_mask_clip_value`). A masked material with no
texture-driven Opacity Mask never discards anything, whatever the texture contains.

**Alpha has to survive compression.** BC1/DXT1 has **no explicit alpha channel** — only a 1-bit
encoding trick that Unreal's BC1 setting does not use, so a mask stored there reads as fully opaque
(the "black background" symptom). Use BC3/DXT5 or BC7 for anything that must cut.

**What this means for our port, concretely:**

- Foliage cutouts → parent `M_AlphaTest` (**already** `BLEND_Masked`, TwoSided, parameter `Color`).
  Set `Color` to a BC3/BC7 texture whose alpha carries the mask. **Do not** add a blend override:
  the parent already is the blend mode, and an override is precisely the thing that fails in a
  cooked game.
- Opaque → `M_PropMaster` / `M_PolygonMaster` / the author's `M_C1_Surface*`, no override.
- Translucent markings → the author's **`M_C1_Surface_Trans`** (the fourth master, present in the
  release and missed by our audit), not translucency forced onto an opaque master. Forcing it is
  what turned the markings white.
- A custom master in a mod pak is still the real shader-map wall (§3): its permutation is not in the
  game's shader library. Parent choice is the only lever we have.

Sources: Epic Instanced Materials docs; `unreal.MaterialInstanceBasePropertyOverrides` (5.8);
Epic issue UE-39754; Epic forum "Using Material Property Overrides causes cooking failures";
UE community threads on DXT1 1-bit alpha.

---

## 1. The model

Motor Town's own masters are the only materials that can render. A cooked `Material` from a
mod pak carries no shader graph — the game's shader maps are baked into its own library and a
mod pak cannot extend them. A custom master cooks to ~3.6 KB with zero shader data and
renders as the default-material checkerboard.

So the port has exactly three usable targets, plus the translucent one:

- `M_PropMaster` — opaque, full PBR. Parameters: `BaseColor`, `Normal`, `Roughness`,
  `Metallic`, `Specular`, `Mask`, `Use_MaskTexture`, `UV_Tiling`. **Never routes alpha.**
- `M_PolygonMaster` — opaque, no `BlendMode`. **Never routes alpha**; masked instances there
  clip to black.
- `M_plants` (Stylized_Forest) — cuts cutouts from **`BaseColor` alpha**. This is the only
  master that produces a real alpha cutout.
- `M_GlassTrans` — the translucent target for surfaces that must blend rather than cut.

There is **no master in Motor Town that samples a separate opacity texture**. The author's
`M_C1_Surface_Masked` reads a dedicated `OpacityTex` parameter, but that design cannot be
reproduced with a vanilla master — the mask has to be moved into `BaseColor`'s alpha channel.

### The author's ground truth (what we are porting *from*)

Extracted from the original pak, not inferred:

- `M_C1_Surface` — 1,381 instances, opaque, scalar Metallic/Roughness, `EmissiveTex`,
  `EmissiveStrength`, `TwoSided`.
- `M_C1_Surface_Tex` — 150 instances, opaque, full PBR with `MetallicTex`/`RoughnessTex` as
  textures. The road markings live here.
- `M_C1_Surface_Masked` — 93 instances, `BLEND_Masked`, alpha from a separate `OpacityTex`.
- **Zero translucent materials.** Any routing that produces translucent instances is a
  deviation from the source, and needs a reason.

---

## 2. The five rules

1. **Never ship a custom or author master.** It renders checkerboard. Reparent to a vanilla
   master and move the data into that master's parameters.
2. **Reparenting changes the parent, not the parameter names.** If the old master called it
   `Color` and the new one calls it `BaseColor`, the binding is dead after the switch. The
   instance then renders the master default — which reads as a **black background** on a
   cutout. Always audit parameter names after a reparent.
3. **Blend mode is per instance, not inherited.** `Parent` alone does not change how the
   material is rasterised; the master ships opaque. A masked instance needs its own
   `BlendMode = BLEND_Masked` (+ `TwoSided`, + clip ~0.3333).
4. **Masking only works if the texture has an alpha channel.** A BC1/DXT1 texture decodes
   alpha as 255 everywhere: the clip never fires and the sheet's RGB background shows. Check
   the format *and* measure the alpha before believing masking will do anything.
5. **An opaque texture cannot be blended by a flag.** If a marking texture is 100% opaque
   (`t = 0.0`), setting `BLEND_Translucent` blends nothing — you get a white sheet. The alpha
   has to exist in the texture.

---

## 3. The attempt ledger

Every pak we shipped, why it failed, and what it proved. This is the part that stops the
looping.

- **A — author masters verbatim.** 1,624 instances repointed to `M_C1_Surface*`, masters
  shipped at their original path. Result: *"no textures are loaded, all checkerboard"*.
  Proved rule 1 the hard way — a cooked master without its shader map cannot compile.
  Permanently dead end.
- **B — vanilla masters, correct groups.** 1,381 → `M_PropMaster`, 150 → `M_PolygonMaster`,
  93 → `M_plants`. Result: *"everything opaque, proper uv, no checkerboard, but also no
  transparency in the trees and no blending for the road markings"*. Proved textures and UVs
  were fine; only alpha behaviour was missing. Proved rule 3.
- **C — per-instance `BLEND_Masked` on the 93 author-masked instances.** Result: *"still
  solid"*, markings *"clip"* when walked over. Measurement showed why: of the 93, **61 had a
  BaseColor texture with zero alpha, 28 had no BaseColor at all, 1 had usable alpha**. The
  flag was right; there was nothing to cut with. Proved rule 4.
- **D — alpha baked from `OpacityTex` into `BaseColor`.** 77 textures composed and re-encoded,
  masked instances pointed at them. Result: no visible change. **Cause: wrong targets.** The
  77 instances we picked turned out to be lamps, tunnel fittings and signage — selected by
  texture-alpha statistics, which grouped them with foliage. Proved that alpha statistics
  alone are not a valid way to choose what to fix.
- **E — 178 further instances masked + constant alpha baked into the three marking textures.**
  Result: *"still the same"*. Two things were true at once: the foliage we needed was on a
  master whose parameter name didn't match, and the markings were the opposite problem.
- **F — parameter rename on the `M_AlphaTest` lineage.** 25 instances had been authored
  against `M_AlphaTest` (colour parameter `Color`), reparented to `M_plants` (expects
  `BaseColor`) — the binding was dead, so they rendered the master default: **black
  background**. Renaming `Color` → `BaseColor` on exactly those 25 was the fix. Proved rule 2,
  and proved that "black background" is a *binding* symptom, not a blend symptom.

The pattern to notice: A–E were all arguments about blending. The actual defects were a dead
parameter binding and textures with no alpha. Blending was never the problem.

---

## 4. Diagnosis procedure — follow it in order

Do these in sequence and stop at the first hit. Do not skip ahead to blend flags.

1. **Identify the instance.** A coordinate plus a screenshot beats any amount of statistics.
   From the coordinate, get the cell, then the mesh, then the material slot. Name the MI
   before changing anything.
2. **Read the instance's live parent.** `--dump` and look at the `Parent` object property's
   `Index`. The name map may contain several stale master imports; only the `Parent` index
   tells you what is actually used. (Both `M_AlphaTest` and `M_plants` appear in the import
   list of a healthy instance — the stale one is a decoy.)
3. **List the instance's texture parameters and compare against the parent's parameter
   names.** Mismatch → rule 2. This is the most common cause of a black background and it
   looks identical to a broken blend.
4. **Check the texture format and measure alpha.** Format without alpha (BC1/DXT1) →
   masking cannot work. Alpha present but `t = 0` → the mask lives elsewhere (the author's
   `OpacityTex`); bake it in.
5. **Only now consider the blend mode.** Opaque sheet that must blend → translucent + alpha
   in the texture. Cutout that must discard → masked + alpha in the texture.

### Symptom → cause table

- **Checkerboard everywhere** → a custom/author master is being referenced (rule 1).
- **Flat colour, no texture** → the parameter name does not match the parent's parameter, or
  no texture is bound at all.
- **Black background around foliage** → masked/opaque material whose texture alpha reads 255,
  *or* a dead parameter binding showing the master default. Distinguish with step 3.
- **White sheet instead of road paint** → opaque marking texture; blending has nothing to
  work with (rule 5).
- **Marking clips / punches through when walked over** → masked material writes depth.
  Translucent does not.
- **Some trees correct, others not** → they are on different parents, or carry different
  parameter names. Diff two instances rather than guessing at the group.

---

## 5. Tooling

All of these are in `mt-pak-extract` (C# `UAssetTool`) unless stated otherwise.

- `--set-mi-parent <in> <out> <list> <masterPkg> <masterName>` — set `Parent` only. Does not
  touch parameters or blend. Follow with a parameter audit.
- `--rename-texture-param <in> <out> <from> <to>` — rename a texture parameter across a
  material directory. This is the fix for rule 2. It scans every file and changes only the
  ones that have the parameter.
- `--set-blend <in> <out> <list> <masked|translucent> [Scalar=Value ...]` — per-instance
  `BlendMode` + `TwoSided` + clip, optionally with scalar overrides.
- `--set-texparam <in> <out> <list|-> <param> <texPkg> <texName>` — repoint one texture
  parameter. The list accepts `MI<TAB>textureName` lines so one pass can give each instance
  its own texture.
- `build_matspak.sh <mats-dir> <out.pak> [extra-content-dir]` — material-only pak. Gates out
  `ShaderArchive` and non-material content.

### Rules for the tools themselves

- **Never drop an instance from the output.** A failed patch must still copy the original
  through. Dropping it removes the material entirely and the mesh falls back to the engine
  default — which looks like a new, different bug. This bit us once: nine materials vanished
  silently and the run still reported success.
- **Assert the counts.** Materials out must equal materials in.
- **Verify on the asset, not on the exit code.** Dump the patched instance and read the
  parameter name, the parent index and the blend mode before packaging.

---

## 6. Textures without cooking

The editor cook does **not** emit `/Game/Mods/C1/**` or `/Game/Mods/C1Full/Textures/**` — it
only produces `Maps`, `Materials` and `Meshes`. `-cookdir=` is ignored and a full content cook
emits nothing either. Do not plan a texture fix around the cook.

What works instead: patch the **cooked** texture in place.

- Decode level 0 from the `.ubulk` (`texture2ddecoder` / `etcpak`), composite the alpha you
  want, re-encode in the **same** format, and write it back. Same format means the same byte
  count, so the `.ubulk` can be overwritten without touching any headers.
- Level 0 only is acceptable: lower mips only affect distant LODs and RGB is unchanged.
- Ship `uasset` + `uexp` + `ubulk` under the **original** asset path in the material pak, so
  every instance that references it picks up the new alpha with no repoint at all.

This is why the alpha bake never needs a recook, and why moving textures to a new namespace
was unnecessary work.

---

## 7. Pak layering

- `zzzz_AMC_C1Test_P.pak` — geometry, level, meshes. Never rebuilt for material work.
- `zzzzz_AMC_C1Mats_P.pak` — materials and material textures. Mounts later (higher
  `zzzzz`), so it wins. Iteration is seconds: build, push, install, restart the game.

Install path: `D:\SteamLibrary\steamapps\common\Motor Town\MotorTown\Content\Paks\`.
`install_mats.ps1 -Src <pak>` verifies `MATS_SHA_MATCH`; "being used by another process"
means the game is running.

---

## 8. Standing warnings

- Never ship `ShaderArchive-*` in a mod pak — it crashes the game (`GlobalShader.cpp:803`).
  `build_matspak.sh` gates this, check it stays gated.
- Do not re-import meshes to fix a material problem. Re-importing is for placement and UVs.
- Do not select fix targets by texture statistics alone (attempt D). Name the instance first.
- Do not conclude "blending is broken" from a screenshot. Read the instance: parent, parameter
  names, texture format, alpha. The blend flag is the last thing to check, not the first.
