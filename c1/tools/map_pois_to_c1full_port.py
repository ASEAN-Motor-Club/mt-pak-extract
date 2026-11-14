#!/usr/bin/env python3
"""Map every source spawn/POI onto the SHIPPED C1Full port.

Adds, per POI:
  port_cell, in_full_port (cell mesh ships in the C1Full pak),
  cell_origin_m, cell_actor_ue_cm, local_offset_cm,
  mesh nearest-vertex distance / Z / dz  -> proof the ported deck is really under the point.

Inputs
  c1/source/c1_source_spawns_pois.json                (from extract_source_spawns_pois.py)
  /opt/data/cache/scratch/c1/fullpak_cells.txt        (cell meshes listed in zzz_AMC_C1Full_v26_P.pak)
  /opt/data/cache/scratch/c1/cell_origins.json        (cell actor origins, metres)
  /opt/data/cache/scratch/c1/cells_full/<cell>.obj    (world-space cell geometry, metres)

Writes the same JSON back with a `port` block per POI + a `port_summary`.
"""
import json
import math
import os
import sys

C1 = '/opt/data/cache/scratch/c1'
SRC = sys.argv[1] if len(sys.argv) > 1 else '/opt/data/workspace/mt-pak-wt-c1commit/c1/source/c1_source_spawns_pois.json'
OUT = sys.argv[2] if len(sys.argv) > 2 else SRC
CELL = 500.0

shipped = {l.strip() for l in open(f'{C1}/fullpak_cells.txt') if l.strip()}
origins = {k: v for k, v in json.load(open(f'{C1}/cell_origins.json')).items()
           if k.startswith('c') and '_' in k and k[1:].split('_')[0].lstrip('-').isdigit()}


def cell_name(x, y):
    return f"c{math.floor(x / CELL)}_{math.floor(y / CELL)}"


def origin_of(cell):
    o = origins.get(cell)
    if o:
        return o
    col, row = cell[1:].split('_')
    return [int(col) * CELL, int(row) * CELL]


_cache = {}


def verts(cell):
    """[(x, y, z)] world metres for a cell OBJ, or None if the file is absent."""
    if cell in _cache:
        return _cache[cell]
    p = f'{C1}/cells_full/{cell}.obj'
    if not os.path.exists(p):
        _cache[cell] = None
        return None
    pts = []
    with open(p, 'rb') as fh:
        for line in fh:
            if line[:2] == b'v ':
                a = line.split()
                try:
                    pts.append((float(a[1]), float(a[2]), float(a[3])))
                except (IndexError, ValueError):
                    pass
    _cache[cell] = pts
    return pts


doc = json.load(open(SRC))
pois = doc['pois']

# group by nominal cell so each OBJ is read once
by_cell = {}
for p in pois:
    x, y, _ = p['bng_m']
    by_cell.setdefault(cell_name(x, y), []).append(p)

summary = {'pois': len(pois), 'cell_mesh_shipped': 0, 'on_ported_deck': 0, 'missing_cell': 0,
           'cells': len(by_cell), 'cells_shipped': 0}
for cell, group in sorted(by_cell.items()):
    pts = verts(cell)
    is_shipped = cell in shipped
    if is_shipped:
        summary['cells_shipped'] += 1
    ox, oy = origin_of(cell)
    for p in group:
        x, y, z = p['bng_m']
        blk = {
            'port_cell': cell,
            'in_full_port': is_shipped,
            'cell_actor_origin_m': [ox, oy],
            'cell_actor_ue_cm': [round(ox * 100, 1), round(-oy * 100, 1), 0.0],
            'cell_obj_present': pts is not None,
            'cell_actor_origin_note': 'origin from cell_origins.json, the build input of '
                                      'set_transforms.py; local-offset arithmetic is NOT '
                                      'derivable from the world-space OBJs, so use the world position',
        }
        if pts:
            best_d2, best = 1e18, None
            for vx, vy, vz in pts:
                d2 = (vx - x) ** 2 + (vy - y) ** 2
                if d2 < best_d2:
                    best_d2, best = d2, (vx, vy, vz)
            blk['mesh_nearest_vertex_m'] = round(math.sqrt(best_d2), 2)
            blk['mesh_z_m'] = round(best[2], 2)
            blk['dz_vs_mesh_m'] = round(z - best[2], 2)
            if blk['mesh_nearest_vertex_m'] <= 25 and abs(blk['dz_vs_mesh_m']) <= 5:
                blk['on_ported_deck'] = True
        blk.setdefault('on_ported_deck', False)
        p['port'] = blk
        summary['cell_mesh_shipped'] += int(is_shipped)
        summary['on_ported_deck'] += int(blk['on_ported_deck'])
        summary['missing_cell'] += int(not is_shipped)

doc['port_reference'] = {
    'pak': 'zzz_AMC_C1Full_v26_P.pak',
    'cells_shipped': len(shipped),
    'frame': "ue_cm = (x*100, -y*100, z*100) for every world position; cell actors sit at "
             "(cell_origins_m[0]*100, -cell_origins_m[1]*100, 0)",
    'deck_test': 'nearest cell-OBJ vertex within 25 m in XY and |dz| <= 5 m',
}
doc['port_summary'] = summary

json.dump(doc, open(OUT, 'w'), indent=1)
print('wrote', OUT)
print(json.dumps(summary, indent=1))
for p in pois:
    b = p['port']
    print(f"{p['kind']:16s} {p['name']:20s} cell={b['port_cell']:7s} ship={int(b['in_full_port'])} "
          f"deck={int(b['on_ported_deck'])} dVert={b.get('mesh_nearest_vertex_m')} "
          f"dzMesh={b.get('dz_vs_mesh_m')} ue={p['ue_cm']}")
