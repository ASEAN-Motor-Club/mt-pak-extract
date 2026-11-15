# Canonical material sidedness and alpha repair

Status: **verified in game**, 2026-11-15.

## Ground truth

`mat_PA_tatsumi_parts` was flickering on cell `c11_9`. The original BeamNG archive
(`/opt/data/inbox/c1src/c1_src.zip`) defines it as:

- `doubleSided` absent: single-sided
- `alphaTest=True`, `alphaRef=49`: masked, clip `49/255 = 0.1922`
- correct parent from `materials_plan_effective.json`: `M_AlphaTestOneSided`

The original DAEs already contain duplicate triangles, including same-normal and
opposite-normal copies. Each DAE is instanced once in the BeamNG level. The duplicates
are canonical geometry, **not an OBJ export artifact**; do not delete them as a blanket
Z-fighting fix.

## Regression and repair

The emissive rollout had replaced Tatsumi's one-sided masked parent with the opaque,
two-sided `MI_MatteBlue_01_E`. Comparing every merged instance against Base_v3 found
189 changed instances: 153 opaque and 36 non-opaque. The 36 non-opaque instances
(21 masked, 10 baked-mask, 4 translucent, 1 own-alpha) were restored from Base_v3,
preserving their compiled parent, blend mode and source-derived clip value.

All 1,653 instances then received the source `doubleSided` value: 77 two-sided, the
remainder one-sided. `UAssetTool --set-sidedness` writes `TwoSided` explicitly and also
writes `bOverride_TwoSided`; without the arm, the engine silently inherits the parent's
sidedness. Existing blend overrides receive `bOverride_BlendMode` too. `IsZero=false` is
required even for a false bool, otherwise UAssetAPI omits it from the unversioned export.

Reproduce with `c1/tools/restore_canonical_materials.py`.

Runtime probe after the repair:

- parent `M_AlphaTestOneSided`
- `BLEND_Masked`
- clip `0.1922`
- `TwoSided=false`

User verdict: **"that works"**.
