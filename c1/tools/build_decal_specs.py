"""Build road specs from the BeamNG DecalRoad AI paths.

The map is a pure Y mirror of the source (verified against the geometry), units are metres
in the source and centimetres in UE. One road actor per DecalRoad keeps both carriageways,
the ramps, and the stacked sections, because every decal is its own one-way path with its
own Z.

    python3 build_decal_specs.py <items.level.json> <out.json>
"""
import json
import math
import statistics
import sys

SPEED_KPH = 120.0

# C1 map geometry bbox (UE cm) -> source metres. Decals outside it have no road geometry
# under them: authoring them puts roads in the void and inflates the nav graph.
BBOX_SRC = (-1530.52, 4938.25, 3574.34, 10522.40)   # x0, y0, x1, y1
MIN_INSIDE_FRAC = 0.60


def to_ue(p):
    return [round(float(p[0]) * 100.0, 2), round(-float(p[1]) * 100.0, 2), round(float(p[2]) * 100.0, 2)]


def main(items_path, out_path):
    rows = [json.loads(l) for l in open(items_path, encoding="utf-8", errors="replace") if l.strip()]
    decals = [r for r in rows if r.get("class") == "DecalRoad"]

    roads = []
    skipped = []
    total_len = 0.0
    for i, d in enumerate(decals):
        nodes = d.get("nodes") or []
        if len(nodes) < 2:
            skipped.append((i, "too_few_nodes"))
            continue

        pts = [to_ue(n) for n in nodes]

        # drop consecutive duplicates (BeamNG sometimes repeats a node at junctions)
        clean = [pts[0]]
        for p in pts[1:]:
            if math.dist(p[:2], clean[-1][:2]) > 1.0:
                clean.append(p)
        if len(clean) < 2:
            skipped.append((i, "degenerate"))
            continue

        length_cm = sum(math.dist(clean[k], clean[k + 1]) for k in range(len(clean) - 1))
        if length_cm < 500.0:          # under 5 m: a stub, not a road
            skipped.append((i, "too_short %.0fcm" % length_cm))
            continue

        x0, y0, x1, y1 = BBOX_SRC
        inside = sum(1 for n in nodes if x0 <= n[0] <= x1 and y0 <= n[1] <= y1)
        if inside < MIN_INSIDE_FRAC * len(nodes):
            skipped.append((i, "outside_bbox %d/%d" % (inside, len(nodes))))
            continue

        lanes_f = int(d.get("lanesLeft", 2) or 0)
        lanes_b = int(d.get("lanesRight", 0) or 0)
        if lanes_f + lanes_b <= 0:
            lanes_f, lanes_b = 2, 0

        widths = [float(n[3]) for n in nodes if len(n) > 3 and n[3]]
        width_m = statistics.median(widths) if widths else 7.0
        lane_width = round(width_m * 100.0 / (lanes_f + lanes_b), 1)

        roads.append({
            "name": "C1_Rd%03d" % i,
            "points": clean,
            "lane_width": lane_width,
            "forward_lanes": lanes_f,
            "backward_lanes": lanes_b,
            "speed_kph": SPEED_KPH,
            "flags": 0,
            "road_type": "Road",
            "source_decal": i,
            "source_width_m": width_m,
            "length_m": round(length_cm / 100.0, 1),
        })
        total_len += length_cm

    out = {"roads": roads, "skipped": skipped,
           "total_length_km": round(total_len / 100000.0, 2)}
    with open(out_path, "w") as f:
        json.dump(out, f, indent=1)

    print("decals=%d roads=%d skipped=%d total_len_km=%.2f" %
          (len(decals), len(roads), len(skipped), total_len / 100000.0))
    print("points_total=%d" % sum(len(r["points"]) for r in roads))
    lw = [r["lane_width"] for r in roads]
    print("lane_width min/median/max: %.0f / %.0f / %.0f" % (min(lw), statistics.median(lw), max(lw)))
    for s in skipped[:10]:
        print("SKIP", s)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
