#!/usr/bin/env python3
"""Extract spawn points / POIs from the original BeamNG C1 (Shutoko) level archive
and convert them to Motor Town / Unreal coordinates.

Source archive: /opt/data/inbox/c1src/c1_src.zip  (levels/c1/... + gameplay/...)
Frame: BeamNG metres (X east, Y north, Z up, right-hand drive).
Port frame: UE cm = (x*100, -y*100, z*100)  [Y mirrored, metres->centimetres]

Writes <outdir>/c1_source_spawns_pois.json
"""
import json, math, os, sys, zipfile

ZIP = '/opt/data/inbox/c1src/c1_src.zip'
OUT = sys.argv[1] if len(sys.argv) > 1 else '.'
CELL = 500.0

z = zipfile.ZipFile(ZIP)


def rd(p):
    return z.read(p).decode('utf-8', errors='replace')


def items(p):
    return [json.loads(l) for l in rd(p).splitlines() if l.strip()]


def jfile(p):
    return json.loads(rd(p))


def ue(x, y, zc):
    return [round(x * 100, 1), round(-y * 100, 1), round(zc * 100, 1)]


def yaw_ue(m):
    """Derived heading, degrees. BeamNG row-major rotationMatrix; the port mirrors Y,
    so the UE yaw is the negation of the source heading. Derived, not yet in-game validated."""
    if not m or len(m) < 4:
        return None
    return round(math.degrees(math.atan2(-m[1], m[0])), 1)


# ---- shipped corridor cells (74) -------------------------------------------------
man = json.load(open('/opt/data/cache/scratch/c1/cells_manifest.json'))
corridor = set(man['cells'] and [c['cell'] for c in man['cells']])
road = json.load(open('/opt/data/cache/scratch/c1/c1_road_points.json'))  # UE cm, y positive = source y*100
road_m = [(p[0] / 100.0, p[1] / 100.0, p[2] / 100.0) for p in road]


def cell_of(x, y):
    return f"{math.floor(x / CELL)}_{math.floor(y / CELL)}"


def nearest_road(x, y, zc):
    best = (1e18, None)
    for rx, ry, rz in road_m:
        d2 = (rx - x) ** 2 + (ry - y) ** 2
        if d2 < best[0]:
            best = (d2, rz)
    return round(math.sqrt(best[0]), 1), round(zc - (best[1] or zc), 1)


# ---- source road network (305 DecalRoads, nodes are [x, y, z, width_m]) ----------
src_nodes = []
src_road_groups = []
for _n in z.namelist():
    if not _n.endswith('items.level.json'):
        continue
    for line in rd(_n).splitlines():
        line = line.strip()
        if not line.startswith('{'):
            continue
        o = json.loads(line)
        if o.get('class') != 'DecalRoad':
            continue
        src_road_groups.append((_n, o))
        for nd in o.get('nodes', []):
            src_nodes.append((nd[0], nd[1], nd[2], nd[3], o.get('__parent', '')))


def nearest_src_road(x, y):
    best_d2, best = 1e18, None
    for nx, ny, nz, w, grp in src_nodes:
        d2 = (nx - x) ** 2 + (ny - y) ** 2
        if d2 < best_d2:
            best_d2, best = d2, (nz, w, grp)
    nz, w, grp = best
    return round(math.sqrt(best_d2), 1), nz, w, grp


def enrich(name, kind, x, y, zc, extra=None):
    nr, dz = nearest_road(x, y, zc)
    rd_d, rd_z, rd_w, rd_grp = nearest_src_road(x, y)
    c = cell_of(x, y)
    o = {
        'name': name,
        'kind': kind,
        'bng_m': [round(x, 2), round(y, 2), round(zc, 3)],
        'ue_cm': ue(x, y, zc),
        'cell': c,
        'in_shipped_corridor': c in corridor,
        'dist_to_c1_loop_m': nr,
        'dz_vs_loop_m': dz,
        'dist_to_source_road_m': rd_d,
        'nearest_source_road': {
            'group': rd_grp,
            'z_m': round(rd_z, 2),
            'width_m': rd_w,
            'dz_m': round(zc - rd_z, 2),
        },
    }
    if extra:
        o.update(extra)
    return o


pois = []

