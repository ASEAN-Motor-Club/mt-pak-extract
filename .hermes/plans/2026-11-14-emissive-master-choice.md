# Emissive on C1: master choice, thought through before building

Date: 2026-11-14, revised 2026-11-15 after web research.
Supersedes the chat recommendation "reparent the unmasked 65 onto M_BaseTexture" — retracted in §1.

## 1. The check that changed the design

`c1/docs/MASTER_CONTRACTS.md` (measured from 283 game-authored instances, not guessed):

- **`M_AlphaTest` / `M_AlphaTestOneSided`** — NameMap is exactly `Color`, `Roughness`,
  `T_fenceMetal_01`, `Texture`, `Texture2D`. **No emissive input of any kind.**
  `Color` is a VECTOR tint; the colour map binds to `Texture`.
- **`M_BaseTexture`** — `Texture`, `Color` (vector tint), `Roughness`, `UV`,
  `WorldPositionOffsetZ`. **Also no emissive input.**

### Retraction
Reparenting the unmasked 65 onto `M_BaseTexture` would have written `EmissiveColor` into
packages whose shader never reads it — the same silent no-op that cost hours with the wrong
`UAssetTool.dll`. Corrected before any code was written.

## 2. Which masters can actually emit

- **`M_GenericBase`** — `EmissiveTexture` (texture), `ColorTint`, `EmissiveOffset` (vector),
  `AmbientOcculusion`/`Metallic`/`Roughness`/`SeaLevel` (scalar). 13 instances.
  No opacity parameter observed → cannot carry an alpha-test clip.
  **No static switch observed on the emissive path** — the key property after §3.
- **`M_PolygonMaster`** — `Emissive`, `Emissive_Tint`, `EmissiveIntensity`, **plus** `Opacity`,
  `Use_Opacity`, `Use_OpacityFromAlpha`, `Use_Emissive`. The only measured master with
  alpha **and** emissive. Its `BaseColor` colour-map binding is *unproven* — instances
  reparented there lost their texture in game (P15 → P16).
- **`M_Base`** — `Emiisive_Color` (sic, typo in the shipped asset), `Main_texture`. 10 instances.

## 3. Web research (2026-11-15): static switches are compile-time

Sources consulted:
- Epic, *Material Parameter Expressions* — static switches change what the shader compiles to;
  dynamic (scalar/vector/texture) parameters are the ones changeable at runtime.
- Epic, *Understanding Shader Permutations* — a static switch selects a compiled permutation.
- Forum threads on changing `StaticSwitchParameter` at runtime: "It's a static switch that
  actually reduces or recalculates all instructions for the material. Other material branches
  can be adjusted at run time."
- *UE4 Modding Guide — Via UAssetGUI* — the supported material-modding pattern is to **copy an
  existing material instance**, because that "also allows you to change parameters that may not
  be present in the existing one".

**Consequence:** a `StaticSwitchParameter` on a **cooked** material instance recompiles nothing.
It requests a shader permutation that either exists in the cooked shader map or does not. If it
does not, the instance falls back — default permutation, or default material. We would set
`Use_Emissive=1`, ship, and see either no glow or a grey surface with no way to tell which link
broke. This demotes "patch the switch" from the obvious fix to the last resort.

## 4. The alternatives, ranked

**Option 1 — unconditional-emissive master (`M_GenericBase`).**
Bind `BaseTexture` (colour map) and `EmissiveTexture` (emissive sheet). Texture parameters are
runtime values: no permutation is requested, nothing can fall back. Structurally correct.
Limits: no opacity/clip → **unmasked materials only**; emissive brightness may only be
expressible through `ColorTint`/`EmissiveOffset` (unverified).

**Option 2 — clone a game-authored emissive instance and repoint its textures.**
Take an MI already parented to an emissive master, keep its parent and static-switch state (so
the cooked permutation already exists), and replace only its texture bindings with ours. This is
the pattern the modding guide endorses. Safest shader path. Costs: transplanting an unrelated
instance's parameter set; needs a donor per master family; donor switches must be inspected first.

