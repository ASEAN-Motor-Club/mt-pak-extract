"""Remove mat_saku_08_02 (lane rope) faces from the canonical cell OBJs.

Source is meshes_local, NOT nc_out/cells_v2: the split re-export is lossy and
shredded the map when it was used as the structural import source. Here the
canonical OBJ is copied verbatim except that faces whose material is the rope
material are dropped, so every other face keeps its original vertices and
material assignment.

Only cells that actually contain the material are written, to noropes/.
"""
import os
import json

SRC = r"D:\C1FullMirror\meshes_local"
DST = r"D:\C1FullMirror\noropes"
REPORT = r"D:\C1FullMirror\noropes_report.json"
TARGET = "mat_saku_08_02"


def main():
    os.makedirs(DST, exist_ok=True)
    out = {}
    for f in sorted(os.listdir(SRC)):
        if not f.lower().endswith(".obj"):
            continue
        mat = None
        drop = 0
        kept = []
        buf = []
        with open(os.path.join(SRC, f), encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith("usemtl "):
                    mat = line[7:].strip()
                if line.startswith("f ") and mat == TARGET:
                    drop += 1
                    continue
                buf.append(line)
        if drop:
            cell = f[:-4]
            with open(os.path.join(DST, f), "w", encoding="utf-8") as fh:
                fh.writelines(buf)
            out[cell] = drop
    json.dump(out, open(REPORT, "w"), indent=1)
    print("NOROPES cells=%d faces_dropped=%d" % (len(out), sum(out.values())))


main()