# ---- 1. spawn spheres (the map's own spawn menu) ---------------------------------
info = jfile('levels/c1/info.json')
labels = {s['objectname']: s['translationId'] for s in info['spawnPoints']}
for it in items('levels/c1/main/missiongroup/playerdroppoints/items.level.json'):
    x, y, zc = it['position']
    pois.append(enrich(it['name'], 'spawn', x, y, zc, {
        'source_label': labels.get(it['name']),
        'is_default_spawn': it['name'] == info.get('defaultSpawnPointName'),
        'yaw_ue_derived': yaw_ue(it.get('rotationMatrix')),
        'spawn_radius_m': it.get('radius'),
        'raw_position': [round(v, 3) for v in it['position']],
    }))

# ---- 2. garages (main facility + the 4 garage prefab instances) ------------------
for it in items('levels/c1/main/missiongroup/garage_triggers/items.level.json'):
    if not it['name'].startswith('garage_entrance'):
        continue
    x, y, zc = it['position']
    pois.append(enrich(it['name'], 'garage_entrance', x, y, zc, {
        'yaw_ue_derived': yaw_ue(it.get('rotationMatrix')),
        'trigger_scale_m': [round(v, 2) for v in it.get('scale', [])],
    }))

for it in items('levels/c1/main/missiongroup/garage_marker/items.level.json'):
    x, y, zc = it['position']
    pois.append(enrich(f"garage_marker_{len([p for p in pois if p['kind']=='garage_marker'])+1}",
                       'garage_marker', x, y, zc, {
                           'yaw_ue_derived': yaw_ue(it.get('rotationMatrix')),
                           'marker_scale_m': [round(v, 3) for v in it.get('scale', [])],
                       }))

# ---- 3. garage-to-garage mission sites (the POIs the mission builders place) -----
g2g = jfile('gameplay/missions/c1/garagetogarage/globalinfo/garages.sites.json')
for p in g2g['parkingSpots']:
    x, y, zc = p['pos']
    pois.append(enrich(p['name'], 'g2g_garage_site', x, y, zc, {
        'source_parking_id': p['oldId'],
        'spot_amount': p.get('spotAmount'),
    }))

# ---- 4. city parking areas ------------------------------------------------------
city = jfile('levels/c1/city.sites.json')
for p in city['parkingSpots']:
    x, y, zc = p['pos']
    pois.append(enrich(p['name'], 'city_parking', x, y, zc, {
        'source_parking_id': p['oldId'],
        'spot_amount': p.get('spotAmount'),
    }))

# ---- 5. speed traps (map "features": speed traps) -------------------------------
traps = items('levels/c1/main/missiongroup/trap/items.level.json')
for i, it in enumerate(sorted(traps, key=lambda o: o['position'][0]), 1):
    x, y, zc = it['position']
    pois.append(enrich(f"speed_trap_{i}", 'speed_trap', x, y, zc, {
        'source_name': it['name'],
    }))

# ---- 6. tunnel portals (Zone/Portal volumes mark tunnel mouths) -----------------
zones = items('levels/c1/main/missiongroup/zones/items.level.json')
for it in zones:
    if it.get('class') != 'Portal':
        continue
    x, y, zc = it['position']
    pois.append(enrich(it['name'], 'tunnel_portal', x, y, zc, {}))

doc = {
    'source': 'BeamNG mod map "C1 Tokyo Expressway Shutokow" (levels/c1)',
    'archive': '/opt/data/inbox/c1src/c1_src.zip',
    'map_meta': {k: info.get(k) for k in ('title', 'size', 'biome', 'country', 'suitablefor',
                                          'features', 'authors', 'roadRules')},
    'frames': {
        'bng_m': 'BeamNG level metres, X east / Y north / Z up',
        'ue_cm': 'Motor Town / Unreal cm = (x*100, -y*100, z*100), Y mirrored',
    },
    'counts': {},
    'pois': pois,
}
for p in pois:
    doc['counts'][p['kind']] = doc['counts'].get(p['kind'], 0) + 1

os.makedirs(OUT, exist_ok=True)
path = os.path.join(OUT, 'c1_source_spawns_pois.json')
with open(path, 'w') as fh:
    json.dump(doc, fh, indent=1)

print('wrote', path)
print('counts', doc['counts'])
inb = [p for p in pois if p['in_shipped_corridor']]
print('inside shipped 74-cell corridor:', len(inb))
for p in pois:
    print(f"{p['kind']:16s} {p['name']:22s} bng={p['bng_m']} ue={p['ue_cm']} cell={p['cell']:6s} "
          f"in={int(p['in_shipped_corridor'])} dLoop={p['dist_to_c1_loop_m']} "
          f"dSrcRoad={p['dist_to_source_road_m']} dZ={p['nearest_source_road']['dz_m']} "
          f"{p.get('source_label') or ''}")
