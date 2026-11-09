"""A0 gate: validate slotmap.json and build c1_cell_baseline.json.

Baseline per cell: triangle count (from the canonical OBJ manifest), slot count and non-null slot
count (from the dumped shipped asset), and the material list. Every non-null slot must resolve to a
material instance that exists in the shipped pak.
"""
import json
import os
import re
import sys

PAK = "/opt/data/cache/scratch/pakcur/MotorTown/Content/Mods/C1Full"
SLOTMAP = sys.argv[1]
MANIFEST = "/opt/data/cache/scratch/c1/cells_full_manifest.json"
OUT = sys.argv[2]


def main():
    sm = json.load(open(SLOTMAP))
    man = json.load(open(MANIFEST))
    matdir = os.path.join(PAK, "Materials")
    have = {f[:-7] for f in os.listdir(matdir) if f.endswith(".uasset")}
    print("slotmap cells: %d   shipped material instances: %d" % (len(sm), len(have)))

    missing_cells = []
    bad_mi = []
    total_slots = total_null = 0
    for cell, rec in sm.items():
        total_slots += rec["want_slots"]
        total_null += sum(1 for s in rec["slots"]
                          if s["mi"] is None or s["mi"].endswith("WorldGridMaterial"))
        for s in rec["slots"]:
            if s["mi"] is None:
                continue
            name = s["mi"].rsplit("/", 1)[-1]
            if name == "WorldGridMaterial":
                continue  # engine default for an empty slot; counted as null below
            if name not in have:
                bad_mi.append((cell, name))
    print("slots total: %d   null slots: %d (%.1f%%)"
          % (total_slots, total_null, 100.0 * total_null / max(1, total_slots)))
    print("unresolved MIs: %d %s" % (len(bad_mi), bad_mi[:5]))

    # manifest keys are bare cell names ("7_17"); asset keys carry the leading "c" ("c7_17")
    cells = {}
    for c in man["cells"]:
        key = "c" + c["cell"]
        cells[key] = c
        cells[c["cell"]] = c
    print("manifest sample keys:", list(cells)[:3])
    baseline = {}
    for cell, rec in sm.items():
        m = cells.get(cell)
        if m is None:
            missing_cells.append(cell)
            continue
        baseline[cell] = {
            "tris": m["tris"],
            "slots": rec["want_slots"],
            "nonnull": rec["want_nonnull"],
            "materials": m["materials"],
        }
    print("cells without manifest entry: %d %s" % (len(missing_cells), missing_cells[:5]))
    print("baseline cells: %d   tris total: %d"
          % (len(baseline), sum(v["tris"] for v in baseline.values())))

    # pak shape gates
    meshdir = os.path.join(PAK, "Meshes")
    meshes = [f for f in os.listdir(meshdir) if f.endswith(".uasset")]
    lods = os.path.join(PAK, "Meshes_LOD")
    print("shipped meshes: %d   Meshes_LOD present: %s" % (len(meshes), os.path.isdir(lods)))

    with open(OUT, "w") as fh:
        json.dump(baseline, fh, indent=1, sort_keys=True)
    print("wrote", OUT)
    ok = not bad_mi and not missing_cells and len(meshes) == 555 and not os.path.isdir(lods)
    print("A0_GATE_" + ("OK" if ok else "FAIL"))


if __name__ == "__main__":
    main()
