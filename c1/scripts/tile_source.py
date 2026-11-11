"""Bake BeamNG Collada models into Motor Town cell tiles.

The original port's tile set (D:\\C1FullMirror\\meshes) was produced outside this repo and
the tool was never checked in, so the 554 shipped cells cannot be extended or reproduced.
This script re-implements the bake from first principles, using the inputs the port itself
uses:

  * ``levels/c1/main/missiongroup/prefabs/newprefab/items.level.json`` -- one line per placed
    model: ``shapeName`` (the .dae) and ``position`` (the model's bounds centre, already in
    BeamNG world metres). The mod author's QuickFixColladaPos.py re-origined every .dae to its
    bounds centre, so there is no rotation or scale to apply here: world = vertex + position.
  * the 3,575 ``.dae`` files under ``levels/c1/art/models``.

Tile convention (measured from the shipped cells, not assumed):
  * 500 m squares aligned to the grid, each tile named ``c<tile_x>_<tile_y>`` and keyed by
    ``floor(x / 500)`` / ``floor(y / 500)`` of the object position.
  * OBJ written in ABSOLUTE world metres, Z up, one ``usemtl`` group per Collada material
    symbol, faces triangulated, every face owning its three vertices (the shipped tiles are
    de-duplicated the same way: verts == 3 * faces).

The caller then runs rebase_obj.py to move each tile onto its own pivot. Nothing here decides
where a tile belongs in the level -- that stays with cell_origins.json and set_transforms.py.

Usage:
    python3 tile_source.py --tile c3_7 --out ref/c3_7_gen.obj     # single tile
    python3 tile_source.py --tiles-from report.json --outdir out/  # batch
    python3 tile_source.py --tile c3_7 --stats                    # counts only, no write
"""
import argparse
import collections
import json
import math
import sys
import zipfile
import xml.etree.ElementTree as ET

CELL = 500.0
MODELS_ROOT = 'levels/c1/art/models/'
LEVEL = 'levels/c1/main/missiongroup/prefabs/newprefab/items.level.json'


def _strip(tag):
    return tag.split('}', 1)[1] if '}' in tag else tag


def _children(el, name):
    return [c for c in el if _strip(c.tag) == name]


def _find(el, name):
    for c in el:
        if _strip(c.tag) == name:
            return c
    return None


def _floats(text):
    return [float(t) for t in text.split()]


def _mat_identity():
    return [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]


def _mat_mul(a, b):
    """Column-major 4x4 multiply, matching Collada's matrix layout."""
    out = [0.0] * 16
    for c in range(4):
        for r in range(4):
            out[c * 4 + r] = sum(a[k * 4 + r] * b[c * 4 + k] for k in range(4))
    return out


def _node_matrix(node):
    """Accumulate a node's transform into a single matrix (Collada order: T * R * S)."""
    m = _mat_identity()
    for child in node:
        tag = _strip(child.tag)
        if tag == 'matrix':
            vals = _floats(child.text or '')
            if len(vals) == 16:
                m = _mat_mul(m, vals)
        elif tag == 'translate':
            v = _floats(child.text or '')
            t = _mat_identity()
            t[12], t[13], t[14] = v[0], v[1], v[2]
            m = _mat_mul(m, t)
        elif tag == 'rotate':
            v = _floats(child.text or '')
            ang = math.radians(v[3])
            x, y, zz = v[0], v[1], v[2]
            n = math.sqrt(x * x + y * y + zz * zz) or 1.0
            x, y, zz = x / n, y / n, zz / n
            c, s = math.cos(ang), math.sin(ang)
            t = _mat_identity()
            t[0] = c + x * x * (1 - c); t[1] = y * x * (1 - c) + zz * s; t[2] = zz * x * (1 - c) - y * s
            t[4] = x * y * (1 - c) - zz * s; t[5] = c + y * y * (1 - c); t[6] = zz * y * (1 - c) + x * s
            t[8] = x * zz * (1 - c) + y * s; t[9] = y * zz * (1 - c) - x * s; t[10] = c + zz * zz * (1 - c)
            m = _mat_mul(m, t)
        elif tag == 'scale':
            v = _floats(child.text or '')
            t = _mat_identity()
            t[0], t[5], t[10] = v[0], v[1], v[2]
            m = _mat_mul(m, t)
    return m


