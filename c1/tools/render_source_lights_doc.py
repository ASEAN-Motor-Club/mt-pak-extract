#!/usr/bin/env python3
"""Render c1_source_lights.json into the markdown reference doc (c1/docs/C1_SOURCE_LIGHTS.md)."""
import json
import sys

SRC = sys.argv[1] if len(sys.argv) > 1 else '/opt/data/workspace/mt-pak-wt-c1commit/c1/source/c1_source_lights.json'
OUT = sys.argv[2] if len(sys.argv) > 2 else '/opt/data/workspace/mt-pak-wt-c1commit/c1/docs/C1_SOURCE_LIGHTS.md'
d = json.load(open(SRC))
L = d['lights']

out = []
w = out.append
w('# C1 source lights — street lamps, tunnel lights, sign lights\n')
w(f"Extracted from `{d['archive']}` by `c1/tools/extract_source_lights.py`. "
  f"**{d['total']:,} light actors** in 12 level groups. Regenerate, do not hand-edit.\n")
w('| group | class | count | cells | in 74-cell corridor | enabled |')
w('|---|---|---:|---:|---:|---:|')

groups = ['streetlamps', 'tunnel_lights', 'sign_lights', 'rainbow_bridge']
cls = {'streetlamps': 'SpotLight', 'tunnel_lights': 'SpotLight',
       'sign_lights': 'PointLight', 'rainbow_bridge': 'PointLight'}
for g in groups:
    s = [x for x in L if x['group'] == g]
    w(f"| `{g}` | {cls[g]} | {len(s):,} | {len({x['cell'] for x in s})} | "
      f"{sum(1 for x in s if x['in_corridor']):,} | {sum(1 for x in s if x['enabled'])} |")
w('')
w('`streetlamps` is split into `lightgroup1..9` (383 / 999 / 1000 / 1000 / 706 / 1000 / 1000 / 1000 / 999). '
  'Those nine groups are BeamNG light groups, not lamp types: every one of the 8,087 lamps carries the same '
  'light parameters.\n')
w('## Every street light is authored DISABLED\n')
w('`isEnabled: false` on all 10,474. BeamNG drives them from the light-group system at night; the level file '
  'stores values, not a lit state. Porting them as "on" reproduces only the geometry intent, not the source '
  'behaviour — and by day the source map is unlit.\n')
w('## Lamp recipe (uniform across all 8,087 street lamps)\n')
w('- SpotLight, `range 20 m`, `brightness 2`, amber `rgb(1, 0.39, 0)` (sodium) for 6,728 of them')
w('- `innerAngle 25°`, `outerAngle 170°` — a wide soft falloff, not a tight cone')
w('- `shadowSoftness 0.5`, shadow `texSize 32` (lowest) → the source does **not** give these lights crisp shadows\n')
w('Tunnel lights (`1,148`): same range/brightness, but `innerAngle 90°` and `texSize 256` — tighter, '
  'sharper, aligned down the bore.\n')
w('Sign lights (`1,116` PointLights) carry no explicit color/brightness/range: they inherit engine defaults '
  'and only exist to lift signage. `rainbow_bridge` (123 PointLights) is the one coloured set — green, blue, '
  'and a few warm — all `texSize 256`. 9 cells, all outside the corridor.\n')
sp = d['loop_spacing']
w('## Spacing\n')
w(f"- {sp['lamps_within_30m_of_loop']:,} of 8,087 street lamps are within 30 m of the authored loop spline")
w(f"- median gap **{sp['gap_median_m']} m** (p10 {sp['gap_p10_m']} m, p90 {sp['gap_p90_m']} m) — dual "
  f"carriageway pairs and interchange clusters pull the p10 down")
w('- lamp head Z: 841.6 m min, 869.8 m median, 929.0 m max (deck heights, not sea level)\n')
w('## Port equivalents\n')
w('Same frame as the spawns/POIs: **`ue_cm = (x*100, -y*100, z*100)`**. Every one of the 10,474 lights lands '
  'in a cell that ships in the C1Full pak (554 cells), so no light is orphaned by the port.\n')
w('Inside the 74-cell corridor (the C1 shipped loop): **2,169 lights** — 1,470 street, 343 tunnel, 356 sign.\n')
w('## What the port has today\n')
w('The `C1Full` level dump (718 actors) contains **zero light actors**: 554 StaticMeshActor, 156 '
  'MotorTownRoad, one `BP_C1_Sky`, one `ExponentialHeightFog`, one PlayerStart, one MotorTownNavigation, one '
  'MTAIVehicleSpawnSystem. All 10,474 source lights were dropped in the port. Whatever night lighting the C1 '
  'map is supposed to have has to be authored.\n')
w('## Placing lights in the port\n')
w('Motor Town already ships the actors: `/Game/Objects/Light/Streetlamp_01B, 02, 02_A, 03, 04, 04_A, 05, 06, '
  '09` (+ `Lamp_01..11`, `CeilLight_*`, `BillboardLight_01`, `SpotLight_01`, `FloodLight_01A`, '
  '`InvisibleLight_02`). `Streetlamp_03_C` derives from `_Base_BreakableLight_C` and holds one '
  '`USpotLightComponent` at `0x3A8` — i.e. MT lamps are breakable blueprint actors with their own spot light.\n')
w('Performance reality: 9,235 shadow-capable spot lights is far past what the renderer will take. A port '
  'pass should place lamps only along the loop, only where a player can see them, and leave MT\'s own light '
  'parameters alone:\n')
w('- start with the 1,470 corridor street lamps, one actor per *pair* (both carriageways share a post run)')
w('- tunnel bores are the highest-value set: 343 lights, enclosed, no shadow cost worth measuring')
w('- drop `sign_lights` entirely — 1,116 point lights for signage is not worth the pass')
w('- never more than a handful lit within one 50 m view, and let the sky do the rest\n')

open(OUT, 'w').write('\n'.join(out) + '\n')
print('wrote', OUT, len('\n'.join(out)), 'chars')
