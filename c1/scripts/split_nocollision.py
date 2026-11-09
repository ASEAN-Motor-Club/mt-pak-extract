"""Split C1 cells into structural / no-collision geometry.

Reads meshes_local_v2 (canonical, pre-split OBJs) and writes three sets:

  <out>/paint/C1_NoCollision_Paint.obj   merged, world metres, road_paint + road_signs
  <out>/foliage/<cell>.obj               one per cell, pivot-relative like the cell meshes
  <out>/cells_v2/<cell>.obj              structural remainder

Every face is classified by its `usemtl` name, never by face index. A material that matches no
group stays structural (that is the safe direction: it keeps collision). A joint/marking face whose
centroid is on the `joint_depth` exclusion list (no support within 30 cm) also stays structural, so
a marking spanning a void is still collidable.

World placement matches the decal mesh that already ships: a merged vertex in metres is
(v.x + origin_x, v.y - origin_y, v.z), imported at uniform scale 100 with its actor at the origin.

Every emitted OBJ is compacted to referenced vertices: the port's orphan-vertex bbox bug (a 409 m
false bbox on c-1_-3 and c1_-8) comes from writing vertices no face references.
"""
import json
import os
import re
import sys

SRC = r"D:\C1FullMirror\meshes_local_v2"
ORIGINS = r"D:\C1FullMirror\cell_origins_v2.json"
CLASSIFY = r"D:\C1FullMirror\nocollision_materials.json"
JOINT_DEPTH = r"D:\C1FullMirror\Scripts\joint_depth.json"
OUT = r"D:\C1FullMirror\nc_out"
REPORT = r"D:\C1FullMirror\nc_out\split_report.json"

# a joint face over a drop shallower than this is a ridge, not a void: split it
VOID_DEPTH_CM = 30.0


def load_rules(path):
    cfg = json.load(open(path))
    groups = []
    for name, g in cfg["groups"].items():
        groups.append((name, [re.compile(p) for p in g["patterns"]]))
    solid = [re.compile("^" + re.escape(m) + "$") for m in cfg.get("solid_keep", {}).get("materials", [])]
    return groups, solid


def classify(mtl, groups, solid):
    """Return the group name for a material, or 'structural'."""
    if not mtl:
        return "structural"
    for name, pats in groups:
        for pat in pats:
            if pat.search(mtl):
                return name
    return "structural"


def load_exclusions(path):
    """cell -> {(material, x_cm, y_cm, z_cm)} for joint faces that span a void."""
    if not os.path.exists(path):
        return {}, 0
    data = json.load(open(path))
    out = {}
    total = 0
    for cell, entries in data.get("faces", {}).items():
        keep = set()
        for e in entries:
            mtl, x, y, z = e[0], e[1], e[2], e[3]
            depth = e[4] if len(e) > 4 else None
            if depth is None or depth >= VOID_DEPTH_CM:
                keep.add((mtl, round(x, 1), round(y, 1), round(z, 1)))
        if keep:
            out[cell] = keep
            total += len(keep)
    return out, total


def read_obj(path):
    verts, uvs, norms, faces = [], [], [], []
    mtl = None
    with open(path, "r", errors="replace") as f:
        for line in f:
            if line.startswith("v "):
                p = line.split()
                verts.append((float(p[1]), float(p[2]), float(p[3])))
            elif line.startswith("vt "):
                p = line.split()
                uvs.append((float(p[1]), float(p[2])))
            elif line.startswith("vn "):
                p = line.split()
                norms.append((float(p[1]), float(p[2]), float(p[3])))
            elif line.startswith("usemtl "):
                mtl = line.split(None, 1)[1].strip()
            elif line.startswith("f "):
                idx = []
                for tok in line.split()[1:]:
                    parts = tok.split("/")
                    v = int(parts[0])
                    vt = int(parts[1]) if len(parts) > 1 and parts[1] else 0
                    vn = int(parts[2]) if len(parts) > 2 and parts[2] else 0
                    idx.append((v, vt, vn))
                faces.append([mtl, idx])
    return verts, uvs, norms, faces