def _apply(m, x, y, z):
    return (m[0] * x + m[4] * y + m[8] * z + m[12],
            m[1] * x + m[5] * y + m[9] * z + m[13],
            m[2] * x + m[6] * y + m[10] * z + m[14])


class Mesh(object):
    """One Collada geometry: positions, uvs, normals and triangles with material symbols."""

    def __init__(self):
        self.pos = []
        self.uv = []
        self.nrm = []
        self.tris = []          # list of ((p, t, n) * 3, symbol)

    def apply_matrix(self, m):
        self.pos = [_apply(m, *p) for p in self.pos]


def parse_dae(path, raw):
    root = ET.fromstring(raw)
    geoms = {}
    for g in root.iter():
        if _strip(g.tag) != 'geometry':
            continue
        gid = g.get('id')
        mesh_el = _find(g, 'mesh')
        if mesh_el is None or gid is None:
            continue
        sources = {}
        vertices_map = {}
        for src in _children(mesh_el, 'source'):
            sid = src.get('id')
            fa = _find(src, 'float_array')
            if fa is not None and fa.text:
                sources[sid] = _floats(fa.text)
        for v in _children(mesh_el, 'vertices'):
            for inp in _children(v, 'input'):
                if inp.get('semantic') == 'POSITION':
                    vertices_map[v.get('id')] = (inp.get('source') or '')[1:]
        m = Mesh()
        prims = _children(mesh_el, 'triangles') + _children(mesh_el, 'polylist')
        if not prims:
            prims = [c for c in mesh_el if _strip(c.tag) in ('triangles', 'polylist')]
        for prim in prims:
            inputs = _children(prim, 'input')
            offs = {}
            for inp in inputs:
                sem = inp.get('semantic')
                if sem == 'TEXCOORD' and inp.get('set') not in (None, '0'):
                    continue          # keep UV set 0; later sets share the same offset
                offs[sem] = (int(inp.get('offset', '0')), inp.get('source', '')[1:])
            stride = max(o for o, _ in offs.values()) + 1 if offs else 1
            v_off, v_id = offs.get('VERTEX', (0, None))
            p_src = vertices_map.get(v_id) or v_id
            pdat = sources.get(p_src, [])
            uv_off, uv_src = offs.get('TEXCOORD', (None, None))
            n_off, n_src = offs.get('NORMAL', (None, None))
            uvdat = sources.get(uv_src, []) if uv_src else []
            ndat = sources.get(n_src, []) if n_src else []
            symbol = prim.get('material') or ''
            idx_el = _find(prim, 'p')
            if idx_el is None or not idx_el.text:
                continue
            idx = [int(t) for t in idx_el.text.split()]
            if _strip(prim.tag) == 'triangles':
                count = int(prim.get('count', '0'))
                tri_idx = [idx[i:i + 3 * stride] for i in range(0, len(idx), 3 * stride)][:count or None]
            else:
                vcount = [int(t) for t in (_find(prim, 'vcount').text or '').split()]
                tri_idx = []
                ptr = 0
                for n in vcount:
                    base = idx[ptr:ptr + n * stride]
                    ptr += n * stride
                    for k in range(1, n - 1):
                        tri_idx.append(base[0:stride] + base[k * stride:(k + 1) * stride]
                                       + base[(k + 1) * stride:(k + 2) * stride])
            for tri in tri_idx:
                corners = []
                for c in range(3):
                    blk = tri[c * stride:(c + 1) * stride]
                    def take(o, dat):
                        if o is None or o >= len(blk):
                            return None
                        i = blk[o]
                        if dat and 3 * i + 2 < len(dat):
                            return (dat[3 * i], dat[3 * i + 1], dat[3 * i + 2])
                        return None
                    p = take(v_off, pdat)
                    if p is None:
                        corners = None
                        break
                    corners.append((p, take(uv_off, uvdat), take(n_off, ndat)))
                if corners:
                    m.tris.append((tuple(corners), symbol))
        geoms[gid] = m

    # visual scene: find instance_geometry nodes and their accumulated transforms
    instances = []
    scene = None
    for el in root.iter():
        if _strip(el.tag) == 'visual_scene':
            scene = el
            break

    def walk(node, parent_m):
        m = _mat_mul(parent_m, _node_matrix(node))
        for c in node:
            tag = _strip(c.tag)
            if tag == 'node':
                walk(c, m)
            elif tag == 'instance_geometry':
                url = (c.get('url') or '').lstrip('#')
                if url in geoms:
                    sym_map = {}
                    bm = _find(c, 'bind_material')
                    if bm is not None:
                        for tc in bm.iter():
                            if _strip(tc.tag) == 'instance_material':
                                sym_map[tc.get('symbol')] = (tc.get('target') or '').lstrip('#')
                    instances.append((url, m, sym_map))

    if scene is not None:
        for c in scene:
            if _strip(c.tag) == 'node':
                walk(c, _mat_identity())
    if not instances:                      # geometry with no scene node: use as authored
        for gid in geoms:
            instances.append((gid, _mat_identity(), {}))

    return [(geoms[gid], m, sym) for gid, m, sym in instances]


