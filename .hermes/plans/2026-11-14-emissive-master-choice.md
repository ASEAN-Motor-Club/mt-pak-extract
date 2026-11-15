# Emissive on C1: master choice, thought through before building

Date: 2026-11-14. Supersedes the recommendation given in chat ("reparent the unmasked 65 to
M_BaseTexture") — that recommendation was wrong and is retracted below.

## 1. The check that changed the design

`c1/docs/MASTER_CONTRACTS.md` (measured from 283 game-authored MIs, not guessed):

- **`M_AlphaTest` / `M_AlphaTestOneSided`** — NameMap is exactly `Color`, `Roughness`,
  `T_fenceMetal_01`, `Texture`, `Texture2D`. **No emissive input of any kind.**
  `Color` is a VECTOR tint; the colour map binds to `Texture`.
- **`M_BaseTexture`** — `Texture`, `Color` (vector tint), `Roughness`, `UV`,
  `WorldPositionOffsetZ`. **Also no emissive input.**

### Retraction
I told freeman to reparent the unmasked 65 with an emissive map onto `M_BaseTexture`.
`M_BaseTexture` does not sample emissive. Doing that would have written `EmissiveColor`
into 65 MIs that no shader reads — the same class of silent no-op that cost hours tonight
with the wrong `UAssetTool.dll`. Corrected here before any code was written.

## 2. Which masters can actually emit

- **`M_GenericBase`** — `EmissiveTexture` (texture), `ColorTint`, `EmissiveOffset` (vector),
  `AmbientOcculusion`/`Metallic`/`Roughness`/`SeaLevel` (scalar). 13 instances.
  No opacity parameter observed → cannot carry an alpha-test clip.
- **`M_PolygonMaster`** — `Emissive`, `Emissive_Tint`, `EmissiveIntensity` (set together by
  `MI_MatteWhite_01`, 11 instances) **plus** `Opacity`, `Use_Opacity`,
  `Use_OpacityFromAlpha`, `Use_Emissive`. This is the only measured master that can do
  **alpha AND emissive in one material**.
  Known landmine: its `BaseColor` colour-map binding is *unproven* — instances reparented
  there lost their texture in game (P15 → P16).
- **`M_Base`** — `Emiisive_Color` (sic, typo in the shipped asset), `Main_texture`. 10 instances.

## 3. The actual decision, with its risk stated

Masked emissive materials (windows, billboards, light panels — the bulk of the 92) cannot
keep both properties without landing on `M_PolygonMaster`, whose colour-map binding has
already burned us once. Two candidate designs:

**A. No reparent for masked.** Masked emissive materials stay on `M_AlphaTest` and ship
without emissive this pass. Only unmasked emissive materials move to `M_GenericBase`.
- Zero risk of breaking alpha or colour binding.
- Cost: the windows — the most visible emissive content on a night map — stay dark.

**B. Everything emissive onto `M_PolygonMaster`.** One master, one code path, alpha and
emissive both available.
- Full visual result.
- Risk: if `BaseColor` cannot take a texture on this master, all 92 lose their colour map
  and render as tinted white — a worse regression than staying dark.

Both are guesses until measured. Therefore: **probe first, mass-apply second.**

## 4. Probe design

One small pak, 2–3 replaced MIs at their existing asset paths (no map edits):
1. an unmasked emissive material reparented to `M_GenericBase` with `EmissiveTexture` bound;
2. a masked emissive material reparented to `M_PolygonMaster` with `Use_Emissive=1`,
   `Use_Opacity=1`, `Emissive` bound, clip preserved, `BaseColor` bound to its colour map;
3. optionally one `M_Base` (`Emiisive_Color`) variant.

Pass criteria, checked **in game** on the night map:
- colour map still visible (proves the texture binding survived the reparent);
- cutout still correct on the masked one (proves the clip survived);
- the surface glows (proves the emissive path is live).

Fail on (1) or (2) ⇒ fall back to design A for that class. No bulk run before this passes.

## 5. Emissive content rules (unchanged, from EMISSIVE_MATERIALS.md)

- Authority for *which* materials emit: `c1/source/merged.materials.json`, verified equal to
  the archive copy (65 `emissiveMap`, 138 `emissive: true`, union 184; ship set 92 = 65 mapped
  + 27 dark-albedo/HDR sentinels). `EmissiveStrength` is a decoy (1.0 everywhere) — ignored.
- Exclusions: `1e-06` factors, `godray_emitter`, `thunderbolt`.
- **Bind per material, not via an atlas.** The doc's atlas-rect scheme is a web-viewer
  optimisation; the engine path takes one emissive sheet per material, and we have those
  sheets from the archive. This removes an entire class of rect/UV bugs.
- Sentinel materials (no emissive map): `EmissiveTexture` = their own albedo, intensity 1.2,
  Reinhard-toned, per the doc's `clamp(texel.rgb*2.0, 0, 1)` intent expressed as an engine
  material parameter rather than a shader formula — verify on the probe which the master
  actually honours.

## 6. Order of operations

1. Probe pak built + verified in game (gates the rest).
2. `emissive_materials.py` written against the winning master path, dry-run census must
   reproduce the 92-material set with per-material `mapTo` traceability.
3. Emissive pass applied **after** the 07c alpha pass (so it sees final parents/param names),
   before the 07b release merge.
4. Release pak, `09_verify.sh`, install to a non-live slot; CustomPak.ini untouched.

## 7. Not to be repeated

- Never write a material parameter without first confirming the target master samples it.
- Never infer a master's capability from a parameter *name* (M_PolygonMaster's `BaseColor`
  is the standing counter-example).
- Never reparent a material before checking what the reparent does to its colour map binding.
