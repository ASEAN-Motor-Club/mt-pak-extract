#!/usr/bin/env python3
"""Report/fix winding of closed shell islands in an OBJ.

An island is 'closed' when every welded undirected edge is used by exactly two
faces. Closed islands with negative signed volume are inside-out; flip them.
Open islands (bands, slabs, single quads) are left alone.

Usage: python3 check_winding.py in.obj [out.obj]   (no out.obj = report only)
"""
import sys
from collections import defaultdict


def load(path):
    verts, faces = [], []
    for line in open(path):
        p = line.split()
        if p and p[0] == 'v':
            verts.append(tuple(float(x) for x in p[1:4]))
        elif p and p[0] == 'f':
            faces.append([int(t.split('/')[0]) - 1 for t in p[1:]])
    return verts, faces


def welded(v, i):
    return tuple(round(c, 3) for c in v[i])


def analyse(v, f):
    """-> list of islands, each a list of face indices."""
    kmap = {}
    keys = []
    for fa in f:
        ks = []
        for i in fa:
            k = welded(v, i)
            kmap.setdefault(k, len(kmap))
            ks.append(kmap[k])
        keys.append(ks)

    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def uni(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for ks in keys:
        for a, b in zip(ks, ks[1:]):
            uni(a, b)
    groups = defaultdict(list)
    for idx, ks in enumerate(keys):
        groups[find(ks[0])].append(idx)
    return list(groups.values()), keys


def is_closed(face_idx, f, keys):
    if len(face_idx) < 4:
        return False
    und = defaultdict(int)
    for idx in face_idx:
        ks = keys[idx]
        for a, b in zip(ks, ks[1:] + ks[:1]):
            und[(min(a, b), max(a, b))] += 1
    return all(c == 2 for c in und.values())


def signed_vol(v, f, face_idx):
    vol = 0.0
    for idx in face_idx:
        fa = f[idx]
        a, b, c = (v[i] for i in fa[:3])
        vol += (a[0] * (b[1] * c[2] - b[2] * c[1])
                - a[1] * (b[0] * c[2] - b[2] * c[0])
                + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
    return vol


def main():
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else None
    v, f = load(src)
    groups, keys = analyse(v, f)
    flipped = 0
    for gi, idxs in enumerate(groups):
        closed = is_closed(idxs, f, keys)
        sv = signed_vol(v, f, idxs)
        bad = closed and sv < 0
        xs = [v[i][0] for idx in idxs for i in f[idx]]
        zs = [v[i][2] for idx in idxs for i in f[idx]]
        print(f'island {gi:2d} {"closed" if closed else "open  "} '
              f'faces={len(idxs):3d} vol={sv:+12.0f} '
              f'x {min(xs):.0f}..{max(xs):.0f} z {min(zs):.0f}..{max(zs):.0f}'
              + ('  <-- FLIP' if bad else ''))
        if bad:
            for idx in idxs:
                f[idx] = list(reversed(f[idx]))
            flipped += 1
    print(f'{flipped} island(s) flipped, {len(f)} faces total')
    if dst and flipped:
        with open(dst, 'w') as fh:
            fh.write('# procedural rear body for the Duro, UE cm, importer scale 1\n')
            fh.write('usemtl CargoBed_01\n')
            for p in v:
                fh.write('v %.4f %.4f %.4f\n' % p)
            for _ in v:
                fh.write('vt 0.000000 0.000000\n')
            for fa in f:
                fh.write('f ' + ' '.join(f'{i + 1}/{i + 1}' for i in fa) + '\n')
        print('wrote', dst)


if __name__ == '__main__':
    main()
