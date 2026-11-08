"""Build slotmap.json: the shipped slot -> MI binding for the cells being rebuilt.

The mapping must be read from the SHIPPED asset (or a UAssetTool --dump of it), because
delete-then-import destroys the only copy of the binding. Two rules learned the hard way:

  * the shipped slot name is the OBJ `usemtl` name minus its numeric suffix
    (`usemtl mat_botom_u_10` -> slot `mat_botom_u` -> MI_C1_mat_botom_u_10), so
    consumers must resolve exact-first then longest-prefix;
  * `dum` (BeamNG's collision-only dummy material) is dropped only for cells whose
    geometry was actually stripped.

Usage (inside the container):
    UAssetTool --dump <shipped>/<cell>.uasset > dump.txt
    python3 make_slotmap.py dump:dump.txt:c-1_-3 [dump:...:c1_-8 ...] > slotmap.json
"""
import json
import re
import sys

MAT_DIR = "/Game/Mods/C1Full/Materials/"


def parse_dump(path):
    """Return [(slot_name, mi_path)] in slot order from a UAssetTool dump."""
    lines = open(path, errors="ignore").read().splitlines()
    imports = {}
    for line in lines:
        m = re.match(r"\s*Import\[(\d+)\]: (.*)", line)
        if m:
            nm = re.search(r"Name=(\S+)", m.group(2))
            imports[int(m.group(1))] = nm.group(1) if nm else "?"
    slots, cur = [], None
    for line in lines:
        mi = re.search(r"MaterialInterface \(Object\): Index=(-?\d+)", line)
        sn = re.search(r"MaterialSlotName \(Name\): (.+)$", line)
        if mi:
            cur = int(mi.group(1))
        elif sn and cur is not None:
            slots.append((sn.group(1).strip(), cur))
            cur = None
    out = []
    for slot, idx in slots:
        name = imports.get(-idx - 1, "?") if idx < 0 else "?"
        mi = name if name.startswith("/Game/") else MAT_DIR + name
        out.append([slot, mi])
    return out


def main(argv):
    result = {}
    for spec in argv:
        kind, path, cell = spec.split(":", 2)
        if kind != "dump":
            sys.exit("unsupported source %r (expected dump:<file>:<cell>)" % kind)
        result[cell] = parse_dump(path)
    json.dump(result, sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
