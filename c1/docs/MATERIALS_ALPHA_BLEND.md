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

### Master contracts, read out of the shipped masters (not guessed)

Dumped from `client-0.7.19.pak`. These are the *actual* parameter names each master declares —
the only names an instance may legally bind.

- **`/Game/Models/Stylized_Forest/Materials/plants/M_plants`** — **the master the port's own tree and
  bush instances actually use, and the one that renders correctly.** `BLEND_Masked`, TwoSided,
  `MSM_Subsurface`, dithered LOD, instanced-static-mesh support; samples `T_plants_basecolor` and
  `T_plants_normal`. Parameters include **`BaseColor`**, `opacity`, `roughness`, `specular`,
  `SS_color`, `HueShift`, `Color_Map`, `Normal_Map`, `GrassBendingDistance`, `AO`, `Power`.
  Do not confuse it with the similarly named AssetsvilleTown master below — they take *different*
  parameter names and swapping between them is a rewrite, not a fix.
- **`/Game/AssetsvilleTown/Materials/MasterMaterials/M_Plants`** — a *second*, different foliage master.
  `BLEND_Masked`, TwoSided, `MSM_Subsurface`, `DitheredLODTransition`,
  `bUsedWithInstancedStaticMeshes`, grass-wind via `SimpleGrassWind`, default texture `T_leaf_01`.
  Parameters: **`Base_Color`** (texture), `Base_Color_Tint`, `Roughness`, `SubSurface_Color`,
  `SubSurface_Power`, `WindPower`.
  → This is the master for trees, bushes and grass. Note the underscore in `Base_Color`.
- **`/Game/AssetsvilleTown2/Materials/MasterMaterials/M_AlphaTest`** — a generic masked master used
  for fences and metal. `BLEND_Masked`, TwoSided, default texture `T_fenceMetal_01`.
  Parameters: `Color`, `Roughness`.
  → It will cut a texture correctly, but it shades like metal. Putting foliage on it produces
  **correct cutout, wrong appearance** — which reads as "these are no longer trees".
- **`/Game/Mods/C1/Materials/M_C1_Surface*`** — the author's own masters (opaque, opaque-PBR,
  masked, and `M_C1_Surface_Trans` for translucency).
- **`M_PropMaster` / `M_PolygonMaster`** — opaque. They declare `Use_Opacity` /
  `Use_OpacityFromAlpha` scalars, and setting those to 1 does **not** turn a foliage billboard into
  a cutout: the bounding rectangle still paints its texture's backdrop, which is black on these
  atlases. Do not route foliage here.

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
- `M_Plants` (`/Game/AssetsvilleTown/Materials/MasterMaterials/M_Plants`) — the foliage master:
  `BLEND_Masked`, TwoSided, `MSM_Subsurface`, dithered LOD, grass wind. Cuts from its colour
  texture's alpha. **Its colour parameter is `Base_Color`, with an underscore** — binding
  `BaseColor` leaves it drawing its default `T_leaf_01`. This is the only master that produces a
  real alpha cutout *and* shades like foliage.
- `M_AlphaTest` (`/Game/AssetsvilleTown2/...`) — generic masked master (fences, metal): cuts
  correctly, parameter `Color`, but shades like metal. Use it for fences and grates, never for
  vegetation.
- `M_GlassTrans` — the translucent target for surfaces that must blend rather than cut.

There is **no master in Motor Town that samples a separate opacity texture**. The author's
`M_C1_Surface_Masked` reads a dedicated `OpacityTex` parameter, but that design cannot be
reproduced with a vanilla master — the mask has to be moved into the colour texture's alpha
channel (`Base_Color` on `M_Plants`, `Color` on `M_AlphaTest`).

Correction to what this document said earlier: the foliage master's parameter is **`Base_Color`**,
not `BaseColor`. Seven builds bound `BaseColor` and silently rendered the master's default leaf.

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
- **F — parameter rename on the `M_AlphaTest` lineage.** 25 instances carried `Color` after being
  reparented to the foliage master; renaming them to `BaseColor` restored a live binding. Proved
  that "black background" is a *binding* symptom, not a blend symptom — but the rename still used
  the wrong target name (see P4).
- **G — the release's whole material tree, repacked into our namespace.** Result: **every material
  broken at once.** Cause: the release's assets carry `/Game/Mods/C1/…` inside their bytes while we
  filed them under `/Game/Mods/C1Full/…`, so the set fell back to the engine default. Proved the
  namespace rule (checklist M19).
- **D1/D2 — magenta probes on the tree atlas.** `area_zz_02_gtf_tex_191` replaced in place with
  solid magenta, then with 75 % transparent blocks. Result: *"some of the trees have a magenta
  texture"* — so texture overrides from a material pak do reach the screen, and those trees were
  rendering **opaque**. Proved the texture path works and localised the failure to the material,
  not the pak machinery.
- **I1/I2 — parent swapped to `M_AlphaTest`, then pointed at `T_fenceMetal_01`.** Still black.
  Proved the fence master cuts fine but is not the foliage master, and that a blend override cannot
  rescue a wrong master.
- **P1/P2 — blend-mode override removed (`--clear-overrides`).** P1 still black *because the
  override was still in the file*: it had been written back in the D chain and every rebuild carried
  it forward. Only after adding a real `--clear-overrides` op (verified by dumping the shipped pak)
  was the canonical configuration actually shipped. P2: still black — because of population (step 0).
