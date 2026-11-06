# P16 — material reimport, reparenting corrected

Supersedes P15. Confirmed in game: the concrete and median-guardrail families are back, and the
masking fix (road markings, lane lines, bushes) is untouched.

## Artifact

- `zzzzz_AMC_C1Mats_P16_P.pak` — 3,071,606 B, sha256 `4e956990b90b9906…`
- 1,653 material instances, no shader archives
- Archived at `/opt/data/releases/c1/` as well as installed

## What changed from P15

P15 reparented **every** instance to the master its treatment implied, including 1,173 opaque rows
that were already parented to masters shipping in the game (`M_PropMaster`, `M_PropMaster` variants).
Those instances rendered correctly; moving them removed their working binding, so concrete,
guardrails and other opaque families lost their textures.

P16 reparents **only what does not exist**:

- **1,173 opaque — parent left as authored** (`kept_parent=1173`)
- **442 masked/bake/ownalpha — reparented to `M_AlphaTest`**, because `BLEND_Masked` requires it
- 1,615 changed, 38 copied (34 `keep_authored` + 4 translucent), 0 failed

`M_PolygonMaster` is no longer a default target. Its `BaseColor` was recorded as a texture slot from
a NameMap, and no shipped instance ever binds a texture to it — the claim is now marked unproven in
`MASTER_CONTRACTS.md`.

## Rules this build encodes

- Reparent only when the current parent is absent from the game.
- Masking is the one deliberate exception.
- A master's parameter **names** are not its parameter **types**; a NameMap is not evidence.

## Known gaps (unchanged)

- 95 secondary texture references point at assets the port never shipped (mostly `*em`/`*EM`
  emissive maps, a few `TNL`/`SMO` normals), each reported on its row.
- 4 materials left translucent over the road: three DXT1 with no alpha channel, one with a 1/255
  spread. Nothing to mask with.
- Emissive: 186 rows accounted, 136 reported lost — 120 sit on the masked master, which has no
  emissive parameter.
