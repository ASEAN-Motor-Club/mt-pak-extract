# Motor Town master material contracts (measured)

Evidence: `--dump` of the master asset (NameMap) plus **283 game-authored MaterialInstances**
sampled from `client-0.7.19.pak`, grouped by their real parent. A parameter's type is taken from the
instances that set it, never from the parameter name.

## Confirmed by instances

**`M_BaseTexture`** (AssetsvilleTown2) — 51 instances
- `Texture` — **texture**
- `Color` — **vector** (a tint, *not* the colour map)
- `Roughness` — scalar
- also: `UV`, `WorldPositionOffsetZ`

**`M_PolygonMaster`** (Env/Materials/Master) — **parameter NAMES only, types unproven**
- `BaseColor` — *name present; type never observed.* No sampled instance binds a **texture** to
  `M_PolygonMaster` (4 instances import it, none carry `TextureParameterValues`). Instances that were
  reparented here to bind a colour map lost their texture in game (P15 → P16). Treat `BaseColor` as
  unknown until an instance that works is found, and prefer the instance's **existing** parent.
- `BaseColor_Tint` — vector (observed on `MI_BaseColor`)
- `BaseColor_Tint` — vector
- `Normal` — texture
- `Metallic` — texture
- `Roughness` — texture
- `Emissive` — **texture**, `Emissive_Tint` — vector, `EmissiveIntensity` — scalar
  (set together by `MI_MatteWhite_01`, 11 instances)
- NameMap additionally: `Opacity`, `Use_Opacity`, `Use_OpacityFromAlpha`, `Use_Emissive`,
  `Use_NormalTexture`, `Use_MetallicTexture`, `Use_RoughnessTexture`, `MetallicIntensity`,
  `RoughnessIntensity`, `Specular`, `UVChannelIndex`, `UV_Tiling`

**`M_BaseColor`** — 9 instances: `Color` — **vector**, `Roughness` — scalar. **No texture slot**;
this master cannot carry a colour map.

**`M_GenericBase`** — 13 instances: `BaseTexture`, `NormalTexture`, `MetallicRoughnessTexture`,
`EmissiveTexture`, `OverlayTexture`, `ColorChangeMask`, `Hair_Mask`, `TriplanarTexture_*` (textures);
`ColorTint`, `EmissiveOffset`, `BaseOffset`, `NormalOffset` (vectors); `AmbientOcculusion`,
`Metallic`, `Roughness`, `SeaLevel` (scalars).

**`M_Base`** — 10 instances: `Main_texture`, `Main_Normal`, `Emiisive_Color` (textures — note the
typo in the shipped name), `Color` (vector), `Metallic`/`Roughness`/`Specular`/`Burn`/`NormalAmount`
(scalars).

**`MI_GlassTrans` / `MI_GlassNonDirection`** — `BaseColor` (texture), `GlassTint` (vector),
`Opacity` (scalar), `Roughness` (scalar).

**`M_AlphaTest` / `M_AlphaTestOneSided`** — confirmed, from a game-authored instance.

`MI_AlphaTestOneSided` (`/Game/AssetsvilleTown2/Materials/MI_AlphaTestOneSided`) parents
`M_AlphaTestOneSided` and sets:

- `Texture` — **texture** parameter (`T_hay`)
- `Color` — **vector** parameter (LinearColor)
- `Roughness` — scalar (3.0)

Both masters carry the identical NameMap (`Color`, `Roughness`, `T_fenceMetal_01`, `Texture`,
`Texture2D`), i.e. the same graph with the sidedness switch flipped, so the contract transfers.
No instance of `M_AlphaTest` itself was sampled, but the sibling settles the layout.

**Consequence, and it is a real bug:** the pavement-text paks (P10–P13) bound the colour map to
`Color`. That is a **vector** parameter, so the write was ignored and the material's real `Texture`
slot kept its default `T_fenceMetal_01`. That is the explanation for "translucent but missing
texture" and then "not rendering at all". **Bind the colour map to `Texture`** on this master —
`Color` is the tint.

**`M_PlantMaster`** — `AO` parameter exists in the NameMap but no sampled instance sets it, so its
type is unknown. Only candidate for an AO slot; `M_GenericBase` has `AmbientOcculusion` (scalar) but
that is an intensity, not a map.

## Ranking for the reimport

1. **`M_PolygonMaster`** — richest *name list*, but unproven for texture binding (see above). Do
   **not** reparent a working opaque instance onto it. Default only for rows whose current parent is
   missing from the game.
2. **`M_GenericBase`** — richest overall (separate emissive map, AO scalar, overlays, triplanar) but
   heavier and oriented to character/environment assets; use where a dedicated emissive map is needed.
3. **`M_BaseTexture`** — simple colour map + tint + roughness; good for flat signs.
4. **`M_BaseColor`** — flat vector colour only; for the 40 `diffuseColor` materials.
5. **`M_PlantMaster`** — foliage: masked, two-sided, AO.
6. **`M_AlphaTest`** — only after the parameter test above proves its layout.
