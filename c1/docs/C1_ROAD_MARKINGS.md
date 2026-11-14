# C1 road markings (kanji / lane-text paint) — where they are and whether they collide

Regenerate with `c1/tools/extract_source_markings.py`; data in `c1/source/c1_source_markings.json`.

## They are not decals

`main.decals.json` holds **two** instances in the whole level. The road paint is geometry:

- **427 marking meshes**, each its own `.dae` with a single geometry and one marking material
  (`mat_kbs_*` / `mat_mj_*`) — 255 in `shutoko/`, 91 in `bayshore/`, 81 in `yokohane/`
- each is placed as its own `TSStatic` (427 instances in the level)
- typical size ~1.4 m × 1.9 m; 214 distinct materials in use

Vocabulary in the material names: `tomare` = 止まれ (STOP), `ya_red` / `ya_blue` / `ya_migue` /
`ya_hidaue` = 矢印 arrows, `cr_30..80` = curve-radius, `dia_*` = ダイヤ diamond markings,
`bunki_*` / `gouryu*` = 分流 / 合流, `hojo1/2/3_*` = 補助標示 destination text (銀座 / 日本橋 /
羽田 …), `lname_*` = lane names, `mj_*` = 文字 text (東京 / 横浜 / 品川, `sokudo_y` 速度,
`gensoku20kiroika`, `0m/40m/60/80m` distance markers).

## In the port they are baked into the cells

Merged into 145 of the port's cell meshes as ordinary material sections —
**1,364 marking material slots**. Densest cells: `5_18` (37), `3_19` (29), `2_11` (28),
`2_10` (28), `1_19` (26), `-2_12` (25).

Measured on the cell OBJs: the paint surface sits **0–3 cm above the adjacent asphalt**
(dominant cluster 0/1/2/3 cm, median 2.4 cm). That offset is in the source geometry, not a port
hack — it is what stops the paint z-fighting the road it is painted on.

## It is the rectangle that is raised and that collides — not the glyph

The paint looks glyph-shaped, but the geometry is not cut to the glyph. Every marking mesh is a
patch of quads; the kanji comes from the texture. Three mechanisms carry it, counted across the
214 marking materials in `merged.materials.json`:

- **62** use `translucentBlendOp: "AddAlpha"` — additive, so a black background contributes
  nothing and only the bright paint reads
- **27** use `alphaTest: true` with `alphaRef: 255` — a hard binary cutout from the texture alpha
- **96** are plain opaque — the whole quad draws and the texture itself carries the glyph with
  matching surroundings
- the remaining ~29 use assorted `alphaRef` values

None of that changes physics. BeamNG's `Visible Mesh Final` collision uses the mesh triangles and
ignores blending and alpha entirely, so **the collider is the full quad, glyph area included and
invisible area included**. The elevation likewise applies to the whole quad — it only *looks*
like the kanji alone is floating because the rest of the quad draws nothing.

Mesh sizes are not uniform: a single small mark can be a 0.55 m quad with 2 triangles, a whole
intersection's paint can be a 42 × 46 m patch with 500+ triangles. So "remove the kanji from
collision" is not a thing we can do by selecting the glyph — the quad is the unit.

## Collision: YES, the source collides them

Every one of the 427 marking TSStatics carries:

```json
"collisionType": "Visible Mesh Final"
```

BeamNG's own TSStatic documentation defines the values as:

| value | meaning |
|---|---|
| `None` | no collision |
| `Bounds` | object bounding box |
| `Collision Mesh` | dedicated collision meshes from the shape (recommended) |
| `Visible Mesh` | rendered mesh polygons used for collision (expensive) |
| `Visible Mesh Final` | rendered mesh polygons used for collision, **intentionally** |

So the markings are collidable in the source. All 3,510 level TSStatics use the same value, so
this is the level's blanket setting, not a decision made per marking.

It is harmless there only because the slab is flush: nothing protrudes above the road surface,
so a wheel never meets an edge.

## Why it hurts in the port

The port's cell meshes use `CTF_USE_COMPLEX_AS_SIMPLE` — the whole triangle soup, marking
sections included, is the collision surface. A painted quad 2–3 cm proud of the asphalt is then a
real 2–3 cm lip on the drivable surface, and complex collision is the expensive path anyway.

Options, in order of cost:

1. **Split markings into their own mesh** (`cells_marks/`) with `NoCollision`, keep the road
   mesh as the collidable cell. Paint can then be lifted as far as needed with zero gameplay
   effect. Cost: ~145 extra actors/draw calls, same material slot count.
2. **Simple collision on cells** (convex/box hull) instead of complex-as-simple — markings stop
   colliding and collision gets cheaper, but the road surface becomes approximate (kerbs, ramps,
   stacked decks need checking).
3. **Leave it** — only defensible if the measured lift really is ≤ ~1 cm everywhere; verify the
   shipped cooked mesh, not the import source.

Do not remove the paint geometry: it is the only thing that draws the markings. Remove it from
*collision*, or lower it.