**Option 3 — patch `Use_Emissive` on `M_PolygonMaster` (`--ensure-switch`).**
Needs a new UAssetTool op mirroring `--ensure-texparam`, because `BindStaticParam`
(Program.cs:8712) clones from an existing `StaticSwitchParameters` entry and these instances have
an empty array. Even implemented correctly, §3 says the write may not take effect.
**Held in reserve — build only if 1 and 2 are eliminated by measurement.**

**Option 4 — keep masked materials dark.**
Masked emissive materials stay on `M_AlphaTest` and ship without emissive this pass. Zero risk,
visibly incomplete: windows and light panels are the main night-time emissive content.

**Option 5 — hand-edit with UAssetGUI.**
Fine for one-offs and for inspecting what a working emissive MI looks like; not a pipeline.
A diagnostic tool, not a build path.

## 5. Decision tree

1. Dump the real `M_GenericBase` from the client pak.
   - emissive path has **no** static switch → **Option 1** for all unmasked emissive materials.
   - has a switch → fall through to **Option 2**.
2. For masked emissive materials, in this order:
   - **Option 2** if a donor instance exists on a masked+emissive master;
   - else **Option 3** as a controlled experiment (one material, in game, known-good fallback
     identified first);
   - else **Option 4**, and say so plainly rather than shipping something that may be grey.
3. Never ship a static-switch change without a visual check in game. The failure mode is
   invisible in the asset data.

## 6. Emissive content rules (unchanged, from EMISSIVE_MATERIALS.md)

- Authority for *which* materials emit: `c1/source/merged.materials.json`, verified equal to the
  archive copy (65 `emissiveMap`, 138 `emissive: true`, union 184; ship set 92 = 65 mapped +
  27 dark-albedo/HDR sentinels). `EmissiveStrength` is a decoy (1.0 everywhere) — ignored.
- Exclusions: `1e-06` factors, `godray_emitter`, `thunderbolt`.
- **Bind per material, not via an atlas.** The doc's atlas-rect scheme is a web-viewer
  optimisation; the engine path takes one emissive sheet per material and we have those sheets.
- Sentinel materials (no emissive map): their own albedo as the emissive texture, intensity 1.2,
  per-material `emissiveFactor` preserved; verify on the probe which parameter the master honours.

## 7. Probe artefacts and current state

- `MI_C1_building_black1` and `MI_C1_building_window1` reparented to `M_PolygonMaster`, colour
  param renamed to `BaseColor`, `Emissive` texture created and bound, `EmissiveIntensity` /
  `Emissive_Tint` written. **`Use_Emissive` NOT set** (no donor entry in the instance).
  Output: `/opt/data/cache/scratch/probe/<stem>/s5/`.
- That probe is **inconclusive by construction** — per §3 the missing switch may not work even
  when set. Re-run under Option 1 or 2 instead of chasing it.
- Emissive sheets already exist as UE textures (`Textures/other/building_black1`,
  `Textures/lamp/building_internal_lights1`) from the 2,327-texture import. No new imports.
- Local `M_GenericBase.uasset` copies are **0 bytes** (failed extraction); the real asset must be
  pulled from the client pak on the Windows install before Option 1 can be evaluated.

## 8. Order of operations

1. Extract + dump `M_GenericBase` from the client pak; settle Option 1 vs 2.
2. Rebuild the probe under the winning option; verify in game (colour visible, cutout correct,
   surface glows).
3. Write `emissive_materials.py` against the winning path; dry-run must reproduce the 92-material
   set with per-material `mapTo` traceability.
4. Apply emissive **after** the 07c alpha pass, before the 07b release merge.
5. Release pak, `09_verify.sh`, install to a non-live slot; CustomPak.ini untouched.

## 9. Not to be repeated

- Never write a material parameter without confirming the target master samples it.
- Never infer a master's capability from a parameter *name* (`M_PolygonMaster.BaseColor` is the
  standing counter-example).
- Never treat a static-switch write as effective in a cooked build without a visual check.
- Never reparent before checking what the reparent does to the colour-map binding.
