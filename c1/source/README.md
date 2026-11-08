# C1 canonical source — provenance

`merged.materials.json` here is the **canonical material source** for the port: 1,605 materials with
their blend, cut, colour, surface and emissive definitions. Every material decision in
`c1/tools/build_materials.py` is derived from it, never from a family name or a screenshot.

**It lives in the repo on purpose.** It previously lived only in `/opt/data/cache/scratch/beamng/`,
which the 24-hour scratch GC deleted — which silently removed the single source of truth for the
whole port. Do not move it back to scratch.

## Provenance

- **Mod:** "Tokyo's Shuto Expressway — Metropolitan Expressway" (BeamNG), the C1 Shuto loop.
  BeamNG thread `threads/tokyos-shuto-expressway-metropolitan-expressway.61259`.
- **Archive:** `c1_src.zip`, 509,258,112 B, sha256
  `333f0edbb9b82b0b6d737f76d5c049d5da9042c69fd6391c63d56c6457a33da4`
  (kept at `/opt/data/inbox/c1src/c1_src.zip`, not in git — 500 MB).
- **Downloaded:** 2026-11-06, from the thread's Google Drive mirror
  (`drive.google.com/file/d/19Xb7YFEYYRH1Bk8i-wO0kH4bUVVBijaK`). The 2019-era
  `drive.google.com/open?id=1in_3zw…` link in the archived copy of the thread is dead (404).
- **Extracted path in the archive:** `levels/c1/art/models/merged.materials.json`
- **This file:** 739,154 B, sha256
  `9a828c5640c2d4435d3d62cacd9bb7be1a3dc77ab7026a6f50fd623baca4a78a`

## Version check (do this after any re-download)

The census must match the port's baseline, or the archive is a different map version:

- materials **1,605**
- `alphaTest` **351** · `alphaRef` **389** · `translucent` **80** · `translucentBlendOp: AddAlpha` **63**
- `doubleSided` **77** · `colorMap` **1,317** · `baseColorMap` **285** · `diffuseColor` **40**
- `opacityMap` **78**

Measured on the file committed here: all match. If a future download disagrees, the port was built
against a different revision and the differences must be reconciled before any rebuild.

## Not committed

The archive's textures and DAE meshes are **not** needed for material work: the port ships its own
copies under `Mods/C1/Textures`, and the geometry pak is the authority for what the client loads.
