# C1 materials — complete reimport from the canonical source (v2, audited)

Status: PLAN, revised after an exhaustive key-by-key audit of `merged.materials.json`.
Nothing executed. Gates marked [ ].

## 1. Why the approach is "rewrite everything"

- **1,653 MaterialInstances** in `zzzz_AMC_C1Test_P.pak`, all under `Mods/C1Full/Materials`.
  **3,306 material entries, zero of them Materials** — every entry is an `MI_*`.
- Every instance parents to one of four author masters (`M_C1_Surface` 1,393,
  `M_C1_Surface_Tex` 155, `M_C1_Surface_Trans` 80, `M_C1_Surface_Masked` 25) at
  `/Game/Mods/C1/Materials/…`, and **`Mods/C1/Materials` does not exist in the pak**.
  Dangling parents ⇒ the engine substitutes the default material.

That is the system defect the family-by-family patches could never fix.

## Status

**Shipped.** P16 is the release (`c1/out/P16_RELEASE.md`, tag `c1-materials-p16`). The plan's phases
all ran; the one assumption that had to be thrown out was "opaque goes to `M_PolygonMaster`" — see
P16 notes and `MASTER_CONTRACTS.md`.

## 1a. Source availability — was a blocker, now RESOLVED (reacquired)

**Resolved 2026-11-06.** The source was missing (scratch GC deleted
`/opt/data/cache/scratch/beamng/`), so it was re-downloaded and is now committed at
**`c1/source/merged.materials.json`** (739 KB) with provenance in `c1/source/README.md`.
Version check passed against the port's baseline exactly — 1,605 materials, `alphaTest` 351,
`alphaRef` 389, `translucent` 80, `AddAlpha` 63, `doubleSided` 77, `colorMap` 1,317,
`baseColorMap` 285, `diffuseColor` 40, `opacityMap` 78 — so this is the same revision the port
was built from, not a newer map release.

`07c_build_materials.sh` now defaults `MATJSON` into the repo instead of scratch.

The original note, kept for the lesson:

`merged.materials.json` **no longer exists on this machine**. The BeamNG extraction lived at
`/opt/data/cache/scratch/beamng/x/…`, which the scratch GC pruned; a full search finds no copy on
disk, none in any git history, and none on the Windows client. `07c_build_materials.sh` still
defaults `MATJSON` to that dead path, so the stage cannot run as written.

What survives, and is enough to proceed if we choose to:

- **The author's own instances encode the blend decision per material** — every `MI_*` carries
  `BasePropertyOverrides` with `BlendMode`, `TwoSided` and `OpacityMaskClipValue` (sampled 6 of 6:
  `BLEND_Masked`, two-sided, clip 0.3333). That is a port-side contract for mask/opaque/blend,
  independent of the lost JSON.
- **`tex_alpha_all.json`** (1,190 textures, format + transparency ratio) survives in scratch and
  answers "can this texture cut" without the source.
- The measured census in §2 is preserved in this plan and in `MATERIALS_ALPHA_BLEND.md` §3f, so the
  numbers are not lost even though the file is.

Two ways forward, and they differ in fidelity:

1. **Re-acquire the source** (Shuto C1 BeamNG archive) and keep the plan exactly as written —
   per-material `alphaRef` thresholds (177–252) survive.
2. **Re-point the contract at the author's instances** — recovers blend/two-sided/clip but collapses
   every cutout to the author's uniform 0.3333, losing the per-material thresholds.

Decision pending with freeman. Whichever wins, the canonical inputs must live in the repo
(`c1/source/`), not in scratch: a 24-hour GC deleted the single source of truth for this port.

## 2. Exhaustive property matrix (measured on the 1,619 instances that resolve)

Every key that exists anywhere in the file, its count over the instances, and how it is translated.
"Unsupported" below is a definition, not a shrug: it is reported per instance.

### Blend / cut

