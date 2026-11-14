# C1 source lights — street lamps, tunnel lights, sign lights

Extracted from `/opt/data/inbox/c1src/c1_src.zip` by `c1/tools/extract_source_lights.py`. **10,474 light actors** in 12 level groups. Regenerate, do not hand-edit.

| group | class | count | cells | in 74-cell corridor | enabled |
|---|---|---:|---:|---:|---:|
| `streetlamps` | SpotLight | 8,087 | 229 | 1,470 | 0 |
| `tunnel_lights` | SpotLight | 1,148 | 43 | 343 | 0 |
| `sign_lights` | PointLight | 1,116 | 122 | 356 | 0 |
| `rainbow_bridge` | PointLight | 123 | 9 | 0 | 0 |

`streetlamps` is split into `lightgroup1..9` (383 / 999 / 1000 / 1000 / 706 / 1000 / 1000 / 1000 / 999). Those nine groups are BeamNG light groups, not lamp types: every one of the 8,087 lamps carries the same light parameters.

## Every street light is authored DISABLED

`isEnabled: false` on all 10,474. BeamNG drives them from the light-group system at night; the level file stores values, not a lit state. Porting them as "on" reproduces only the geometry intent, not the source behaviour — and by day the source map is unlit.

## Lamp recipe (uniform across all 8,087 street lamps)

- SpotLight, `range 20 m`, `brightness 2`, amber `rgb(1, 0.39, 0)` (sodium) for 6,728 of them
- `innerAngle 25°`, `outerAngle 170°` — a wide soft falloff, not a tight cone
- `shadowSoftness 0.5`, shadow `texSize 32` (lowest) → the source does **not** give these lights crisp shadows

Tunnel lights (`1,148`): same range/brightness, but `innerAngle 90°` and `texSize 256` — tighter, sharper, aligned down the bore.

Sign lights (`1,116` PointLights) carry no explicit color/brightness/range: they inherit engine defaults and only exist to lift signage. `rainbow_bridge` (123 PointLights) is the one coloured set — green, blue, and a few warm — all `texSize 256`. 9 cells, all outside the corridor.

## Spacing

- 1,034 of 8,087 street lamps are within 30 m of the authored loop spline
- median gap **17.0 m** (p10 4.0 m, p90 34.8 m) — dual carriageway pairs and interchange clusters pull the p10 down
- lamp head Z: 841.6 m min, 869.8 m median, 929.0 m max (deck heights, not sea level)

## Port equivalents

Same frame as the spawns/POIs: **`ue_cm = (x*100, -y*100, z*100)`**. Every one of the 10,474 lights lands in a cell that ships in the C1Full pak (554 cells), so no light is orphaned by the port.

Inside the 74-cell corridor (the C1 shipped loop): **2,169 lights** — 1,470 street, 343 tunnel, 356 sign.

## What the port has today

The `C1Full` level dump (718 actors) contains **zero light actors**: 554 StaticMeshActor, 156 MotorTownRoad, one `BP_C1_Sky`, one `ExponentialHeightFog`, one PlayerStart, one MotorTownNavigation, one MTAIVehicleSpawnSystem. All 10,474 source lights were dropped in the port. Whatever night lighting the C1 map is supposed to have has to be authored.

## Placing lights in the port

Motor Town already ships the actors: `/Game/Objects/Light/Streetlamp_01B, 02, 02_A, 03, 04, 04_A, 05, 06, 09` (+ `Lamp_01..11`, `CeilLight_*`, `BillboardLight_01`, `SpotLight_01`, `FloodLight_01A`, `InvisibleLight_02`). `Streetlamp_03_C` derives from `_Base_BreakableLight_C` and holds one `USpotLightComponent` at `0x3A8` — i.e. MT lamps are breakable blueprint actors with their own spot light.

Performance reality: 9,235 shadow-capable spot lights is far past what the renderer will take. A port pass should place lamps only along the loop, only where a player can see them, and leave MT's own light parameters alone:

- start with the 1,470 corridor street lamps, one actor per *pair* (both carriageways share a post run)
- tunnel bores are the highest-value set: 343 lights, enclosed, no shadow cost worth measuring
- drop `sign_lights` entirely — 1,116 point lights for signage is not worth the pass
- never more than a handful lit within one 50 m view, and let the sky do the rest

