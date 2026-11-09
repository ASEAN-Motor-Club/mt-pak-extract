"""Build slotmap.json: the shipped slot -> MI binding for the cells being rebuilt.

The mapping must be read from the SHIPPED asset (or a UAssetTool --dump of it), because
delete-then-import destroys the only copy of the binding. Three rules learned the hard way:

  * the array is positional and gaps are meaningful: a slot whose `MaterialInterface` is
    absent must be reproduced as an EMPTY slot, never dropped, or every later slot shifts
    and the mesh renders the wrong material on its faces while the non-null count matches;
  * the shipped slot name is the OBJ `usemtl` name minus its numeric suffix
    (`usemtl mat_botom_u_10` -> slot `mat_botom_u` -> MI_C1_mat_botom_u_10), so
    consumers must resolve exact-first then longest-prefix;
  * `dum` (BeamNG's collision-only dummy material) is dropped only for cells whose
    geometry was actually stripped.

Usage (inside the container):
    UAssetTool --dump <shipped>/<cell>.uasset > dump.txt
    python3 make_slotmap.py dump:dump.txt:c-1_-3 [dump:...:c1_-8 ...] > slotmap.json

Output:
    { "<cell>": { "want_slots": N, "want_nonnull": M,
                  "slots": [ {"slot": ..., "imported": ..., "mi": "/Game/..."|null}, ... ] } }
"""
import json
import re
import sys

MAT_DIR = "/Game/Mods/C1Full/Materials/"


def parse_dump(path):
    """Return (slots, want_slots, want_nonnull) from a UAssetTool dump."""
    lines = open(path, errors="ignore").read().splitlines()
    imports = {}
    for line in lines:
        m = re.match(r"\s*Import\[(\d+)\]: (.*)", line)
        if m:
            nm = re.search(r"Name=(\S+)", m.group(2))
            imports[int(m.group(1))] = nm.group(1) if nm else "?"

    # locate the StaticMaterials array and walk its entries
    start = None
    count = None
    for i, line in enumerate(lines):
        m = re.search(r"StaticMaterials \(Array\[(\d+)\]\):", line)
        if m:
            start = i + 1
            count = int(m.group(1))
            break
    if start is None or count is None:
        raise SystemExit("no StaticMaterials array in %s" % path)

    entries = {}
    for line in lines[start:]:
        if re.search(r"StaticMaterials \(Array\[\d+\]\):", line) and entries:
            break
        idx = re.match(r"\s*\[(\d+)\] ", line)
        if not idx:
            continue
        n = int(idx.group(1))
        if n >= count:
            continue
        e = entries.setdefault(n, {"slot": None, "imported": None, "idx": None})
        mi = re.search(r"MaterialInterface \(Object\): Index=(-?\d+)", line)
        sn = re.search(r"MaterialSlotName \(Name\): (.+)$", line)
        im = re.search(r"ImportedMaterialSlotName \(Name\): (.+)$", line)
        if mi:
            e["idx"] = int(mi.group(1))
        elif sn:
            e["slot"] = sn.group(1).strip()
        elif im:
            e["imported"] = im.group(1).strip()

    slots = []
    nonnull = 0
    for n in range(count):
        e = entries.get(n, {"slot": None, "imported": None, "idx": None})
        mi = None
        if e["idx"] not in (None, 0):
            name = imports.get(-e["idx"] - 1, "?")
            if name == "WorldGridMaterial":
                # UE's placeholder for a slot with no material; a real binding never names it.
                # Counting it as non-null is what invented a /Game/.../WorldGridMaterial path.
                mi = None
            else:
                mi = name if name.startswith("/Game/") else MAT_DIR + name
                nonnull += 1
        slots.append({
            "slot": e["slot"],
            "imported": e["imported"] or e["slot"],
            "mi": mi,
        })
    return slots, count, nonnull


def main(argv):
    result = {}
    for spec in argv:
        kind, path, cell = spec.split(":", 2)
        if kind != "dump":
            sys.exit("unsupported source %r (expected dump:<file>:<cell>)" % kind)
        slots, want, nonnull = parse_dump(path)
        result[cell] = {
            "want_slots": want,
            "want_nonnull": nonnull,
            "slots": slots,
        }
    json.dump(result, sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))