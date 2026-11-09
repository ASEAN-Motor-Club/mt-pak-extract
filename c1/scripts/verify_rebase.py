"""Gate A1: prove meshes_local_v2 is a faithful rebase of the canonical cell export.

Emits a per-cell scan (`D:/C1FullMirror/v2_scan.json`) so the gate can be re-evaluated without
re-reading 5.6 GB, then applies the plan's checks.
"""
import json
import os
import sys

SRC = r"D:\C1FullMirror\meshes"
DST = r"D:\C1FullMirror\meshes_local_v2"
MANIFEST = r"D:\C1FullMirror\cells_full_manifest.json"
SCAN_OUT = r"D:\C1FullMirror\v2_scan.json"
TOL = 1e-3
NON_CELL = {"C1_Decals"}


def scan(path):
    tris = 0
    mats = set()
    mn = [float("inf")] * 3
    mx = [float("-inf")] * 3
    header = None
    with open(path, "r", errors="ignore") as f:
        for line in f:
            if line.startswith("v "):
                p = line.split()
                for i in range(3):
                    val = float(p[1 + i])
                    if val < mn[i]:
                        mn[i] = val
                    if val > mx[i]:
                        mx[i] = val
            elif line.startswith("usemtl "):
                mats.add(line[7:].strip())
            elif line.startswith("f "):
                tris += 1
            elif header is None and line.startswith("#"):
                header = line.strip()
    return {"tris": tris, "mats": sorted(mats),
            "min": [round(v, 5) for v in mn], "max": [round(v, 5) for v in mx],
            "header": header}


def main():
    files = sorted(f for f in os.listdir(DST) if f.lower().endswith(".obj"))
    scan_out = {}
    for f in files:
        cell = os.path.splitext(f)[0]
        src = os.path.join(SRC, f)
        rec = {"v2": scan(os.path.join(DST, f))}
        if os.path.exists(src):
            rec["src"] = scan(src)
        scan_out[cell] = rec
    with open(SCAN_OUT, "w") as fh:
        json.dump(scan_out, fh)
    print("scanned %d objs -> %s" % (len(scan_out), SCAN_OUT))

    man = json.load(open(MANIFEST))
    cells = {}
    for c in man["cells"]:
        cells[c["cell"]] = c
        cells["c" + c["cell"]] = c

    total = 0
    extra = {}
    bad_tris, bad_bbox, decal_split, missing = [], [], [], []
    joint_cells = sign_cells = 0
    mj_names = set()
    for cell, rec in scan_out.items():
        tris, mats = rec["v2"]["tris"], set(rec["v2"]["mats"])
        if cell in NON_CELL:
            extra[cell] = tris
            continue
        total += tris
        if rec["v2"]["header"] and "decal split" in rec["v2"]["header"].lower():
            decal_split.append(cell)
        if any(x.startswith("mat_joint") for x in mats):
            joint_cells += 1
        mj_names.update(x for x in mats if x.startswith("mat_mj"))
        if any(x.startswith("road_signs") for x in mats):
            sign_cells += 1
        m = cells.get(cell)
        if m is None:
            missing.append(cell)
            continue
        if tris != m["tris"]:
            bad_tris.append([cell, tris, m["tris"]])
        if "src" in rec:
            d = [abs((rec["v2"]["max"][i] - rec["v2"]["min"][i])
                     - (rec["src"]["max"][i] - rec["src"]["min"][i])) for i in range(3)]
            if max(d) > TOL:
                bad_bbox.append([cell, [round(v, 4) for v in d]])

    print("cells: %d   extra (non-cell): %s" % (len(scan_out) - len(extra), extra))
    print("total tris: %d (manifest %d)" % (total, man["total_tris"]))
    print("joint cells: %d   road_signs cells: %d   distinct mat_mj names: %d"
          % (joint_cells, sign_cells, len(mj_names)))
    print("decal-split headers: %d %s" % (len(decal_split), decal_split[:5]))
    print("cells not in manifest: %d %s" % (len(missing), missing[:5]))
    print("tri mismatches: %d %s" % (len(bad_tris), bad_tris[:8]))
    print("bbox extent drift > 1mm: %d %s" % (len(bad_bbox), bad_bbox[:8]))
    ok = (total == man["total_tris"] and not bad_tris and not bad_bbox and not decal_split
          and not missing and joint_cells == 187 and sign_cells == 28 and len(mj_names) == 92)
    print("A1_GATE_" + ("OK" if ok else "FAIL"))


if __name__ == "__main__":
    main()