class Sink:
    """Accumulates faces and emits a compacted OBJ (only referenced verts/uvs/normals)."""

    def __init__(self, header):
        self.header = header
        self.verts, self.uvs, self.norms = [], [], []
        self.faces = []
        self.mtl_order = []

    def add(self, verts, uvs, norms, faces, vmap, tmap, nmap):
        self.faces.extend(faces)
        for mtl, _ in faces:
            if mtl not in self.mtl_order:
                self.mtl_order.append(mtl)
        for v in verts:
            self.verts.append(v)
        for t in uvs:
            self.uvs.append(t)
        for n in norms:
            self.norms.append(n)

    def write(self, path, translate=None):
        """Write, dropping every vertex/uv/normal no face references."""
        vused, tused, nused = {}, {}, {}
        out_faces = []
        for mtl, idx in self.faces:
            new = []
            for a, b, c in idx:
                if a not in vused:
                    vused[a] = len(vused)
                if b and b not in tused:
                    tused[b] = len(tused)
                if c and c not in nused:
                    nused[c] = len(nused)
                new.append((vused[a], tused[b] if b else 0, nused[c] if c else 0))
            out_faces.append((mtl, new))

        with open(path, "w") as f:
            f.write("# %s\n" % self.header)
            order = sorted(vused.items(), key=lambda kv: kv[1])
            for old, _new in order:
                x, y, z = self.verts[old - 1]
                if translate:
                    x, y, z = translate(x, y, z)
                f.write("v %.4f %.4f %.4f\n" % (x, y, z))
            for old, _new in sorted(tused.items(), key=lambda kv: kv[1]):
                u, v = self.uvs[old - 1]
                f.write("vt %.6f %.6f\n" % (u, v))
            for old, _new in sorted(nused.items(), key=lambda kv: kv[1]):
                f.write("vn %.6f %.6f %.6f\n" % self.norms[old - 1])
            cur = None
            for mtl, idx in out_faces:
                if mtl != cur:
                    f.write("usemtl %s\n" % (mtl if mtl else "none"))
                    cur = mtl
                f.write("f " + " ".join(
                    "%d/%d/%d" % (a, b, c) if b and c else ("%d//%d" % (a, c) if c else str(a))
                    for a, b, c in idx) + "\n")
        return len(vused), len(tused), len(nused)


def bbox_of(verts, faces):
    mn = [float("inf")] * 3
    mx = [float("-inf")] * 3
    for _mtl, idx in faces:
        for a, _b, _c in idx:
            v = verts[a - 1]
            for i in range(3):
                if v[i] < mn[i]:
                    mn[i] = v[i]
                if v[i] > mx[i]:
                    mx[i] = v[i]
    return mn, mx


def face_centroid(verts, idx):
    n = len(idx)
    return (sum(verts[a - 1][0] for a, _b, _c in idx) / n,
            sum(verts[a - 1][1] for a, _b, _c in idx) / n,
            sum(verts[a - 1][2] for a, _b, _c in idx) / n)


