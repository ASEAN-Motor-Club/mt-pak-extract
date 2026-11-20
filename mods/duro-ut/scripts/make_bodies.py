#!/usr/bin/env python3
"""Author the Duro swappable rear bodies as OBJs.

Styling reference: BeamNG Gavril MD-Series upfits.
  MD70 Dump Bed  - tapered ribbed steel box, capped top rail, headboard above
                   the cab, top-hinged ribbed tailgate with bottom latches,
                   subframe with scissor hoist.
  MD60 Tanker    - true cylinder with dished heads, two manhole hatches, a
                   curved crown railing on two stanchions, rear ladder, two
                   saddle cradles on a subframe.

Duro local frame (UE cm): X = length (+X toward the cab), Y = width, Z = up.
Bed opening after the cut: x -330 .. -62, y +-118, floor top z 92.
OBJ vertices are written in UE cm; the Interchange import applies no scale and
no axis conversion (see the linux-mesh-cook skill).

Output: obj/duro_dump_body.obj, obj/duro_tanker_body.obj
"""
import math
import os

X_REAR, X_FRONT = -330.0, -62.0
Y_HALF = 118.0
Z_FLOOR = 92.0


class OBJ:
    def __init__(self):
        self.v, self.f = [], []

    def vert(self, p):
        self.v.append(p)
        return len(self.v)

    def quad(self, a, b, c, d):
        i = len(self.v)
        for p in (a, b, c, d):
            self.vert(p)
        self.f.append((i + 1, i + 2, i + 3, i + 4))

    def tri(self, a, b, c):
        i = len(self.v)
        for p in (a, b, c):
            self.vert(p)
        self.f.append((i + 1, i + 2, i + 3))

    def box(self, x0, x1, y0, y1, z0, z1):
        q = self.quad
        q((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1))   # top
        q((x0, y1, z0), (x1, y1, z0), (x1, y0, z0), (x0, y0, z0))   # bottom
        q((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1))   # -Y
        q((x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1))   # +Y
        q((x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1))   # rear
        q((x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1))   # front

    def slab(self, x0, x1, yb, yt, z0, z1, thick):
        """Tapered wall running along X.

        yb/yt are the OUTER half-widths at the bottom and top edge; the wall
        thickness goes inward, so the panel leans in toward the top like a
        dump body side.
        """
        s = 1.0 if yb > 0 else -1.0
        yb, yt = abs(yb), abs(yt)
        ob0, ob1 = s * yb, s * (yb - thick)
        ot0, ot1 = s * yt, s * (yt - thick)
        q = self.quad
        q((x0, ob0, z0), (x1, ob0, z0), (x1, ot0, z1), (x0, ot0, z1))   # outer
        q((x1, ob1, z0), (x0, ob1, z0), (x0, ot1, z1), (x1, ot1, z1))   # inner
        q((x0, ot0, z1), (x1, ot0, z1), (x1, ot1, z1), (x0, ot1, z1))   # top edge
        q((x0, ob1, z0), (x1, ob1, z0), (x1, ob0, z0), (x0, ob0, z0))   # bottom
        q((x0, ob1, z0), (x0, ob0, z0), (x0, ot0, z1), (x0, ot1, z1))   # rear
        q((x1, ob0, z0), (x1, ob1, z0), (x1, ot1, z1), (x1, ot0, z1))   # front

    def cyl(self, p0, p1, r, seg=16, caps=True):
        """Cylinder between two points on any axis."""
        ax = [p1[i] - p0[i] for i in range(3)]
        ln = math.sqrt(sum(c * c for c in ax))
        ax = [c / ln for c in ax]
        ref = (0.0, 0.0, 1.0) if abs(ax[2]) < 0.9 else (1.0, 0.0, 0.0)
        u = (ax[1] * ref[2] - ax[2] * ref[1],
             ax[2] * ref[0] - ax[0] * ref[2],
             ax[0] * ref[1] - ax[1] * ref[0])
        ul = math.sqrt(sum(c * c for c in u))
        u = [c / ul for c in u]
        w = (ax[1] * u[2] - ax[2] * u[1],
             ax[2] * u[0] - ax[0] * u[2],
             ax[0] * u[1] - ax[1] * u[0])
        ring0, ring1 = [], []
        for i in range(seg):
            a = 2 * math.pi * i / seg
            d = [math.cos(a) * u[k] + math.sin(a) * w[k] for k in range(3)]
            ring0.append(tuple(p0[k] + r * d[k] for k in range(3)))
            ring1.append(tuple(p1[k] + r * d[k] for k in range(3)))
        for i in range(seg):
            j = (i + 1) % seg
            self.quad(ring0[i], ring0[j], ring1[j], ring1[i])
        if caps:
            for ring, p in ((ring0, p0), (ring1, p1)):
                for i in range(seg):
                    j = (i + 1) % seg
                    self.tri(p, ring[j], ring[i])

    def arc_slab(self, x, half_w, cz, cy, radius, a0, a1, thick, seg=12):
        """Saddle cradle: a band of a cylinder around the Y axis at x."""
        inner = radius - thick
        for i in range(seg):
            t0 = a0 + (a1 - a0) * i / seg
            t1 = a0 + (a1 - a0) * (i + 1) / seg
            def pt(ang, r, xx):
                return (xx, cy + r * math.cos(ang), cz + r * math.sin(ang))
            self.quad(pt(t0, inner, x - half_w), pt(t1, inner, x - half_w),
                      pt(t1, radius, x - half_w), pt(t0, radius, x - half_w))
            self.quad(pt(t1, inner, x + half_w), pt(t0, inner, x + half_w),
                      pt(t0, radius, x + half_w), pt(t1, radius, x + half_w))
            self.quad(pt(t0, radius, x - half_w), pt(t1, radius, x - half_w),
                      pt(t1, radius, x + half_w), pt(t0, radius, x + half_w))
            self.quad(pt(t1, inner, x - half_w), pt(t0, inner, x - half_w),
                      pt(t0, inner, x + half_w), pt(t1, inner, x + half_w))
        for xx in (x - half_w, x + half_w):
            for i in range(seg):
                t0 = a0 + (a1 - a0) * i / seg
                t1 = a0 + (a1 - a0) * (i + 1) / seg
                def pt(ang, r, q=xx):
                    return (q, cy + r * math.cos(ang), cz + r * math.sin(ang))
                self.quad(pt(t0, inner), pt(t0, radius), pt(t1, radius), pt(t1, inner))

    def write(self, path, usemtl='CargoBed_01'):
        with open(path, 'w') as fh:
            fh.write('# procedural rear body for the Duro, UE cm, importer scale 1\n')
            fh.write(f'usemtl {usemtl}\n')
            for x, y, z in self.v:
                fh.write(f'v {x:.4f} {y:.4f} {z:.4f}\n')
            for _ in self.v:
                fh.write('vt 0.000000 0.000000\n')
            for face in self.f:
                fh.write('f ' + ' '.join(f'{i}/{i}' for i in face) + '\n')
        print(f'wrote {path}: {len(self.v)} verts, {len(self.f)} faces')


