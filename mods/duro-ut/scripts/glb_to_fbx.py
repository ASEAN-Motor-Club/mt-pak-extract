#!/usr/bin/env python3
"""glb_to_fbx.py — convert a Motor Town vehicle GLB into an ASCII FBX that keeps
every vertex attribute the game's materials depend on.

The OBJ route only carried POSITION + TEXCOORD_0; MT vehicle meshes also use
NORMAL, COLOR_0 and TEXCOORD_1..7 for paint masks and tinting. Losing them makes
the truck render flat grey, so the import path goes through FBX instead.

Coordinates: glTF (metres, Y-up) -> UE cm (X length, Y width, Z up):
    X = gx*100, Y = -gz*100, Z = gy*100
FBX is written with UpAxis=Z so Unreal imports the numbers unchanged.

Usage:
  python3 glb_to_fbx.py --glb Body.glb --slots slots.txt --out Body.fbx \
      [--bed-x -62] [--bed-z 86] [--tail-cut-x -300] [--keep-bed]
"""
import argparse
import json
import struct

CT = {5120: ('b', 1), 5121: ('B', 1), 5122: ('h', 2),
      5123: ('H', 2), 5125: ('I', 4), 5126: ('f', 4)}
NC = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}

BED_CUT_X = -62.0
BED_CUT_Z = 86.0
LIGHT_SECS = {4, 5, 6, 7, 8, 9, 10, 12, 14, 15}
UV_SETS = 8


def load_glb(path):
    b = open(path, 'rb').read()
    off, js, binary = 12, None, None
    while off < len(b):
        ln, ty = struct.unpack_from('<II', b, off)
        chunk = b[off + 8: off + 8 + ln]
        if ty == 0x4E4F534A:
            js = json.loads(chunk)
        elif ty == 0x004E4942:
            binary = chunk
        off += 8 + ln + ((4 - ln % 4) % 4 if ln % 4 else 0)
    return js, binary


def acc(js, binary, idx):
    a = js['accessors'][idx]
    fmt, size = CT[a['componentType']]
    n = NC[a['type']]
    bv = js['bufferViews'][a['bufferView']]
    base = bv.get('byteOffset', 0) + a.get('byteOffset', 0)
    stride = bv.get('byteStride') or size * n
    return [struct.unpack_from('<' + fmt * n, binary, base + i * stride) for i in range(a['count'])]


def ue_pos(p):
    gx, gy, gz = p
    return (gx * 100.0, -gz * 100.0, gy * 100.0)


def ue_normal(n):
    gx, gy, gz = n
    return (gx, -gz, gy)


def gather(args):
    """Returns control points, per-corner indices, per-corner uv sets, colors,
    normals and a per-polygon material index."""
    slots = [s.strip() for s in open(args.slots) if s.strip()]
    js, binary = load_glb(args.glb)
    prims = js['meshes'][0]['primitives']
    assert len(prims) == len(slots), f'{len(prims)} primitives vs {len(slots)} slots'

    points, corner_uv, corner_col, corner_nrm, poly_mat = [], [], [], [], []
    key_to_idx = {}

    def key(cp):
        return cp  # fully-qualified tuple is already unique

    for si, prim in enumerate(prims):
        at = prim['attributes']
        pos = [ue_pos(p) for p in acc(js, binary, at['POSITION'])]
        nrm = [ue_normal(n) for n in acc(js, binary, at['NORMAL'])] if 'NORMAL' in at else [(0.0, 0.0, 1.0)] * len(pos)
        col = acc(js, binary, at['COLOR_0']) if 'COLOR_0' in at else [(1.0, 1.0, 1.0, 1.0)] * len(pos)
        uvs = []
        for u in range(UV_SETS):
            k = f'TEXCOORD_{u}'
            uvs.append(acc(js, binary, at[k]) if k in at else [(0.0, 0.0)] * len(pos))
        idx = [t[0] for t in acc(js, binary, prim['indices'])]

        for k in range(0, len(idx), 3):
            tri = idx[k:k + 3]
            cx = sum(pos[i][0] for i in tri) / 3.0
            cz = sum(pos[i][2] for i in tri) / 3.0
            is_bed = (si not in LIGHT_SECS) and (cx < args.bed_x) and (cz > args.bed_z)
            is_tail = (args.tail_cut_x is not None and si in (9, 14, 15)
                       and cx < args.tail_cut_x)
            if is_tail or (is_bed and not args.keep_bed):
                continue
            for i in tri:
                uvrow = tuple((uvs[u][i][0], uvs[u][i][1]) for u in range(UV_SETS))
                k2 = (pos[i], nrm[i], col[i], uvrow)
                got = key_to_idx.get(k2)
                if got is None:
                    got = len(points)
                    key_to_idx[k2] = got
                    points.append((pos[i], nrm[i], col[i], uvrow))
                corner_uv.append(got)
                corner_col.append(got)
                corner_nrm.append(got)
            poly_mat.append(si)
    return slots, points, corner_uv, poly_mat