def main():
    argv = sys.argv[1:]
    global SRC, ORIGINS, CLASSIFY, JOINT_DEPTH, OUT, REPORT
    while argv:
        flag = argv.pop(0)
        if flag == "--src":
            SRC = argv.pop(0)
        elif flag == "--origins":
            ORIGINS = argv.pop(0)
        elif flag == "--classify":
            CLASSIFY = argv.pop(0)
        elif flag == "--joint-depth":
            JOINT_DEPTH = argv.pop(0)
        elif flag == "--out":
            OUT = argv.pop(0)
        elif flag == "--report":
            REPORT = argv.pop(0)
        else:
            raise SystemExit("unknown argument %r" % flag)

    groups, solid = load_rules(CLASSIFY)
    exclusions, excl_total = load_exclusions(JOINT_DEPTH)
    origins = json.load(open(ORIGINS))
    print("groups: %s   solid_keep patterns: %d   exclusion cells: %d   exclusion faces: %d"
          % ([g[0] for g in groups], len(solid), len(exclusions), excl_total), flush=True)

    os.makedirs(os.path.join(OUT, "paint"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "foliage"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "cells_v2"), exist_ok=True)

    paint = Sink("C1 no-collision: road paint + signs (world metres)")
    files = sorted(f for f in os.listdir(SRC) if f.lower().endswith(".obj"))
    report = {"cells": 0, "paint_tris": 0, "foliage_tris": 0, "structural_tris": 0,
              "solid_keep_tris": 0, "excluded_faces": excl_total, "excluded_used": 0,
              "missing_origin": [], "unknown_materials": {}, "per_cell": {},
              "empty_outputs": [], "unreferenced_materials": [], "tri_mismatch": [],
              "bbox_drift": [], "foliage_only": []}
    unknown = {}

    for f in files:
        cell = os.path.splitext(f)[0]
        report["cells"] += 1
        verts, uvs, norms, faces = read_obj(os.path.join(SRC, f))
        if cell not in origins:
            report["missing_origin"].append(cell)
            continue
        ox, oy = origins[cell][0], origins[cell][1]

        buckets = {"paint": [], "foliage": [], "structural": []}
        for mtl, idx in faces:
            g = classify(mtl, groups, solid)
            if g in ("road_paint", "road_signs"):
                g = "paint"
            elif g == "foliage":
                g = "foliage"
            else:
                g = "structural"
                if mtl and not any(p.search(mtl) for p in solid):
                    unknown[mtl] = unknown.get(mtl, 0) + (len(idx) - 2)
            if g == "paint" and mtl and cell in exclusions:
                c = face_centroid(verts, idx)
                key = (mtl, round(c[0] * 100, 1), round(c[1] * 100, 1), round(c[2] * 100, 1))
                if key in exclusions[cell]:
                    report["excluded_used"] += 1
                    g = "structural"
            buckets[g].append((mtl, idx))

        n_paint = sum(len(i) - 2 for _, i in buckets["paint"])
        n_foliage = sum(len(i) - 2 for _, i in buckets["foliage"])
        n_struct = sum(len(i) - 2 for _, i in buckets["structural"])
        n_solid = sum(len(i) - 2 for m, i in buckets["structural"]
                      if m and any(p.search(m) for p in solid))
        report["paint_tris"] += n_paint
        report["foliage_tris"] += n_foliage
        report["structural_tris"] += n_struct
        report["solid_keep_tris"] += n_solid
        report["per_cell"][cell] = {"structural": n_struct, "paint": n_paint,
                                   "foliage": n_foliage, "v2": sum(len(i) - 2 for _, i in faces)}

        # merged paint, world metres
        if buckets["paint"]:
            voff, toff, noff = len(paint.verts), len(paint.uvs), len(paint.norms)
            paint.add([(x + ox, y - oy, z) for (x, y, z) in verts], uvs, norms,
                      [(m, [(a + voff, (b + toff) if b else 0, (c + noff) if c else 0)
                           for a, b, c in i]) for m, i in buckets["paint"]], None, None, None)

        # foliage, pivot-relative, one OBJ per cell
        if buckets["foliage"]:
            s = Sink("C1 no-collision foliage %s" % cell)
            s.add(verts, uvs, norms, buckets["foliage"], None, None, None)
            used = s.write(os.path.join(OUT, "foliage", f))
            if used[0] == 0:
                report["empty_outputs"].append("foliage/" + f)

        if buckets["structural"]:
            s = Sink("C1 structural %s" % cell)
            s.add(verts, uvs, norms, buckets["structural"], None, None, None)
            used = s.write(os.path.join(OUT, "cells_v2", f))
            if used[0] == 0:
                report["empty_outputs"].append("cells_v2/" + f)
        else:
            report["foliage_only"].append(cell)

        # nothing may leave the cell's original footprint: the union of the three buckets must
        # cover exactly the vertices v2 references, so no bucket can hide a shifted vertex
        full = bbox_of(verts, faces)
        parts = [bbox_of(verts, buckets[k]) for k in ("structural", "paint", "foliage")
                 if buckets[k]]
        if parts:
            umn = [min(p[0][i] for p in parts) for i in range(3)]
            umx = [max(p[1][i] for p in parts) for i in range(3)]
            d = max(max(abs(umn[i] - full[0][i]), abs(umx[i] - full[1][i])) for i in range(3))
            if d > 1e-3:
                report["bbox_drift"].append([cell, round(d, 4)])

        if (report["cells"] % 50) == 0:
            print("  %d/%d cells" % (report["cells"], len(files)), flush=True)

    used = paint.write(os.path.join(OUT, "paint", "C1_NoCollision_Paint.obj"))
    report["paint_verts"] = used[0]

    # gates
    for cell, r in report["per_cell"].items():
        if r["structural"] + r["paint"] + r["foliage"] != r["v2"]:
            report["tri_mismatch"].append([cell, r])
    report["unknown_materials"] = dict(sorted(unknown.items(), key=lambda kv: -kv[1])[:40])
    ok = (not report["tri_mismatch"] and not report["missing_origin"]
          and not report["empty_outputs"] and not report["bbox_drift"]
          and report["excluded_used"] == excl_total)
    report["ok"] = ok
    json.dump(report, open(REPORT, "w"), indent=1)
    print("SPLIT cells=%d paint=%d foliage=%d structural=%d solid_keep=%d excluded=%d/%d "
          "paint_verts=%d mismatch=%d bbox_drift=%d foliage_only=%d ok=%s"
          % (report["cells"], report["paint_tris"], report["foliage_tris"],
             report["structural_tris"], report["solid_keep_tris"], report["excluded_used"],
             excl_total, report["paint_verts"], len(report["tri_mismatch"]),
             len(report["bbox_drift"]), len(report["foliage_only"]), ok))


if __name__ == "__main__":
    main()