| property | count | translation |
|---|---|---|
| `alphaTest` true | 351 | masked; clip = `alphaRef/255` |
| `alphaTest` true, no `alphaRef` | 14 | masked at **0.5**, flagged, eyeballed in Phase 5 |
| `alphaRef` present, no `alphaTest` | 52 | **no cut** — the ref is inert; recorded, not applied |
| `alphaTest` + `translucent` together | 0 | impossible in this data set |
| `translucent` | 80 | see the transparency table below |
| `translucentBlendOp: AddAlpha` | 63 of 80 | **masked** (decided with freeman after A/B on 62 textures): no MT additive master, glyphs stay legible, sorting disappears |
| `translucentBlendOp: None` | 1,525 | opaque (+ alphaTest), never translucency |
| `translucentZWrite` | 80 (all translucent) | no MI switch; unsupported, recorded |
| `translucentRecvShadows` | 65 | no MI switch; unsupported, recorded |
| `doubleSided` | 77 | TwoSided **only when true**; all 77 are opaque/masked, **none** translucent |
| `castShadows` | 0 in the instance set (3 elsewhere) | out of scope, recorded |
| `invertBackFaceNormals` | 0 in the instance set | out of scope, recorded |

> Correction to what I shipped in P10–P14: `TwoSided = true` was set on **every** masked instance.
> The source says two-sided for 77 of them only. The rewrite takes TwoSided from `doubleSided`
> exactly, and never "just in case".

### Colour

| property | count | translation |
|---|---|---|
| `colorMap` (sRGB) | 1,316 | base colour texture |
| `baseColorMap` | 285 | base colour texture (PBR spelling, same slot) |
| `diffuseColor` (flat RGBA) | 40 | **no texture** — needs a colour *vector* param; else 1×1 solid texture, reported |
| none of the three | 3 | left authored, recorded |
| `colorMap` + `baseColorMap` together | 0 | mutually exclusive, verified |
| `baseColorFactor` | 30 (stage 0) | tint: scalar/vector if the master has one, else folded into the 1×1 case, else recorded |
| `mapTo` | 1,605 | identity (`mapTo == name` for all resolved) — **no aliasing** |

### Surface

| property | count | translation |
|---|---|---|
| `normalMap` | 170 | normal slot; linear — never re-encoded by the alpha bake |
| `normalMapStrength` | 1 | scalar if the master exposes one, else recorded |
| `roughnessMap` | 217 | roughness slot |
| `roughnessFactor` | 24 | scalar; **map wins, factor only when no map** |
| `metallicMap` | 153 | metallic slot |
| `metallicFactor` | 169 | same precedence |
| neither metallic map nor factor | 1,433 | master default, recorded |
| `ambientOcclusionMap` | 156 | AO slot if present, else **dropped and recorded** (first channel to sacrifice) |

### Emissive — under-stated in v1, actually 184 instances (~11 %)

| property | count | translation |
|---|---|---|
| `emissive` flag only | 116 | needs an emissive master; colour map, factor 1.0 |
| `emissiveMap` | 65 | emissive texture |
| `emissiveFactor` | 68 | scalar tint |
| `instanceEmissive` | 15 | scalar variant, treated as `emissiveFactor` |
| `glow` / `glowFactor` | 4 / 2 | routed to the emissive path, flagged as approximation |

**Answered by Phase 0 (measured, not assumed).** Two game masters carry emissive:

- `M_PolygonMaster` — params `Emissive`, `Emissive_Tint`, `EmissiveIntensity`, `Use_Emissive`,
  plus `Normal`, `Metallic`, `Roughness`, `Opacity`, `Use_Opacity`, `Use_OpacityFromAlpha`.
  This is the game's own default prop material: the game's `MI_BaseColor` wrapper parents to
  `MI_PolygonMaster`, so it is battle-tested on ordinary static meshes.
- `M_BaseColor` — `Color` (texture) + `Emissive`, `Metallic`, `Roughness` (scalars).

So the 184 emissive instances are representable; they do not need to be downgraded.
AO is the constrained one: `AO` exists only on `M_PlantMaster` (masked, two-sided, foliage).
AO elsewhere is dropped and reported, per the degradation order.

### Transparency — three sources, one of which v1 missed

| case | count | translation |
|---|---|---|
| `translucent` + `opacityMap` | 68 | bake opacity into colour alpha (all mips), masked at 0.5 |
| `translucent`, no `opacityMap`, colour map has alpha | 12 | masked off its own alpha at 0.5 |
| **`opacityMap` without `translucent`** | **10** | **cutout mask on an opaque material** — bake into alpha and mask, not left opaque |
| `alphaTest` (mask in colour alpha) | 351 | masked, clip from `alphaRef` |

