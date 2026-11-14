#!/usr/bin/env python3
"""Inventory the C1 road markings (kanji / lane text paint) and their collision.

Source: the marking meshes are NOT decals. Each one is its own TSStatic pointing at a
single-geometry .dae whose material is `mat_kbs_*` or `mat_mj_*`. They are then merged into
the port's cell meshes as ordinary material sections.

Answers the question "do the markings have colliders in the source?" with evidence:
the TSStatic `collisionType` field, which BeamNG documents as:
  None | Bounds | Collision Mesh | Visible Mesh | Visible Mesh Final
`Visible Mesh Final` = rendered mesh polygons are the collider, intentionally.

Writes c1/source/c1_source_markings.json and prints a summary.
"""
import collections
import json
import os
import re
import sys
import zipfile

ZIP = '/opt/data/inbox/c1src/c1_src.zip'
C1 = '/opt/data/cache/scratch/c1'
OUT = sys.argv[1] if len(sys.argv) > 1 else '/opt/data/workspace/mt-pak-wt-c1commit/c1/source/c1_source_markings.json'

z = zipfile.ZipFile(ZIP)
MARK = re.compile(r'mat_(kbs|mj)_')


def jsonl(p):
    out = []
    for line in z.read(p).decode('utf-8', 'replace').splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


# ---- 1. which .dae files are markings ------------------------------------------------
marking_dae = {}
for i in z.infolist():
    if not i.filename.endswith('.dae') or i.file_size > 200000:
        continue
    body = z.read(i.filename).decode('utf-8', 'replace')
    mats = sorted(set(re.findall(r'mat_((?:kbs|mj)_[A-Za-z0-9_]+)-material', body)))
    if not mats:
        continue
    # slab thickness + footprint of the single marking geometry
    m = re.search(r'positions-array" count="(\d+)">([^<]+)<', body)
    verts = []
    if m:
        nums = [float(x) for x in m.group(2).split()]
        verts = [nums[k:k + 3] for k in range(0, len(nums), 3)]
    th = round(max(v[2] for v in verts) - min(v[2] for v in verts), 4) if verts else None
    wx = round(max(v[0] for v in verts) - min(v[0] for v in verts), 3) if verts else None
    wy = round(max(v[1] for v in verts) - min(v[1] for v in verts), 3) if verts else None
    marking_dae[i.filename] = {'materials': mats, 'thickness_units': th,
                               'footprint_units': [wx, wy]}

# ---- 2. the TSStatic instances that draw them ----------------------------------------
ts = []
for p in z.namelist():
    if p.endswith('.prefab.json') or p.endswith('/items.level.json'):
        ts += [o for o in jsonl(p) if o.get('class') == 'TSStatic']
inst = []
for o in ts:
    shape = (o.get('shapeName') or '').lstrip('/')
    if shape in marking_dae:
        inst.append({
            'shape': shape,
            'route': shape.split('/')[-2],
            'collisionType': o.get('collisionType'),
            'decalType': o.get('decalType'),
            'materials': marking_dae[shape]['materials'],
        })

# ---- 3. how they land in the ported cells --------------------------------------------
cells = json.load(open(f'{C1}/cells_full_manifest.json'))['cells']
port = collections.defaultdict(list)
for c in cells:
    for m in c['materials']:
        if MARK.match(m):
            port[c['cell']].append(m)

summary = {
    'source': ZIP,
    'marking_meshes': len(marking_dae),
    'instances': len(inst),
    'by_route': dict(collections.Counter(i['route'] for i in inst)),
    'collision_types': dict(collections.Counter(i['collisionType'] for i in inst)),
    'distinct_materials': len({m for d in marking_dae.values() for m in d['materials']}),
    'port_cells_with_markings': len(port),
    'port_marking_slots': sum(len(v) for v in port.values()),
    'slab_thickness_units': sorted({d['thickness_units'] for d in marking_dae.values()}),
}
print(json.dumps(summary, indent=1))
print('\ncells with the most markings:',
      sorted(((c, len(v)) for c, v in port.items()), key=lambda t: -t[1])[:6])

json.dump({'summary': summary,
           'marking_meshes': marking_dae,
           'instances': inst,
           'port_cells': {k: sorted(set(v)) for k, v in port.items()}},
          open(OUT, 'w'), indent=1)
print('wrote', OUT, os.path.getsize(OUT), 'B')