- **P3 — all 19 remaining foliage instances moved to `M_AlphaTest`, `BaseColor`→`Color`.**
  Result: *"they no longer look like trees, but they do seem cut out"*. Cutout correct, master
  wrong.
- **P4 — all 20 foliage instances moved to `M_Plants` with the parameter renamed `BaseColor` →
  `Base_Color`.** The master's own name map declares `Base_Color` (underscore) alongside
  `Base_Color_Tint`, `SubSurface_Color`, `SubSurface_Power`, `WindPower`. Everything before this
  bound `BaseColor`, so the master always drew its default `T_leaf_01`. This is the first build
  that binds the real tree atlases on the real foliage master, with no overrides.

- **P5/P6 — texture repair and the bushes.** P5 pointed the tree instances at real atlases (a rename
  had truncated one to a non-existent `area_zz_02_gtf_tex`), and moved `MI_C1_mat_tree_06` off a
  **PF_DXT1** texture — no alpha channel, so it could never cut. P6 converted the 9 bush instances,
  which sat on the author's **opaque** `M_C1_Surface`: their textures are 31–76 % transparent, so an
  opaque master painted the backdrop (the "green background"). Result: *"nothing changed"* — because
  the family had been moved to `AssetsvilleTown/M_Plants`, which is **not** the master the geometry's
  instances use.
- **P7 — stop overriding foliage entirely.** The pak shipped *without* its 27 foliage instances, so
  the geometry pak's own author-derived instances drew the trees. Result: *"the main trees are fixed
  now."* The instances were never broken. Our material pak had been replacing a working author
  configuration with a different master, on every build since B.
- **P8 — the same treatment for bushes only.** Bushes keep their own `BaseColor` binding, are
  parented to `Stylized_Forest/M_plants` (the master the working trees use), and carry no overrides.
  Still on the author's opaque master otherwise, which is the last green backdrop.

The pattern to notice: A–E were all arguments about blending, and blending was never the problem.
F–P4 were all *binding* failures, and the last one was a single character: `BaseColor` vs
`Base_Color`. Three separate rules converge here — count the population (step 0), read the
master's real parameter names (step 3), and never carry an override forward without verifying the
shipped bytes.

---

## 3b. The rule that would have saved the whole loop

**A material pak does not have to include an instance at all.** Absence is a configuration: if the
base pak's own instance already renders correctly, overriding it can only make things worse, and
saying so is a one-build experiment rather than an argument.

- Before building a fix for a family, build **the pak without that family** and look. If the symptom
  disappears, the base configuration was correct and the defect is in *your* override — not in the
  base assets, not in the blend mode, not in the alpha.
- Corollary: never "fix" an instance by moving it to a *differently named* master and assuming the
  names line up. Two foliage masters exist (`Stylized_Forest/M_plants` with `BaseColor` +
  `opacity`; `AssetsvilleTown/M_Plants` with `Base_Color` + `SubSurface_*`). They are different
  materials with different contracts; a swap is a rewrite.
- Corollary: the geometry pak's instances come from the author. They are the reference. Compare
  against them before replacing them.

## 4. Diagnosis procedure — follow it in order

Do these in sequence and stop at the first hit. Do not skip ahead to blend flags.

0. **Count the population before you touch one of it.** A reported symptom is almost never one
   instance. Query the whole family — e.g. every instance whose bound texture lives under
   `/Textures/vegetation/` — and print parent, parameter name and override state for each. Twenty
   foliage instances existed; nineteen were on an opaque master and only one was on a masked one, so
   three consecutive builds changed exactly one tree while a forest stayed black. Fixing "the"
   instance you dumped is not fixing the symptom.
1. **Identify the instance.** A coordinate plus a screenshot beats any amount of statistics.
   From the coordinate, get the cell, then the mesh, then the material slot. Name the MI
   before changing anything.
   The player position is readable without asking: UE4SS writes
   `MotorTown\Binaries\Win64\ue4ss\UE4SS.log`, and the client mod logs
   `pawn_loc=<x> <y> <z>` (centimetres, y negated — the same convention as the import). A mod that
   only logs `tick no-pawn` means the player is not spawned; the coordinates appear once it is.
   The game's own Unreal log is *not* written to `Saved\Logs` — only Chromium/CEF logs are there.
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
  parameter names. Diff two instances rather than guessing at the group — and count the group first
  (step 0), because "some" is usually the majority.
- **Cut out correctly but no longer look like trees** → the cutout is right and the *master* is
  wrong: the instance is bound to a master that does not shade like foliage (or the colour parameter
  is dead and the master is drawing its own default texture). Check the master's own name map.
- **A one-character parameter difference** (`BaseColor` vs `Base_Color`, `Color` vs `BaseColor`) is
  not a typo to fix casually: parameter names are a contract, and a mismatch is a silent, total
  failure of that binding.

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
- `--clear-overrides <in> <out> <list|->` — remove `BasePropertyOverrides` entirely so the
  instance inherits the parent's blend state. Added after discovering that a blend override
  written by an earlier stage survives every later rebuild: P1 was meant to be "no override" and
  still shipped one. Use this whenever a build claims to be canonical; then dump the *shipped*
  pak to confirm the block is gone.
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
- **Verify a whole family, not a representative instance.** Better: assert on the set — parent,
  parameter name and override presence for every instance in the reported family. One correct
  instance proves nothing about the other nineteen.
- **Edits are cumulative, so verify the shipped bytes.** Property blocks written in an earlier
  stage persist through every subsequent pass. Dump out of the built `.pak`, not out of the
  staging directory.

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