### Sampler / engine-level properties (cannot live on a MaterialInstance)

| property | count | handling |
|---|---|---|
| `useAnisotropic` | 1,370 | sampler setting; recorded, not applied |
| `animFlags`, `sequenceFramePerSec`, `sequenceSegmentSize` | 4 | flipbook; **excluded from baking and masking**, recorded |
| `detailMap` / `detailNormalMap` / `detailScale` | 4 / 4 / 2 | unsupported (second UV set + blend), recorded |
| `groundType` (`VOID` 101, `RUMBLE_STRIP` 1, `SHOCK_ABSORBER` 1) | 103 | audio/physics surface, not a material; recorded |
| `persistentId`, `version`, `name`, `class` | all | metadata; ignored |
| stages 1–3 | **0 in the instance set** (20 materials globally, factors only, no maps) | verified non-issue |

### Instances with no canonical material

**34** instance names have no entry in the source JSON (15 `MI_C1X_*`, plus e.g.
`MI_C1_mat_road_03`, `MI_C1_mat_box`). They are **not** rewritten: they keep their authored setup
and are listed so the gap stays visible.

## 3. Design (revised)

### 3.0 Master inventory (measured this session — Read, not assumed) [x]

Dumped from `client-0.7.19.pak`, NameMap plus a real game instance per master:

- `M_PolygonMaster` (Env/Materials/Master) — BaseColor, BaseColor_Tint, Emissive, Emissive_Tint,
  EmissiveIntensity, Use_Emissive, Normal, Use_NormalTexture, Metallic, MetallicIntensity,
  Roughness, RoughnessIntensity, Opacity, Use_Opacity, Use_OpacityFromAlpha, Specular, UVChannelIndex,
  snow/rain/wind switches. **The default prop master.**
- `M_PolygonRoadMaster` — same plus road-specific Noise/triplanar; no AO.
- `M_PlantMaster` — BaseColor, **AO**, Normal, Roughness, Opacity, two-sided, BLEND_Masked.
  The only master with an AO slot.
