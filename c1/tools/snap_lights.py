"""Snap street-light positions onto the actual lamp-head geometry in the ported meshes.

Why: the level import is correct (verified 0.8 m XY / 0.08 m Z against matched fixtures), but a
light records the *node* position, while the visible fitting is mesh geometry. In multi-deck areas
(Shibaura stacks three decks between z 869 and 895 m) a light can look detached from the pole the
player is looking at.

Method: per cell OBJ, take every face whose material is lamp-like, union-find the shared vertices
into connected components, and use each component's centroid as a fixture anchor. Then snap each
light to the nearest anchor within dXY_MAX, rejecting matches whose |dZ| exceeds DZ_MAX so a lamp
cannot jump to the deck above.

Usage:
    python3 snap_lights.py rows.json out.json [cells_dir]
rows.json is a list of {name, ue_cm:[x,y,z]} in MT centimetres.
"""
import collections
import json
import math
import os
import sys

DXY_MAX = 4.0      # metres
DZ_MAX = 1.5       # metres - the anti-deck-jump guard
LAMP_TOKENS = ("lamp",)


def lamp_components(obj_path):
    """Connected components of lamp-material geometry -> list of (cx,cy,cz,nverts) in metres."""
    verts = []
    parent = []

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    cur = None
    edges = []
    for line in open(obj_path, errors="ignore"):
        if line.startswith("v "):
            x, y, z = map(float, line.split()[1:4])
            verts.append((x, y, z))
            parent.append(len(verts) - 1)
        elif line.startswith("usemtl"):
            parts = line.split(None, 1)
            cur = parts[1].strip() if len(parts) > 1 else "?"
        elif line.startswith("f ") and cur and any(t in cur.lower() for t in LAMP_TOKENS):
            idx = [int(tok.split("/")[0]) - 1 for tok in line.split()[1:]]
            for a, b in zip(idx, idx[1:]):
                if 0 <= a < len(verts) and 0 <= b < len(verts):
                    edges.append((a, b))

    for a, b in edges:
        union(a, b)

    groups = collections.defaultdict(list)
    for a, _b in edges:
        groups[find(a)].append(a)
    out = []
    for _root, members in groups.items():
        uniq = set(members)
        if len(uniq) < 8:          # ignore slivers
            continue
        xs = sum(verts[i][0] for i in uniq) / len(uniq)
        ys = sum(verts[i][1] for i in uniq) / len(uniq)
        zs = sum(verts[i][2] for i in uniq) / len(uniq)
        out.append((xs, ys, zs, len(uniq)))
    return out


def main():
    rows_path, out_path = sys.argv[1], sys.argv[2]
    cells_dir = sys.argv[3] if len(sys.argv) > 3 else "/opt/data/cache/scratch/c1/cells_full"
    rows = json.load(open(rows_path))

    cache = {}
    stats = {"snapped": 0, "kept": 0, "no_cell_obj": 0, "no_fixture": 0}
    for r in rows:
        x, y, z = r["ue_cm"][0] / 100.0, -r["ue_cm"][1] / 100.0, r["ue_cm"][2] / 100.0
        cell = "c%d_%d" % (math.floor(x / 500.0), math.floor(y / 500.0))
        if cell not in cache:
            p = os.path.join(cells_dir, cell + ".obj")
            cache[cell] = lamp_components(p) if os.path.exists(p) else None
        comps = cache[cell]
        if comps is None:
            stats["no_cell_obj"] += 1
            continue
        best = None
        for cx, cy, cz, _n in comps:
            dxy = math.hypot(cx - x, cy - y)
            dz = abs(cz - z)
            if dxy <= DXY_MAX and dz <= DZ_MAX:
                if best is None or dxy < best[0]:
                    best = (dxy, cx, cy, cz)
        if best is None:
            stats["no_fixture"] += 1
            continue
        r["snap"] = {"dxy_m": round(best[0], 2), "dxy_from": [round(x, 2), round(y, 2), round(z, 2)]}
        r["ue_cm"] = [round(best[1] * 100.0, 1), round(-best[2] * 100.0, 1), round(best[3] * 100.0, 1)]
        stats["snapped"] += 1

    json.dump(rows, open(out_path, "w"), indent=1)
    print("SNAP", json.dumps(stats), "->", out_path)


if __name__ == "__main__":
    main()
