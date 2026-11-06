# C1 lighting — what we port, and why the primitive is ours

Source: BeamNG `levels/c1` light actors, extracted by `c1/tools/extract_source_lights.py` into
`c1/source/c1_source_lights.json` (10,474 actors). Geometry inventory in `C1_SOURCE_LIGHTS.md`.

## What exists in the source

| group | total | in corridor |
|---|---|---|
| `streetlamps` | 8,087 | 1,470 |
| `tunnel_lights` | 1,148 | 343 |
| `sign_lights` | 1,116 | 356 |
| `rainbow_bridge` | 123 | 0 |
| **corridor total** | | **2,169** |

Only the 74-cell corridor ships in the C1 pak, so **2,169** is the whole port target. Every source
light is authored `isEnabled: false` — the source lights the map at night from its own light-group
system, so day-time darkness is *source behaviour*, not an optimisation.

**Lamp recipe** (uniform across 8,087 street lamps): SpotLight, range **20 m**, brightness 2,
amber `rgb(1, 0.39, 0)`, inner **25°** / outer **170°**, `shadowSoftness 0.5`, shadow `texSize 32`
(no crisp shadows in the source either). Tunnel: same but inner **90°**, texSize 256.

## Posts are not ported — they are already in the geometry

The nine `streetlamps/lightgroupN` groups contain 8,087 `SpotLight` and **zero `TSStatic`**. The
posts are part of the terrain/road geometry that became the 554 cell meshes, and the lamp-lens
materials are already in the port's material-instance set (`MATERIALS_ALPHA_BLEND.md`). So the port
adds **light only**: no post geometry, no extra draw calls.

## Rejected primitives

| candidate | why not |
|---|---|
| `/Game/Objects/Light/Streetlamp_*`, `SpotLight_01` | placing *instances* of game BP classes from our project ships an export of the dummy → `RF_NeedLoad` on load (`motortown-ue-project-map-authoring`) |
| `InvisibleLight_Base_C` | a bare `AActor` with no `RegisterDistance` — always on, no culling hook |
| MT's `RegisterDistance` + `MTComponentLOD` mechanism | not exposed to a bare project; MT's own lamp BPs are the only consumers |

## Chosen primitive

**`/Game/Mods/C1Full/Blueprints/BP_C1_Lamp`** — our own Blueprint:

- parent `Actor` (plain engine class, safe to instance)
- root `SceneComponent`
- child `SpotLightComponent` named `Light`
- variables `bLit` (bool, default false), `RegisterRadius` (float, default 15000)
- light **off** by default; `cast_shadows = false`, mobility `Movable`

Because it is our own BP and not a game BP, instances are safe to place from `C1FullMirror`.

## Density is local, not total

Measured from the inventory (2,169 corridor lamps):

- nearest-neighbour spacing: street median **10.1 m** (facing pairs — both sides of the road),
  tunnel median **9.6 m**
- lamps within a radius of a lamp position: 100 m → median 26 / p99 73; 150 m → median 40 /
  max 101; 200 m → median 56 / max 127
- worst pocket: **17 lamps inside a 20 m radius**

26–40 lights near any viewpoint is what the GPU sees; the level total is not the frame cost. That is
why the plan ports all 2,169 and bounds what is *enabled* instead (manager nearest-N), and why
global thinning is explicitly not a lever.

## Open behaviour work

- day/night gating: driven by the level's directional light elevation, not hard-coded hours
- manager: `BP_C1_LightManager`, 0.5 s timer, enables the N nearest lamps (default 32)