- `M_AlphaTest` / `M_AlphaTestOneSided` — single `Color` texture + `Roughness`; the cheap masked pair.
- `M_BaseColor` — `Color` texture + `Emissive`/`Metallic`/`Roughness` scalars.
- `M_BaseTexture` — single `Texture` param (what the game's road-sign instances use).
- `M_PropMaster` — BaseColor, Normal, Mask, Use_MaskTexture, Use_NormalTexture, Metallic, Roughness.
- `M_GlassTrans` / `M_Glass` / `M_GlassNonDirection` — translucent family; no additive.
- `M_GroundMaster`, `M_RoadMaster`, `M_Decal_Base`, `M_DecalMaster`, `M_MudMaster`, `M_Plants`,
  `M_Leaves`, `M_Trunk`, `M_SubSurface`, `M_Metal`, `M_Flag`, `M_Cables`, `M_Animation`.

Consequence for §3.3: **`M_PolygonMaster` is the primary target**, not `M_AlphaTest`. It has colour,
normal, metallic, roughness, emissive and opacity gating in one master, which removes most of the
degradation pressure. `M_AlphaTest` remains the fallback when a row needs nothing but colour.

Still to confirm in Phase 0 before use: the exact *type* of `Emissive` on each master (texture vs
scalar) — names are proven, types are inferred from the NameMap and must be confirmed against a
game instance that sets it.

### 3.1 Phase 0 — Ground truth [x] (results below)

**Gate 1 — dangling parents, confirmed on the live pak.** Scanned the client's current
`zzzz_AMC_C1Test_P.pak` (699,996,849 B) with `findstr`:
`/Mods/C1/Materials` → **MISS**, `M_C1_Surface_Masked` → **MISS**, `MI_C1_mat_mj_honsen` → HIT,
`Mods/C1Full/Materials` → HIT. The instances are present; their parents are not.

**Gate 2 — master contracts, measured.** 283 game-authored instances dumped and grouped by parent.
Full table in `c1/docs/MASTER_CONTRACTS.md`. Key results: `M_BaseTexture.Texture`=texture and
`Color`=**vector**; `M_PolygonMaster` has `BaseColor`/`Normal`/`Metallic`/`Roughness` as textures
plus `Emissive`=**texture** with `Emissive_Tint` and `EmissiveIntensity`; `M_BaseColor` has **no
texture slot at all** (flat `Color` vector).

**Gate 3 — emissive is solved, AO is not.** Emissive: full support on `M_PolygonMaster`
(texture + tint + intensity) and `M_GenericBase` (`EmissiveTexture`). AO: only `M_PlantMaster.AO`
(untyped — no sampled instance sets it) and `M_GenericBase.AmbientOcculusion` (a scalar, not a map).
AO therefore remains droppable-and-reported everywhere except foliage.

**Root cause found and settled offline (no game test needed).** `M_AlphaTest`'s colour map binds to
**`Texture`**; `Color` is a **vector tint**. Proven by the game's own `MI_AlphaTestOneSided`, which
sets `Texture` as a TextureParameterValue (`T_hay`) and `Color` as a VectorParameterValue, on a
master with an identical NameMap.

P10–P13 bound the colour map to `Color` — a vector parameter — so every write was ignored and the
master kept its default `T_fenceMetal_01`. That is the whole "missing texture" → "not rendering at
all" chain, explained without a build.

Consequence for Phase 2: binding parameter per target master is `Texture` on `M_AlphaTest`,
`BaseColor` on `M_PolygonMaster`, `Texture` on `M_BaseTexture`, `Color` (vector) on `M_BaseColor`.
The compiler must carry the parameter name **per master**, never globally.

### 3.1b Original Phase 0 checklist (for the record)

1. Check the **client's current** pak (`zzzz_AMC_C1Test_P.pak`, 699,996,849 B) for `Mods/C1/Materials`.
   Gate: counted present/absent.
2. Build a **master capability matrix**: for each candidate master, dump 3 game-authored instances
   and record its {colour, normal, rough, metal, AO, emissive, opacity} slots and exact parameter
   names → `c1/docs/MASTER_CONTRACTS.md`.
   Candidates: `M_AlphaTest`, `M_AlphaTestOneSided`, `M_BaseColor`, `M_BaseTexture`, `M_Glass`,
   `M_Metal`, `M_Plants`, `M_SubSurface`, `M_Trunk`, `M_Water_Realistic`,
   `/Game/Env/Materials/Master/{M_PropMaster, M_GlassTrans}`.
3. Gate: **no master is used later without a dumped contract.**

**If the author masters turn out to exist in a pak we have not inspected, stop and re-plan** — the
job becomes much smaller.

### 3.2 Phase 1 — Compiler [ ]

`c1/tools/compile_materials.py` → `materials_plan.json`, one row per instance with every field in §2
plus `unsupported[]` and `assumptions[]` (clip defaults, dropped channels, approximations).

Gate: 1,653 rows; 34 unresolved present and marked `keep_authored`; treatment histogram matches §2.

### 3.3 Phase 2 — Master assignment with a defined degradation order [ ]

- masked → `M_AlphaTest`, or `M_AlphaTestOneSided` when `doubleSided` is false
- opaque → the master with the most matching slots
- translucent (68 + 12) and `opacityMap`-only (10) → masked substitution (no `AddAlpha` equivalent,
  and translucent decals sort against the road)
- emissive → a master with an emissive slot if one exists, else non-emissive + reported

When a master lacks a slot, channels drop in a **fixed order**, recorded per instance:
**AO → metallic → roughness → normal → emissive**. Colour and alpha are never dropped; a row whose
master cannot take a colour texture fails loudly instead of shipping a white prop.

Gate: zero silent drops; every drop in `unsupported[]`.

### 3.4 Phase 3 — Textures [ ]

- bake only where the chosen master needs alpha the shipped texture lacks (§2 transparency table)
- bake **every mip**, box-filter the mask per level, keep source pixel format, assert byte count
- never re-encode normal/data maps; never touch sRGB flags; flipbooks excluded
- every texture a row depends on is verified present in the client pak (format + alpha) or shipped by us

Gate: per-texture report (format, mips, alpha source, coverage); zero size mismatches.

### 3.5 Phase 4 — Apply [ ]

Ops (`--rename-texture-param`, `--set-mi-parent`, `--clear-overrides`, `--set-clip`) driven strictly
by the plan JSON. Invariants: run from `<repo>/csharp/UAssetTool`; `Error:` fails on exit 0;
digit-suffixed FNames resolve via `--dump`; in-count == out-count or abort.

Gate: counts match, pak built, SHA recorded.

### 3.6 Phase 5 — Verification [ ]

Static, 100 % of rows: parent exists in the client pak; every parameter name legal for its master;
blend/clip/two-sided match the plan; no stale overrides.

In-game, one pass per family: lane lines (`mat_line`, `mat_mj_line` @0.988) · crosswalks
(`mat_zeb_b`) · `_o_data` markings (`mat_line_br`) · pavement text (`honsen`, `wangan`, arrows) ·
emissive signage spot check · foliage regression · opaque spot check.

Gate: each family signed off; regressions reverted per family.

### 3.7 Phase 6 — Ship and roll back [ ]

Single file `zzzzz_AMC_C1Mats_P.pak`; previous build kept beside it for A/B. Commit compiler, plan
JSON, `MASTER_CONTRACTS.md`, `MATERIALS_ALPHA_BLEND.md` §5. Stage `07c` loses its `--family mat_mj`
default.

## 4. Non-goals (explicit)

Recreating `M_C1_Surface*` or authoring new Material assets (see §4.1) · exact `AddAlpha` · `translucentZWrite`,
`translucentRecvShadows`, `castShadows`, `groundType`, `useAnisotropic`, `invertBackFaceNormals`,
`detailMap`/`detailNormalMap`, flipbook animation, `normalMapStrength` without a slot.

### 4.1 Can we author our own materials, or write shaders?

**Authoring a new Material asset offline: no.** A cooked `UMaterial` is a graph plus a baked shader
map (platform bytecode, one permutation set per feature combination). Producing one requires the
editor or a matching DDC to compile it. Nothing in our toolchain synthesises that bytecode, and a
material without a valid shader map loads as the default material (which is exactly the checkerboard
we already diagnosed).

**Writing shaders: no, not usefully.** UE compiles material HLSL at cook time; cooked clients carry
shader bytecode, not source, and the runtime has no shader compiler. Hooking the shader pipeline from
UE4SS is not a supported path and is out of scope for a map port.

**What we can do, and what the plan uses:**

- **Clone an existing Material** (`--clone-asset`) to get a private master with the same graph under
  our own name. This isolates our instances from any other content sharing the master, but adds no
  parameters — the graph is fixed.
- **Bend a master per instance** via `BasePropertyOverrides`: `BlendMode`, `TwoSided`,
  `OpacityMaskClipValue`. That is how masked/translucent behaviour is already being set.
- **Pick the master whose slots already cover the row.** `M_PolygonMaster` covers colour, normal,
  metallic, roughness, emissive and opacity gating; `M_PlantMaster` adds AO; `M_AlphaTest` covers
  the colour-only masked case.

Because `M_PolygonMaster` has `Emissive`, the masked pavement text also has an optional upgrade
available later: masking + a modest emissive value reproduces the *look* of `AddAlpha` (self-lit
paint) without any translucent sorting. Not in scope now — noted because it is cheap if the masked
version reads too flat in-game.

## 5. Risks

1. Slot scarcity forces the degradation order; the order is a judgement call, so it is written down
   and reported per instance.
2. 1,653 rewrites at once are harder to bisect than family patches — mitigated by the plan JSON, the
   report, and keeping the previous pak.
3. The client's geometry pak has changed twice mid-session; textures are verified per build, never
   remembered.
4. Two instances of one key can need different treatment; the compiler keys on instance name.
5. Clip 0.5 for the 14 `alphaTest`-without-`alphaRef` materials is an assumption, reviewed in Phase 5.

## 6. Acceptance

- No shipped instance has a parent missing from the client pak.
- Every parameter name is legal for its master (checked, not assumed).
- Lane lines, crosswalks, markings, pavement text, emissive signage and foliage correct in one pass —
  no black panels, no white sheets, no checkerboards.
- The report states, per instance, exactly what could not be reproduced.