# ---------------------------------------------------------------- shared bits

def subframe(o, z_top=Z_FLOOR, rails=(-58.0, 58.0), width=7.0, x0=X_REAR, x1=X_FRONT):
    """Chassis rails + cross members the body bolts to."""
    for y in rails:
        o.box(x0, x1, y - width, y + width, z_top - 10, z_top)
    for x in (x0 + 20, -240.0, -150.0, x1 - 25):
        o.box(x - 6, x + 6, rails[0] - width, rails[1] + width, z_top - 8, z_top - 2)


# ---------------------------------------------------------------- MD70 dump

DUMP_X0 = -330.0   # full bed length: the lamps now live on the rear bumper bar
DUMP_X1 = -72.0
DUMP_YB = 112.0      # outer half width at the floor
DUMP_YT = 104.0      # outer half width at the top (sides lean in 8 cm)
DUMP_Z0 = 110.0      # body floor top - raised 18 cm over the chassis so the
                     # subframe and hoist read from the side like the MD upfit
DUMP_TOP = 208.0     # side wall top, level with the cab roof
DUMP_HB = 236.0      # headboard top, above the cab roof
RIB_OUT = 3.5


def dump_body(path):
    o = OBJ()
    t = 5.0
    z0 = DUMP_Z0
    # floor plate
    o.box(DUMP_X0, DUMP_X1, -DUMP_YB, DUMP_YB, z0 - 7, z0 - 1)
    o.box(DUMP_X0, DUMP_X1, -DUMP_YB + 3, DUMP_YB - 3, z0 - 1, z0)
    # side walls, tapered, with an external rib every ~48 cm
    for sgn in (-1, 1):
        o.slab(DUMP_X0, DUMP_X1, sgn * DUMP_YB, sgn * DUMP_YT, z0 - 1, DUMP_TOP, t)
        # capped top rail, slightly proud of the panel
        o.box(DUMP_X0 - 2, DUMP_X1 + 2, min(sgn * DUMP_YT, sgn * (DUMP_YT - 9)),
              max(sgn * DUMP_YT, sgn * (DUMP_YT - 9)), DUMP_TOP - 6, DUMP_TOP)
        n = 5
        for i in range(1, n + 1):
            xc = DUMP_X0 + (DUMP_X1 - DUMP_X0) * i / (n + 1)
            yb = DUMP_YB + RIB_OUT
            yt = DUMP_YT + RIB_OUT
            o.slab(xc - 4, xc + 4, sgn * yb, sgn * yt, z0 + 6, DUMP_TOP - 8, 2.5)
    # headboard: full width, taller than the sides, ribs on the bed face
    o.box(DUMP_X1 - 10, DUMP_X1, -DUMP_YT + 1, DUMP_YT - 1, z0 - 1, DUMP_HB)
    for i in range(4):
        yc = -DUMP_YT + 12 + i * (2 * DUMP_YT - 24) / 3.0
        o.box(DUMP_X1 - 14, DUMP_X1 - 8, yc - 5, yc + 5, z0 + 6, DUMP_HB - 8)
    # tailgate: top-hinged, ribbed, with bottom latches
    gx0, gx1 = DUMP_X0, DUMP_X0 + 8
    o.box(gx0, gx1, -108, 108, z0 + 2, DUMP_TOP - 4)
    for i in range(4):
        yc = -108 + 6 + i * (216 - 12) / 3.0
        o.box(gx0 - 3, gx0, yc - 5, yc + 5, z0 + 8, DUMP_TOP - 10)
    o.cyl((gx0 + 4, -108, DUMP_TOP - 2), (gx0 + 4, 108, DUMP_TOP - 2), 3.0, seg=10)
    for yc in (-96, 96):
        o.box(gx0 - 8, gx0 + 3, yc - 9, yc + 9, z0 + 4, z0 + 20)
    # subframe + scissor hoist, in the 18 cm gap under the floor
    subframe(o)                                                    # chassis rails
    for y in (-58.0, 58.0):                                        # lift frame
        o.box(DUMP_X0 + 6, DUMP_X1 - 4, y - 6, y + 6, Z_FLOOR - 2, z0 - 7)
    for x in (-286.0, -210.0, -130.0):
        o.box(x - 6, x + 6, -58, 58, Z_FLOOR - 2, Z_FLOOR + 6)     # cross members
    o.cyl((-236.0, -22.0, Z_FLOOR + 2), (-120.0, -22.0, z0 - 4), 6.0, seg=10)  # ram
    o.cyl((-236.0, 22.0, Z_FLOOR + 2), (-120.0, 22.0, z0 - 4), 6.0, seg=10)
    o.box(-244.0, -226.0, -26, 26, Z_FLOOR - 4, Z_FLOOR + 10)      # ram body
    o.cyl((-76.0, -52.0, z0 - 12), (-76.0, 52.0, z0 - 12), 7.0, seg=12)   # front pivot
    o.cyl((-290.0, -52.0, Z_FLOOR), (-290.0, 52.0, Z_FLOOR), 6.0, seg=12)  # rear hinge
    o.write(path)


