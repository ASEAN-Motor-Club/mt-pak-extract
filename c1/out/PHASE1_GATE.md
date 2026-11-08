# Phase 1 gate — compiled material plan

`c1/out/materials_plan.json` — one row per port instance, from the canonical source.

**Source** `c1/source/merged.materials.json` sha256 `9a828c56…4a78a`, 1,605 materials. Re-verified
after re-download: the census matches the port's baseline exactly, so this is the same revision.

**Instances** 1,653 rows → 1,619 resolved + 34 `keep_authored` (no source entry; port-only).
1,604 distinct source keys, so 49 keys carry two instances.

## Treatment

- **opaque** 1,173 — parent `M_PolygonMaster`, colour into `BaseColor`
- **masked** 355 — parent `M_AlphaTest`, colour into `Texture`, clip from `alphaRef/255`
- **bake** 79 — separate opacity map baked into the colour alpha, clip 0.5
- **ownalpha** 8 — translucent with no mask, masked off the colour's own alpha, clip 0.5
- **translucent_keep** 4 — genuinely cannot be masked, left translucent and reported
- **keep_authored** 34 — no canonical material, untouched

Reconciles with the source census:
- 365 `alphaTest` instances − 10 that also carry an opacity map = **355 masked**
- 79 bake = 68 translucent+mask + 10 alphaTest+mask + 1 mask on a non-translucent material
- 12 translucent with no mask = 8 ownalpha + 4 left alone
- 1,173 opaque, unchanged

## Property translation

- **Two-sided: 79 rows**, from the source's own `doubleSided`. Not a blanket setting — this is the
  defect that made P10–P14 wrong.
- **Clip: 442 rows** = masked + bake + ownalpha.
- Textures bound: base 1,619 (100 % of live rows), opacity 79, roughness 217, normal 170,
  metallic 153, emissive 66, AO 71.
- **Emissive: 186 rows.** 66 carry a map; 136 are reported lost explicitly (120 sit on the masked
  master, which exposes no emissive parameter; 16 are factor-only with no map).
- **AO: never silent** — 156 rows report that no non-foliage master takes an AO map.
- **95 secondary texture references unresolved** (mostly `*em`/`*EM` emissive maps and a few
  `TNL`/`SMO` normals). Each is reported on its own row; none is silently dropped.
- Assumptions, all recorded per row: 10 "alphaTest + opacity map → the map is the mask",
  14 "alphaTest with no alphaRef → clip 0.5", 1 "opacity map on a non-translucent material".

## Trust in the alpha decisions

Base-texture alpha was measured from the cooked texture where possible; 338 rows fell back to the
**source dds** because small cooked textures keep their mips inline (no `.ubulk`) and cannot be
decoded. Those three "leave translucent" calls were each confirmed from the DDS header as DXT1
(no alpha channel). No masked/ownalpha decision rests on an unknown alpha.

## Not verified yet

The plan is analysis only; nothing has been packed. Applying it needs each instance's parameter
**names** rewritten to the target master's contract (`Texture` vs `BaseColor`), which the tool does
not yet do per-master, and the two-sided/clip overrides written per row rather than per batch.
