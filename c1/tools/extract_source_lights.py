#!/usr/bin/env python3
"""Extract the light inventory (street lamps, tunnel lights, sign lights, bridge lights)
from the original BeamNG C1 level and map it into Motor Town / C1Full coordinates.

Source groups (levels/c1/main/missiongroup/):
  streetlamps/lightgroup1..9   SpotLight  - the road lamps
  tunnel_lights/               SpotLight  - tunnel bores
  sign_lights/                 PointLight - illuminated signage
  rainbowbridge/               PointLight - Rainbow Bridge illumination

Writes c1/source/c1_source_lights.json + prints a summary.
"""
import collections
import json
import math
import os
import sys
import zipfile

ZIP = '/opt/data/inbox/c1src/c1_src.zip'
C1 = '/opt/data/cache/scratch/c1'
OUT = sys.argv[1] if len(sys.argv) > 1 else '/opt/data/workspace/mt-pak-wt-c1commit/c1/source/c1_source_lights.json'
CELL = 500.0

z = zipfile.ZipFile(ZIP)


def items(p):
    return [json.loads(l) for l in z.read(p).decode('utf-8', errors='replace').splitlines() if l.strip()]


corridor = {c['cell'] for c in json.load(open(f'{C1}/cells_manifest.json'))['cells']}
shipped_full = {l.strip() for l in open(f'{C1}/fullpak_cells.txt') if l.strip()}
origins = {k: v for k, v in json.load(open(f'{C1}/cell_origins.json')).items()
           if k.startswith('c') and k[1:].split('_')[0].lstrip('-').isdigit()}
road = [(p[0] / 100.0, p[1] / 100.0, p[2] / 100.0) for p in json.load(open(f'{C1}/c1_road_points.json'))]

GROUPS = [('streetlamps', f'levels/c1/main/missiongroup/streetlamps/lightgroup{i}/items.level.json')
          for i in range(1, 10)]
GROUPS += [('tunnel_lights', 'levels/c1/main/missiongroup/tunnel_lights/items.level.json'),
           ('sign_lights', 'levels/c1/main/missiongroup/sign_lights/items.level.json'),
           ('rainbow_bridge', 'levels/c1/main/missiongroup/rainbowbridge/items.level.json')]


def cell_of(x, y):
    return f"c{math.floor(x / CELL)}_{math.floor(y / CELL)}"


lights = []
summary = {}
for group, path in GROUPS:
    if path not in z.namelist():
        print('MISSING', path)
        continue
    want = 'PointLight' if group in ('sign_lights', 'rainbow_bridge') else 'SpotLight'
    key = f"{group}/{path.split('/')[-2]}" if '/lightgroup' in path else group
    n = 0
    for o in items(path):
        if o.get('class') != want:
            continue
        x, y, zc = o['position']
        c = cell_of(x, y)
        rec = {
            'group': group,
            'class': o['class'],
            'name': o.get('name'),
            'bng_m': [round(x, 2), round(y, 2), round(zc, 2)],
            'ue_cm': [round(x * 100, 1), round(-y * 100, 1), round(zc * 100, 1)],
            'cell': c,
            'in_corridor': c[1:] in corridor,
            'in_full_port': c in shipped_full,
            'enabled': bool(o.get('isEnabled', False)),
        }
        for k_src, k_dst in (('brightness', 'brightness'), ('range', 'range_m'),
                             ('innerAngle', 'inner_deg'), ('outerAngle', 'outer_deg'),
                             ('texSize', 'tex_size'), ('shadowSoftness', 'shadow_softness'),
                             ('color', 'color')):
            if k_src in o:
                v = o[k_src]
                rec[k_dst] = [round(f, 3) for f in v] if isinstance(v, list) else v
        lights.append(rec)
        n += 1
    summary[key] = n

print('counts', json.dumps(summary))

# ---- how close each lamp is to the shipped loop, and lamp spacing along it ----
for L in lights:
    x, y, _ = L['bng_m']
    best = min(((rx - x) ** 2 + (ry - y) ** 2, i) for i, (rx, ry, _rz) in enumerate(road))
    L['dist_to_loop_m'] = round(math.sqrt(best[0]), 1)
    L['loop_index'] = best[1]

onloop = sorted((L for L in lights if L['group'] == 'streetlamps' and L['dist_to_loop_m'] <= 30),
                key=lambda L: L['loop_index'])
gaps = []
for a, b in zip(onloop, onloop[1:]):
    dx, dy = b['bng_m'][0] - a['bng_m'][0], b['bng_m'][1] - a['bng_m'][1]
    d = math.hypot(dx, dy)
    if 0 < d < 200:
        gaps.append(d)
gaps.sort()
spacing = {
    'lamps_within_30m_of_loop': len(onloop),
    'gap_median_m': round(gaps[len(gaps) // 2], 1) if gaps else None,
    'gap_p10_m': round(gaps[int(len(gaps) * 0.1)], 1) if gaps else None,
    'gap_p90_m': round(gaps[int(len(gaps) * 0.9)], 1) if gaps else None,
}
print('spacing', spacing)

# ---- the "lamp recipe": which attribute set the groups actually share ----
def hist(grp, key):
    c = collections.Counter()
    for L in lights:
        if L['group'] != grp:
            continue
        v = L.get(key)
        if isinstance(v, list):
            v = tuple(v[:3])
        c[v] += 1
    return c.most_common(4)


recipe = {}
for grp in summary:
    recipe[grp] = {
        'enabled': dict(collections.Counter(L['enabled'] for L in lights if L['group'] == grp)),
        'brightness': hist(grp, 'brightness'),
        'range_m': hist(grp, 'range_m'),
        'color_rgb': [list(map(list, [(k, v) for k, v in hist(grp, 'color')]))],
        'inner_deg': hist(grp, 'inner_deg'),
        'outer_deg': hist(grp, 'outer_deg'),
        'tex_size': hist(grp, 'tex_size'),
        'shadow_softness': hist(grp, 'shadow_softness'),
        'cells': len({L['cell'] for L in lights if L['group'] == grp}),
        'in_corridor': sum(1 for L in lights if L['group'] == grp and L['in_corridor']),
        'in_full_port': sum(1 for L in lights if L['group'] == grp and L['in_full_port']),
    }

doc = {
    'source': 'BeamNG map C1 Tokyo Expressway Shutokow — light actors',
    'archive': ZIP,
    'frames': {
        'bng_m': 'BeamNG level metres (X east, Y north, Z up)',
        'ue_cm': 'Motor Town / Unreal: (x*100, -y*100, z*100)',
    },
    'counts': summary,
    'total': len(lights),
    'corridor_lamps': sum(1 for L in lights if L['in_corridor']),
    'loop_spacing': spacing,
    'recipe': recipe,
    'lights': lights,
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(doc, open(OUT, 'w'), indent=1)
print('wrote', OUT, os.path.getsize(OUT), 'B')
print('in corridor', doc['corridor_lamps'], 'of', doc['total'])