def bin_all(dae_reader, objs, targets, outdir):
    """One pass over every model, writing each face to its tile in the shipped OBJ format.

    Matches the layout of the existing cells exactly (measured on c3_7.obj): a one-line header,
    then per face ``usemtl <material>`` followed by three v/vt/vn triples and an ``f`` whose
    indices are all the same (every face owns its own vertices; verts == 3 * faces).
    """
    import os
    handles = {}
    counts = {}
    verts = {}
    for (tx, ty) in sorted(targets):
        name = 'c%d_%d' % (tx, ty)
        path = os.path.join(outdir, name + '.obj')
        f = open(path, 'w')
        f.write('# C1 corridor cell %d_%d (metres, Z-up)\n' % (tx, ty))
        handles[(tx, ty)] = (name, f)
        counts[(tx, ty)] = 0
        verts[(tx, ty)] = 0

    total = 0
    for shape, px, py, pz in objs:
        raw = dae_reader(shape)
        if raw is None:
            continue
        for mesh, m, sym_map in parse_dae(shape, raw):
            mesh.apply_matrix(m)
            for corners, symbol in mesh.tris:
                pts = [(c[0][0] + px, c[0][1] + py, c[0][2] + pz, c[1], c[2]) for c in corners]
                cx = sum(p[0] for p in pts) / 3.0
                cy = sum(p[1] for p in pts) / 3.0
                key = (int(math.floor(cx / CELL)), int(math.floor(cy / CELL)))
                ent = handles.get(key)
                if ent is None:
                    continue
                name, f = ent
                mat = sym_map.get(symbol, symbol) or 'default'
                f.write('usemtl %s\n' % mat)
                base = verts[key] + 1
                for (x, y, z, uv, nrm) in pts:
                    f.write('v %.3f %.3f %.3f\n' % (x, y, z))
                    if uv:
                        f.write('vt %.5f %.5f\n' % (uv[0], uv[1]))
                    else:
                        f.write('vt 0.00000 0.00000\n')
                    if nrm:
                        f.write('vn %.4f %.4f %.4f\n' % (nrm[0], nrm[1], nrm[2]))
                    else:
                        f.write('vn 0.0000 0.0000 1.0000\n')
                f.write('f %d/%d/%d %d/%d/%d %d/%d/%d\n' % (
                    base, base, base, base + 1, base + 1, base + 1, base + 2, base + 2, base + 2))
                verts[key] += 3
                counts[key] += 1
                total += 1

    summary = []
    for key, (name, f) in handles.items():
        f.close()
        summary.append({'tile': name, 'faces': counts[key], 'verts': verts[key]})
    return summary, total


