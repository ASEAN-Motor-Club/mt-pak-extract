"""Generate c1/config/tp_points.json from the original BeamNG level source.

The named teleport targets the client mod's /tp understands are read from the map's own
mission groups, not hand-copied, so a re-derived source cannot drift from the shipped table.

    python3 c1/tools/make_tp_points.py /opt/data/inbox/c1src/c1_src.zip \
        > c1/config/tp_points.json

Conversion is the same one the geometry port uses: bng metres -> UE cm as
(x*100, -y*100, z*100). An entry with no `rotationMatrix` is identity (forward = +Y_bng),
i.e. UE yaw 270.
"""
import json
import re
import sys
import zipfile

GROUPS = ("playerdroppoints", "garage_marker", "trap", "tunnel_triggers")
LANDMARK = {"spawn_default": ["shibaura"], "spawn_parking": ["tatsumi"],
            "spawn_road": ["yotsuya"], "spawn_new": ["haneda"],
            "spawn_mirai": ["mirai", "shin_yamashita"]}


def items(zf, group):
    path = f"levels/c1/main/missiongroup/{group}/items.level.json"
    out = []
    for line in zf.read(path).decode("utf-8", "replace").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def ue(pos):
    x, y, z = pos[:3]
    return [round(x * 100), round(-y * 100), round(z * 100)]


def by_number(objs):
    def key(o):
        m = re.search(r"(\d+)$", o.get("name", ""))
        return int(m.group(1)) if m else 0
    return sorted(objs, key=key)


def main(argv):
    zf = zipfile.ZipFile(argv[0])
    table = []
    for o in items(zf, "playerdroppoints"):
        name = o.get("name")
        if name == "spawn_garage":
            continue          # rewritten to the active garage slot at runtime
        coords = ue(o["position"])
        table.append([name, coords])
        for alias in LANDMARK.get(name, ()):
            table.append([alias, coords])
    for i, o in enumerate(items(zf, "garage_marker"), 1):
        table.append([f"garage{i}", ue(o["position"])])
    for i, o in enumerate(by_number(items(zf, "trap")), 1):
        table.append([f"trap{i}", ue(o["position"])])
    for i, o in enumerate(by_number(items(zf, "tunnel_triggers")), 1):
        table.append([f"tunnel{i}", ue(o["position"])])
    # one entry per line keeps the committed table diffable
    sys.stdout.write("[\n" + ",\n".join(json.dumps(e) for e in table) + "\n]\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
