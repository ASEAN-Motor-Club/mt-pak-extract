# C1 emissive — rebuild state (2026-11-15)

## Established facts (measured, not inferred)

1. `M_C1_Surface_Tex` source had sampler-type mismatches (Normal/Linear Color params on
   Color placeholder textures) -> SM6 compile errors -> default-material fallback.
   FIXED at source: all five texture params = sampler Color; `EmissiveStrength` default
   5.0, slider 0-100. Editor preview glows (user-confirmed).
2. Our project cook writes the master WITHOUT shader strings
   (`Saved\Cooked\WindowsServer\...\M_C1_Surface_Tex.uexp` = 3,599 B, 0 shader strings),
   including a full `-CookAll` WindowsServer cook (`c1/tools/cook_server.ps1`).
3. RUNTIME TRUTH (Lua probe `emis/probe13.lua`): the shipped instance's live parent is
   `Material /Game/Env/Materials/Master/M_PropMaster` — a VANILLA master with NO emissive
   parameter. Every emissive entry we ever wrote was inert.
4. The materials pak `zzzzz_AMC_C1Mats_P27_P.pak` contains 3,306 material files but NOT
   `M_C1_Surface_Tex`. The client's Paks dir currently has no materials pak at all.
5. No pak (client or archive) contains `M_C1_Surface_Tex`; both
   `/Game/Mods/C1/Materials/` and `/Game/Mods/C1Full/Materials/` resolve as live objects,
   so it is loaded from somewhere not yet identified.

## Donor parameter survey (out/*_parsed.json)

- `MI_Halloween_Master`: BaseColor, Normal only  -> any clone inheriting it is DEAD for emissive.
- `MI_GhostLight_Halloween_01`: BaseColor, Emissive, EmissiveIntensity, Emissive_Tint,
  Normal, Use_Emissive, Use_NormalTexture — but its PARENT is MI_Halloween_Master.
- `MI_Rug_Halloween_01`: same param set, also parented into the Halloween chain.
- `MI_PolygonMaster`: essentially empty (RefractionDepthBias); its parent IS
  `M_PolygonMaster` (the master that does declare Use_Emissive/EmissiveIntensity/Emissive_Tint).

## The gap

No vanilla instance in hand both (a) parents to `M_PolygonMaster` and (b) carries
BaseColor/Emissive texture entries. Cloning `MI_PolygonMaster` gives (a) but the texture
entries cannot be added (`--set-mi-params` textures block only CLONES an existing entry).
Cloning ghost/rug gives (b) but the parent chain (MI_Halloween_Master) lacks emissive params.

## Next build (not yet done cleanly)

Clone `MI_GhostLight_Halloween_01` (keeps BaseColor/Emissive/Use_Emissive entries)
THEN `--patch-export-props` its Parent import to
`/Game/Env/Materials/Master/M_PolygonMaster`, verify
`Import[...] = Material, Name=M_PolygonMaster` before packing.
Note: probe17.sh attempt re-used probe15 paths due to a sed mismatch — script hygiene
needed, no pak was installed from it.

## Client state

Probe v13 installed (Pak9), Count=10, game running. Cleanup = delete
`*C1EmisProbe*` paks, rewrite CustomPak.ini with the 9 real mods (see `emis/restore2.ps1`).
