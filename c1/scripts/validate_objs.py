"""Reject OBJ files the importer will mangle.

Written after 792 meshes shipped with a sliver running from each actor pivot out to its geometry:
every split OBJ ended with `f 0 1/1/1 2/2/2`, and vertex index 0 is not a vertex — the importer
resolves it to the mesh origin. One line per file, invisible in file sizes and triangle counts,
visible as a map that looks exploded.

Checks, cheapest first, streaming (these files run to tens of megabytes):
  1. face lines using index 0
  2. negative face indices (relative references)
  3. face indices beyond the vertex count
  4. UV indices beyond the `vt` count
  5. faces with fewer than three corners

Usage: python3 c1/scripts/validate_objs.py <dir-or-file> [...]
Exit code 1 if anything fails, with one line per offending file.
"""
import os
import sys


def check(path):
    nv = nvt = 0
    problems = {"index_zero": 0, "negative": 0, "vertex_out_of_range": 0,
                "uv_out_of_range": 0, "short_face": 0}
    worst = None
    with open(path, "r", errors="ignore") as f:
        for lineno, line in enumerate(f, 1):
            if line.startswith("v "):
                nv += 1
            elif line.startswith("vt "):
                nvt += 1
            elif line.startswith("f "):
                toks = line.split()[1:]
                if len(toks) < 3:
                    problems["short_face"] += 1
                    worst = worst or (lineno, line.strip())
                    continue
                for tok in toks:
                    parts = tok.split("/")
                    if parts[0] in ("", "0"):
                        problems["index_zero"] += 1
                        worst = worst or (lineno, line.strip())
                        continue
                    vi = int(parts[0])
                    if vi < 0:
                        problems["negative"] += 1
                        worst = worst or (lineno, line.strip())
                    elif nv and vi > nv:
                        problems["vertex_out_of_range"] += 1
                        worst = worst or (lineno, line.strip())
                    if len(parts) > 1 and parts[1]:
                        ti = int(parts[1])
                        if nvt and 0 < ti and ti > nvt:
                            problems["uv_out_of_range"] += 1
                            worst = worst or (lineno, line.strip())
                        elif ti == 0:
                            problems["index_zero"] += 1
                            worst = worst or (lineno, line.strip())
    return nv, nvt, {k: v for k, v in problems.items() if v}, worst


def iter_targets(args):
    for arg in args:
        if os.path.isdir(arg):
            for name in sorted(os.listdir(arg)):
                if name.lower().endswith(".obj"):
                    yield os.path.join(arg, name)
        else:
            yield arg


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    bad = 0
    total = 0
    for path in iter_targets(args):
        total += 1
        nv, nvt, problems, worst = check(path)
        if problems:
            bad += 1
            detail = ", ".join("%s=%d" % kv for kv in problems.items())
            print("FAIL %s v=%d vt=%d %s" % (os.path.basename(path), nv, nvt, detail))
            if worst:
                print("     line %d: %s" % worst)
    print("checked=%d failed=%d" % (total, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
