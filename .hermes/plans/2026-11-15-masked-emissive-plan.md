# Masked + emissive C1 materials — research and plan (2026-11-15)

## Problem

Ten C1 materials (tunnel lamps, traffic signals, Tokyo Tower glow, vending/object props)
are **masked** (alpha cutout) and need **emission**. Two facts established by testing:

- No vanilla material is both masked and emissive-capable. `M_PlantMaster` is
  `BLEND_Masked` with no emissive; the emissive-enabled instances (`MI_MatteBlue_01_E`,
  `MI_FishingVil_Glass_01`) are opaque/glass. `MI_Transparent` is masked but exposes no
  parameters at all (only `Parent`), so it cannot be driven.
- Our own cooked masters rendered grey every time.

## Research findings

**Root cause of custom-master grey (Epic forums, multiple independent reports):**
"Share Material Shader Code" (project packaging setting, **default ON** since UE4.25)
moves compiled shaders into a *shared shader library*
(`ShaderArchive-…-PCD3D_SM5.ushaderbytecode`). A game that mounts a third-party pak
**never loads that archive from the pak**, so the material logs
`Missing shader resource for hash … in the shader library` /
`Can't compile … with cooked content, will use default material instead` and renders as
the grey default.

This explains every observation to date:

- **Instances that inherit a vanilla parent's shaders work** — no new shader needed.
- **Instances carrying `bHasStaticPermutationResource` fail** — they request a *new*
  permutation, i.e. a new shader, which is again unavailable.
- **`M_FlashLight_LF` instances emitted** — unlit parent shaders already exist in game.
- **Our own masters always failed** — a master needs its own compiled shader code.

Verified locally: `D:\UEProjects\C1\Config\DefaultEngine.ini` has **no**
`bShareMaterialShaderCode` entry, so it is at the default (enabled).

Secondary finding (same threads): rendering settings in the mod project should match the
game (renderer / shader model), or cooked materials can load incorrectly. Our cook uses
`-TargetPlatform=Windows`, which has been fine for textures and instances.

## Decision

Disable shared shader code for the mod project and re-cook the custom masked master.
This is the documented fix for exactly our symptom, and it also unblocks future custom
masters instead of forcing every material onto a vanilla parent.

## Steps

1. **Config**: add to `D:\UEProjects\C1\Config\DefaultEngine.ini`
   under `[/Script/UnrealEd.ProjectPackagingSettings]`:
   - `bShareMaterialShaderCode=False`
   - `bSharedMaterialNativeLibraries=False` (native shader libraries off too)
2. **Re-cook** (`cook_client.ps1`). Confirm the cooked masked master's `.uexp` grows and
   contains standalone shader code, and that no `.ushaderbytecode` archive is required.
3. **Single-material gate**: install the masked pak with only `MI_C1_mat_kb_light_a`
   enabled (a lamp, intensity 4.7). Verify:
   - probe: instance resolves, parent = `M_C1_MaskedEmissive`
   - visual: alpha cutout intact **and** emitting
   - absence of the grey default = the shared-shader fix worked
4. **Full set**: if the gate passes, enable the remaining nine with their existing
   entries (`masked_entries.json`, intensities from the source). If a subset is preferred
   (skip the vending/object props), edit the entries first.
5. **Rollback**: the masked content is a **separate pak**; deleting it restores the
   original masked materials. The working 174-material opaque pak is untouched and is not
   reinstalled as part of this work.

## Verification gates

- Config change present in `DefaultEngine.ini` (read back).
- Cooked master export materially different from the pre-change build (hash).
- Live probe returns our master as parent.
- Visual: cutout + emission, not grey, not a solid quad.

## Risks / open questions

- Disabling shared shader code changes the whole cook output; other cooked assets are
  regenerated. We only ship the masked pak from that cook, so blast radius is limited.
- If the game still rejects the custom master after the setting change, the fallback is
  to **skip masked emission entirely** (keep the current correct cutouts, no glow) and
  record that custom masters are not viable for this game — not to keep iterating
  indefinitely.
- Renderer/shader-model mismatch is a second possible cause if the first fix does not
  resolve it; would need the game's rendering settings compared against the project's.

## References

- Epic forums: "Why are my materials not rendering after updating to 4.25" — fix:
  deselect "Share Material Shader Code" in packaging.
- Epic forums: "Shaders from mounted pak are not loaded when I mount the pak file and
  open the map from it" — same fix; includes the exact `Missing shader resource for hash`
  log lines.
- Local recipe and instance rules: `c1/tools/emissive/README.md`, tag `c1-emissive-v1`.

## RESOLVED (2026-11-15)

Disabling `bShareMaterialShaderCode` + `bSharedMaterialNativeLibraries` and re-cooking
made the custom masked master render correctly — gate lamp `mat_kb_light_a` confirmed
in-game with its cutout intact and emitting, parent probe returning
`M_C1_MaskedEmissive`. Master `.uexp` grew to 31,060 B (standalone shader code embedded).
Full ten-material masked set rolled out as a separate pak alongside the 174-material
opaque set. Custom masters are viable for this game with that setting.
