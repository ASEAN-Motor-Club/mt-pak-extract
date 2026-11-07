"""Re-base every cell OBJ so its pivot sits on its own 500 m grid origin.

The original import baked absolute BeamNG world coordinates into the vertices and
placed every actor at (0,0,0). Motor Town's road/nav/spawn systems work from actor
transforms, so a flattened level is invisible to them.

This writes meshes_local/<name>.obj with x,y shifted by -origin (origin snapped down
to the 500 m cell grid) and records origin per tile in cell_origins.json. Importing
those at scale 100 and placing each actor at origin*100 reproduces the identical
world geometry with real transforms.
"""
import json
import math
import os
import sys

SRC = r"D:\C1FullMirror\meshes"
DST = r"D:\C1FullMirror\meshes_local"
ORIGINS = r"D:\C1FullMirror\cell_origins.json"
CELL = 500.0        # metres per BeamNG cell
SCALE = 100.0       # metres -> centimetres for the actor transform


def read_min_xy(path):
    mnx = mny = float("inf")
    with open(path, "r", errors="ignore") as f:
        for line in f:
            if line.startswith("v "):
                p = line.split()
                x = float(p[1]); y = float(p[2])
                if x < mnx: mnx = x
                if y < mny: mny = y
    return mnx, mny


def rewrite(path, out, ox, oy):
    with open(path, "r", errors="ignore") as f, open(out, "w") as g:
        for line in f:
            if line.startswith("vt "):
                # Geometry is mirrored along Y (BeamNG -> MT level frame), which
                # reverses the texture. Mirror V to match: v' = 1 - v.
                q = line.rstrip("\n").split()
                if len(q) >= 3:
                    u = float(q[1])
                    v = 1.0 - float(q[2])
                    rest = " ".join(q[3:])
                    g.write("vt %.6f %.6f%s\n" % (u, v, (" " + rest) if rest else ""))
                else:
                    g.write(line)
            elif line.startswith("v "):
                p = line.rstrip("\n").split()
                x = float(p[1]) - ox
                # Leave Y alone: MT runs on the opposite Y axis from BeamNG, so the
                # importer's Y negation IS the correct conversion. The actor transform
                # compensates instead (see set_transforms.py: y = -origin*100).
                y = float(p[2]) - oy
                rest = " ".join(p[3:])
                g.write("v %.4f %.4f %s\n" % (x, y, rest))
            else:
                g.write(line)


def main():
    os.makedirs(DST, exist_ok=True)
    files = sorted(f for f in os.listdir(SRC) if f.lower().endswith(".obj"))
    origins = {}
    done = 0
    for name in files:
        src = os.path.join(SRC, name)
        mnx, mny = read_min_xy(src)
        if not math.isfinite(mnx) or not math.isfinite(mny):
            print("SKIP %s (no vertices)" % name)
            continue
        ox = math.floor(mnx / CELL) * CELL
        oy = math.floor(mny / CELL) * CELL
        rewrite(src, os.path.join(DST, name), ox, oy)
        origins[os.path.splitext(name)[0]] = [ox, oy]
        done += 1
        if done % 50 == 0:
            print("rebased %d/%d" % (done, len(files)), flush=True)

    with open(ORIGINS, "w") as f:
        json.dump(origins, f, indent=1)
    print("REBASE_DONE files=%d" % done)
    for k in list(origins)[:5]:
        print("  %s origin_m=%s" % (k, origins[k]))


if __name__ == "__main__":
    sys.exit(main())