# ---------------------------------------------------------------- MD60 tanker

TANK_X0 = -318.0
TANK_X1 = -66.0
TANK_R = 70.0
TANK_CZ = 178.0
TANK_DOME = 18.0
TANK_SEG = 24


def tanker_body(path):
    o = OBJ()
    # barrel + dished heads
    x0, x1 = TANK_X0 + TANK_DOME, TANK_X1 - TANK_DOME
    for i in range(TANK_SEG):
        a0 = 2 * math.pi * i / TANK_SEG
        a1 = 2 * math.pi * (i + 1) / TANK_SEG
        y0, z0 = TANK_R * math.cos(a0), TANK_CZ + TANK_R * math.sin(a0)
        y1, z1 = TANK_R * math.cos(a1), TANK_CZ + TANK_R * math.sin(a1)
        # wound so the normal points away from the X axis (was inside-out)
        o.quad((x0, y0, z0), (x0, y1, z1), (x1, y1, z1), (x1, y0, z0))
    for x, sgn in ((x0, -1), (x1, 1)):
        rings = [0.35, 0.62, 0.82]
        prev = None
        for k, frac in enumerate(rings):
            xx = x + sgn * TANK_DOME * frac
            rr = TANK_R * math.sqrt(max(0.0, 1.0 - frac * frac))
            ring = [(xx, rr * math.cos(2 * math.pi * i / TANK_SEG),
                     TANK_CZ + rr * math.sin(2 * math.pi * i / TANK_SEG))
                    for i in range(TANK_SEG)]
            if prev is None:
                for i in range(TANK_SEG):
                    j = (i + 1) % TANK_SEG
                    o.quad(ring[i], ring[j],
                           (x, TANK_R * math.cos(2 * math.pi * j / TANK_SEG),
                            TANK_CZ + TANK_R * math.sin(2 * math.pi * j / TANK_SEG)),
                           (x, TANK_R * math.cos(2 * math.pi * i / TANK_SEG),
                            TANK_CZ + TANK_R * math.sin(2 * math.pi * i / TANK_SEG)))
            else:
                for i in range(TANK_SEG):
                    j = (i + 1) % TANK_SEG
                    o.quad(prev[i], ring[i], ring[j], prev[j])
            prev = ring
        apex = (x + sgn * TANK_DOME, 0.0, TANK_CZ)
        for i in range(TANK_SEG):
            j = (i + 1) % TANK_SEG
            o.tri(prev[i], apex, prev[j])
    top = TANK_CZ + TANK_R
    # two manhole hatches: collar + domed lid
    for hx in (-280.0, -108.0):
        o.cyl((hx, 0, top - 3), (hx, 0, top + 9), 21.0, seg=16)
        o.cyl((hx, 0, top + 9), (hx, 0, top + 13), 24.0, seg=16)
    # crown railing on two stanchions, plus cross braces
    for sx in (-272.0, -116.0):
        o.cyl((sx, -34, top - 4), (sx, -34, top + 25), 3.0, seg=8)
        o.cyl((sx, 34, top - 4), (sx, 34, top + 25), 3.0, seg=8)
        o.cyl((sx, -34, top + 25), (sx, 34, top + 25), 3.0, seg=8)
    for yy in (-34.0, 34.0):
        o.cyl((-272.0, yy, top + 25), (-116.0, yy, top + 25), 3.0, seg=8)
    o.cyl((-232.0, -34, top + 25), (-232.0, 34, top + 25), 2.5, seg=8)
    o.cyl((-156.0, -34, top + 25), (-156.0, 34, top + 25), 2.5, seg=8)
    # rear ladder on the rear head
    lx = TANK_X0 - 2
    for yy in (-14.0, 14.0):
        o.cyl((lx, yy, 104), (lx, yy, top - 4), 2.5, seg=8)
    z = 116.0
    while z < top - 12:
        o.cyl((lx, -14, z), (lx, 14, z), 2.0, seg=8)
        z += 24.0
    # two saddle cradles wrapping the lower barrel
    for sx in (-292.0, -96.0):
        o.arc_slab(sx, 8.0, TANK_CZ, 0.0, TANK_R + 2, math.radians(200), math.radians(340), 6.0)
    # subframe, plus the bracket that ties the front head to the cab
    subframe(o, x0=TANK_X0 + 4, x1=TANK_X1 - 4)
    o.box(TANK_X1 - 20, TANK_X1 - 4, -24, 24, Z_FLOOR - 2, Z_FLOOR + 12)
    # small discharge valve cluster at the rear, under the barrel
    o.box(TANK_X0 + 6, TANK_X0 + 30, -26, 26, Z_FLOOR - 4, Z_FLOOR + 26)
    o.cyl((TANK_X0 + 8, -12, Z_FLOOR + 8), (TANK_X0 - 10, -12, Z_FLOOR + 8), 4.0, seg=8)
    o.cyl((TANK_X0 + 8, 12, Z_FLOOR + 8), (TANK_X0 - 10, 12, Z_FLOOR + 8), 4.0, seg=8)
    o.write(path)


if __name__ == '__main__':
    out = os.path.dirname(os.path.abspath(__file__)) + '/obj'
    os.makedirs(out, exist_ok=True)
    dump_body(out + '/duro_dump_body.obj')
    tanker_body(out + '/duro_tanker_body.obj')