def build_tile(dae_reader, objects, stats_only=False):
    out = []          # (symbol, [(p,t,n) x3])
    for shape, px, py, pz in objects:
        raw = dae_reader(shape)
        if raw is None:
            continue
        for mesh, m, sym_map in parse_dae(shape, raw):
            mesh.apply_matrix(m)
            for corners, symbol in mesh.tris:
                name = sym_map.get(symbol, symbol) or 'default'
                out.append((name, [(c[0][0] + px, c[0][1] + py, c[0][2] + pz,
                                    c[1], c[2]) for c in corners]))
    stats = {'faces': len(out), 'materials': len({n for n, _ in out})}
    if stats_only:
        return [], stats
    tris_by_mat = {}
    for name, c in out:
        tris_by_mat.setdefault(name, []).append(c)
    lines = []
    vcount = 0
    for name in sorted(tris_by_mat):
        lines.append('usemtl %s' % name)
        for c in tris_by_mat[name]:
            lines.append('f %d %d %d' % (vcount + 1, vcount + 2, vcount + 3))
            for (x, y, z, uv, nrm) in c:
                lines.append('v %.4f %.4f %.4f' % (x, y, z))
            vcount += 3
    stats['verts'] = vcount
    return lines, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default='/opt/data/inbox/c1src/c1_src.zip')
    ap.add_argument('--tile', help='tile name, e.g. c3_7')
    ap.add_argument('--bin-test', help='tile name; bin faces by centroid across all models and report')
    ap.add_argument('--tiles-from', help='JSON report with rows: tile_x, tile_y')
    ap.add_argument('--bin-missing', action='store_true', help='write every face whose tile has no existing cell')
    ap.add_argument('--existing', default='/opt/data/cache/scratch/cell_origins_v2.json', help='JSON whose keys are cell names')
    ap.add_argument('--bin-all', action='store_true', help='one-pass write of every tile in --tiles-from')
    ap.add_argument('--out', help='output .obj for --tile')
    ap.add_argument('--outdir', help='output dir for --tiles-from')
    ap.add_argument('--stats', action='store_true')
    args = ap.parse_args()

    z = zipfile.ZipFile(args.src)
    names = set(z.namelist())
    cache = {}

    def reader(shape):
        key = shape.lstrip('/')
        if key in cache:
            return cache[key]
        data = z.read(key) if key in names else None
        cache[key] = data
        return data

    objs = []
    for line in z.read(LEVEL).split(b'\n'):
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        p = o.get('position')
        if p:
            objs.append((o['shapeName'], p[0], p[1], p[2]))

    def in_tile(o, tx, ty):
        return (int(math.floor(o[1] / CELL)) == tx and int(math.floor(o[2] / CELL)) == ty)

    def bin_test(tx, ty):
        """Tile by TRIANGLE CENTROID over every placed model, not by object position.

        The shipped tiles carry geometry from models whose bounds centre sits in a neighbouring
        tile (a long road segment crossing the boundary), so the bake must have binned faces, not
        objects. This mode reproduces that and reports the resulting counts without writing.
        """
        lo_x, lo_y = tx * CELL, ty * CELL
        hi_x, hi_y = lo_x + CELL, lo_y + CELL
        keep = []
        done = 0
        for shape, px, py, pz in objs:
            raw = reader(shape)
            if raw is None:
                continue
            done += 1
            if done % 250 == 0:
                print('  ... %d/%d models, %d faces so far' % (done, len(objs), len(keep)), flush=True)
            for mesh, m, sym_map in parse_dae(shape, raw):
                mesh.apply_matrix(m)
                for corners, symbol in mesh.tris:
                    xs = [c[0][0] + px for c in corners]
                    ys = [c[0][1] + py for c in corners]
                    cx = sum(xs) / 3.0
                    cy = sum(ys) / 3.0
                    if lo_x <= cx < hi_x and lo_y <= cy < hi_y:
                        name = sym_map.get(symbol, symbol) or 'default'
                        keep.append((name, [(c[0][0] + px, c[0][1] + py, c[0][2] + pz,
                                             c[1], c[2]) for c in corners]))
        mats = len({n for n, _ in keep})
        print('tile c%d_%d by centroid: faces=%d materials=%d' % (tx + 1, -ty, len(keep), mats))
        if keep:
            mn = [min(p[i] for _, c in keep for p in c) for i in range(3)]
            mx = [max(p[i] for _, c in keep for p in c) for i in range(3)]
            print('bbox x %.1f..%.1f  y %.1f..%.1f  z %.1f..%.1f' % (
                mn[0], mx[0], mn[1], mx[1], mn[2], mx[2]))
        print('BIN_TEST_DONE')

    if args.bin_test:
        tx, ty = [int(v) for v in args.bin_test[1:].split('_')]
        bin_test(tx, ty)
        return

    if args.tile:
        tx, ty = [int(v) for v in args.tile[1:].split('_')]
        sel = [o for o in objs if in_tile(o, tx, ty)]
        lines, stats = build_tile(reader, sel, args.stats)
        print('tile %s: objects=%d faces=%d verts=%d materials=%d' % (
            args.tile, len(sel), stats['faces'], stats.get('verts', 0), stats['materials']))
        if lines and args.out:
            with open(args.out, 'w') as f:
                f.write('\n'.join(lines) + '\n')
            print('wrote %s' % args.out)
        return

    if args.bin_missing:
        existing = set()
        for n in json.load(open(args.existing)):
            if n == 'uvquad':
                continue
            try:
                i, j = [int(v) for v in n[1:].split('_')]
            except Exception:
                continue
            existing.add((i, j))
        import os
        os.makedirs(args.outdir, exist_ok=True)
        handles = {}
        counts = collections.Counter()
        verts = collections.Counter()

        def handle(key):
            h = handles.get(key)
            if h is None:
                path = os.path.join(args.outdir, 'c%d_%d.obj' % key)
                h = open(path, 'w')
                h.write('# C1 corridor cell %d_%d (metres, Z-up)\n' % key)
                handles[key] = h
            return h

        for shape, px, py, pz in objs:
            raw = reader(shape)
            if raw is None:
                continue
            for mesh, m, sym_map in parse_dae(shape, raw):
                mesh.apply_matrix(m)
                for corners, symbol in mesh.tris:
                    pts = [(c[0][0] + px, c[0][1] + py, c[0][2] + pz, c[1], c[2]) for c in corners]
                    key = (int(math.floor(sum(p[0] for p in pts) / 3.0 / CELL)),
                           int(math.floor(sum(p[1] for p in pts) / 3.0 / CELL)))
                    if key in existing:
                        continue
                    f = handle(key)
                    f.write('usemtl %s\n' % (sym_map.get(symbol, symbol) or 'default'))
                    base = verts[key] + 1
                    for (x, y, z, uv, nrm) in pts:
                        f.write('v %.3f %.3f %.3f\n' % (x, y, z))
                        f.write('vt %.5f %.5f\n' % (uv[0], uv[1]) if uv else 'vt 0.00000 0.00000\n')
                        f.write('vn %.4f %.4f %.4f\n' % (nrm[0], nrm[1], nrm[2]) if nrm else 'vn 0.0000 0.0000 1.0000\n')
                    f.write('f %d/%d/%d %d/%d/%d %d/%d/%d\n' % (
                        base, base, base, base + 1, base + 1, base + 1, base + 2, base + 2, base + 2))
                    verts[key] += 3
                    counts[key] += 1

        for key, f in handles.items():
            f.close()
        rows = [{'tile': 'c%d_%d' % k, 'faces': v, 'verts': verts[k]} for k, v in counts.items()]
        rows.sort(key=lambda r: -r['faces'])
        for r in rows[:15]:
            print('  %-12s faces=%-8d verts=%d' % (r['tile'], r['faces'], r['verts']))
        print('missing tiles with geometry: %d  total faces: %d' % (len(rows), sum(counts.values())))
        with open(os.path.join(args.outdir, 'summary.json'), 'w') as f:
            json.dump({'tiles': rows, 'total_faces': sum(counts.values())}, f, indent=1)
        return

    if args.bin_all:
        report = json.load(open(args.tiles_from))
        targets = {(int(r['tile_x']), int(r['tile_y'])) for r in report['rows']}
        import os
        os.makedirs(args.outdir, exist_ok=True)
        summary, total = bin_all(reader, objs, targets, args.outdir)
        summary.sort(key=lambda s: -s['faces'])
        empty = [s for s in summary if s['faces'] == 0]
        for s in summary[:15]:
            print('  %-10s faces=%-8d verts=%d' % (s['tile'], s['faces'], s['verts']))
        print('tiles written=%d  empty=%d  total faces=%d' % (len(summary), len(empty), total))
        with open(os.path.join(args.outdir, 'summary.json'), 'w') as f:
            json.dump({'tiles': summary, 'total_faces': total}, f, indent=1)
        return

    if args.tiles_from:
        report = json.load(open(args.tiles_from))
        for row in report['rows']:
            tx, ty = row['tile_x'], row['tile_y']
            name = 'c%d_%d' % (tx + 1, -ty)      # same naming the origin files use
            sel = [o for o in objs if in_tile(o, tx, ty)]
            lines, stats = build_tile(reader, sel)
            if not lines:
                print('%s: EMPTY, skipped' % name)
                continue
            path = '%s/%s.obj' % (args.outdir.rstrip('/'), name)
            with open(path, 'w') as f:
                f.write('\n'.join(lines) + '\n')
            print('%s: objects=%d faces=%d verts=%d materials=%d' % (
                name, len(sel), stats['faces'], stats.get('verts', 0), stats['materials']))
        return

    print('nothing to do')


if __name__ == '__main__':
    sys.exit(main())