def fbx(args):
    slots, points, corners, polymat = gather(args)
    N = len(points)
    print(f'slots={len(slots)} control points={N} corners={len(corners)} polys={len(polymat)}')

    # Every layer below is written ByPolygonVertex, so it must be sized and ordered
    # by polygon corner, not by control point. Deduplicated control points gave
    # arrays shorter than the corner list, which made the importer misindex them
    # (flat shading, wrong UVs). glTF v grows downwards, UE's grows upwards: flip.
    verts, nrm, col = [], [], []
    uvs = [[] for _ in range(UV_SETS)]
    for c in corners:
        p, n, cl, uvrow = points[c]
        verts.append(p)
        nrm.append(n)
        col.append(cl)
        for u in range(UV_SETS):
            uvs[u].append((uvrow[u][0], 1.0 - uvrow[u][1]))

    def arr(vals):
        return ','.join(f'{v:.6f}' for v in vals)

    with open(args.out, 'w', newline='\n') as f:
        w = f.write
        w('; FBX 7.4.0 project file\n')
        w('FBXHeaderExtension:  {\n')
        w('\tFBXHeaderVersion: 1003\n\tFBXVersion: 7400\n')
        w('\tCreator: "yumemi glb_to_fbx"\n}\n')
        w('GlobalSettings:  {\n\tVersion: 1000\n\tProperties70:  {\n')
        w('\t\tP: "UpAxis", "int", "Integer", "",2\n')
        w('\t\tP: "UpAxisSign", "int", "Integer", "",1\n')
        w('\t\tP: "FrontAxis", "int", "Integer", "",1\n')
        w('\t\tP: "FrontAxisSign", "int", "Integer", ",-1\n')
        w('\t\tP: "CoordAxis", "int", "Integer", "",0\n')
        w('\t\tP: "CoordAxisSign", "int", "Integer", "",1\n')
        w('\t\tP: "UnitScaleFactor", "double", "Number", "",1\n')
        w('\t}\n}\n')
        w('Definitions:  {\n\tVersion: 100\n')
        w(f'\tCount: {2 + len(slots)}\n')
        w('\tObjectType: "Model" {\n\t\tCount: 1\n\t}\n')
        w('\tObjectType: "Geometry" {\n\t\tCount: 1\n\t}\n')
        w(f'\tObjectType: "Material" {{\n\t\tCount: {len(slots)}\n\t}}\n}}\n')
        w('Objects:  {\n')

        w('\tGeometry: 100000, "Geometry::Body", "Mesh" {\n')
        flat = []
        for v in verts:
            flat.extend(v)
        w(f'\t\tVertices: *{len(flat)} {{\n\t\t\ta: {arr(flat)}\n\t\t}}\n')
        pvi = []
        for i in range(0, len(corners), 3):
            a, b, c = corners[i], corners[i + 1], corners[i + 2]
            pvi.extend([a, b, -(c + 1)])
        w(f'\t\tPolygonVertexIndex: *{len(pvi)} {{\n\t\t\ta: {",".join(str(x) for x in pvi)}\n\t\t}}\n')
        w('\t\tGeometryVersion: 124\n')

        fn = []
        for n in nrm:
            fn.extend(n)
        w('\t\tLayerElementNormal: 0 {\n\t\t\tVersion: 101\n\t\t\tName: ""\n')
        w('\t\t\tMappingInformationType: "ByPolygonVertex"\n')
        w('\t\t\tReferenceInformationType: "Direct"\n')
        w(f'\t\t\tNormals: *{len(fn)} {{\n\t\t\t\ta: {arr(fn)}\n\t\t\t}}\n\t\t}}\n')

        for u in range(UV_SETS):
            fu = []
            for t in uvs[u]:
                fu.extend(t)
            w(f'\t\tLayerElementUV: {u} {{\n\t\t\tVersion: 101\n\t\t\tName: "UVChannel_{u + 1}"\n')
            w('\t\t\tMappingInformationType: "ByPolygonVertex"\n')
            w('\t\t\tReferenceInformationType: "Direct"\n')
            w(f'\t\t\tUV: *{len(fu)} {{\n\t\t\t\ta: {arr(fu)}\n\t\t\t}}\n\t\t}}\n')

        fc = []
        for c in col:
            fc.extend((c[0], c[1], c[2], c[3] if len(c) > 3 else 1.0))
        w('\t\tLayerElementColor: 0 {\n\t\t\tVersion: 101\n\t\t\tName: "VertexColor"\n')
        w('\t\t\tMappingInformationType: "ByPolygonVertex"\n')
        w('\t\t\tReferenceInformationType: "Direct"\n')
        w(f'\t\t\tColors: *{len(fc)} {{\n\t\t\t\ta: {arr(fc)}\n\t\t\t}}\n\t\t}}\n')

        w('\t\tLayerElementMaterial: 0 {\n\t\t\tVersion: 101\n\t\t\tName: ""\n')
        w('\t\t\tMappingInformationType: "ByPolygon"\n')
        w('\t\t\tReferenceInformationType: "IndexToDirect"\n')
        w(f'\t\t\tMaterials: *{len(polymat)} {{\n\t\t\t\ta: {",".join(str(m) for m in polymat)}\n\t\t\t}}\n\t\t}}\n')

        w('\t\tLayer: 0 {\n\t\t\tVersion: 100\n')
        w('\t\t\tLayerElement:  {\n\t\t\t\tType: "LayerElementNormal"\n\t\t\t\tTypedIndex: 0\n\t\t\t}\n')
        for u in range(UV_SETS):
            w('\t\t\tLayerElement:  {\n\t\t\t\tType: "LayerElementUV"\n\t\t\t\tTypedIndex: %d\n\t\t\t}\n' % u)
        w('\t\t\tLayerElement:  {\n\t\t\t\tType: "LayerElementColor"\n\t\t\t\tTypedIndex: 0\n\t\t\t}\n')
        w('\t\t\tLayerElement:  {\n\t\t\t\tType: "LayerElementMaterial"\n\t\t\t\tTypedIndex: 0\n\t\t\t}\n')
        w('\t\t}\n\t}\n')

        w('\tModel: 200000, "Model::Body", "Mesh" {\n\t\tVersion: 232\n')
        w('\t\tProperties70:  {\n\t\t\tP: "Lcl Translation", "Lcl Translation", "", "A",0,0,0\n\t\t}\n')
        w('\t\tShading: T\n\t\tCulling: "CullingOff"\n\t}\n')

        for i, s in enumerate(slots):
            mid = 300000 + i
            w(f'\tMaterial: {mid}, "Material::{s}", "" {{\n\t\tVersion: 102\n')
            w('\t\tShadingModel: "phong"\n\t\tMultiLayer: 0\n\t}\n')

        w('}\n')
        w('Connections:  {\n')
        w('\tC: "OO", 200000, 0\n')
        w('\tC: "OO", 100000, 200000\n')
        for i, _ in enumerate(slots):
            w(f'\tC: "OO", {300000 + i}, 200000\n')
        w('}\n')

    print('wrote', args.out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--glb', required=True)
    ap.add_argument('--slots', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--keep-bed', action='store_true')
    ap.add_argument('--bed-x', type=float, default=BED_CUT_X)
    ap.add_argument('--bed-z', type=float, default=BED_CUT_Z)
    ap.add_argument('--tail-cut-x', type=float, default=None)
    fbx(ap.parse_args())


if __name__ == '__main__':
    main()
